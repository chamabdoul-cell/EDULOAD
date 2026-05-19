"""Download queue service — job state, workers, URL validation, directory helper."""
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from queue import Queue
from uuid import uuid4

_KNOWN_DOC_EXTS = {".pdf", ".docx", ".txt", ".html", ".htm", ".md", ".epub", ".doc", ".odt"}
_CTYPE_EXT_MAP = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/markdown": ".md",
}


def _infer_ext(ctype: str, dest_path: Path) -> str | None:
    """Return the correct extension from Content-Type, then magic bytes."""
    ext = _CTYPE_EXT_MAP.get(ctype.split(";")[0].strip().lower())
    if ext:
        return ext
    try:
        header = dest_path.read_bytes()[:8]
        if header[:4] == b"%PDF":
            return ".pdf"
        if header[:2] == b"PK":
            return ".docx"
    except Exception:
        pass
    return None


def _is_html_content(dest_path: Path) -> bool:
    """Return True if the file content is an HTML page (not a real document)."""
    try:
        snippet = dest_path.read_bytes()[:32].lower()
        return snippet[:5] in (b"<!doc", b"<html") or b"<html" in snippet
    except Exception:
        return False

from config.settings import AIConfig
from db import get_db
import repositories.history as history_repo
import repositories.queue as queue_repo
import repositories.settings as settings_repo

BASE_DIR = Path(__file__).parent.parent
DL_DIR   = BASE_DIR / "downloads"
DL_DIR.mkdir(exist_ok=True)

_MAX_CONCURRENT = 3

# Shared in-memory job state — imported by the download router
download_jobs: dict[str, dict] = {}
_dl_queue: Queue = Queue()

ALLOWED_DOWNLOAD_DOMAINS = [
    "arxiv.org", "export.arxiv.org", "doaj.org", "openalex.org",
    "gutenberg.org", "archive.org", "plos.org", "ncbi.nlm.nih.gov",
    "biorxiv.org", "medrxiv.org", "hal.science", "persee.fr",
    "openedition.org", "erudit.org", "africarxiv.org", "ajol.info",
    "europepmc.org", "zenodo.org", "figshare.com", "osf.io",
    "frontiersin.org", "mdpi.com", "peerj.com", "hindawi.com",
    "intechopen.com", "f1000research.com",
]

GLOBAL_NORTH_DOMAINS = {
    "semanticscholar.org", "api.semanticscholar.org",
    "pubmed.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov",
    "api.crossref.org", "core.ac.uk", "api.base-search.net",
    "unpaywall.org", "api.unpaywall.org",
}


def active_domains() -> set:
    domains = set(ALLOWED_DOWNLOAD_DOMAINS)
    if AIConfig.is_north():
        domains |= GLOBAL_NORTH_DOMAINS
    return domains


def is_allowed_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        host   = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return any(host == d or host.endswith("." + d) for d in active_domains())
    except Exception:
        return False


def get_download_dir() -> Path:
    try:
        db  = get_db()
        val = settings_repo.get_setting(db, "download_dir")
        db.close()
        if val and val.strip():
            p = Path(val.strip())
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return DL_DIR


def enqueue_job(url: str, meta: dict | None = None) -> str:
    job_id = uuid4().hex
    download_jobs[job_id] = {
        "job_id":   job_id,
        "url":      url,
        "status":   "queued",
        "position": _dl_queue.qsize(),
        "progress": 0,
        "speed":    "",
        "eta":      "",
        "file":     "",
        "error":    "",
        "method":   "direct",
    }
    try:
        db = get_db()
        queue_repo.enqueue_job(db, job_id, url)
        db.close()
    except Exception:
        pass
    _dl_queue.put((job_id, {"url": url, "meta": meta or {}}))
    return job_id


def _run_download_job(job_id: str, req_data: dict):
    job    = download_jobs[job_id]
    job["status"] = "running"
    _db_update_job(job_id, status="running")

    url    = req_data["url"]
    dl_dir = get_download_dir()

    if not is_allowed_url(url):
        job["status"] = "error"
        job["error"]  = "URL not from an allowed open-access source."
        _db_update_job(job_id, status="error", error=job["error"])
        return

    try:
        parsed   = urllib.parse.urlparse(url)
        raw_name = Path(parsed.path).name or "document"
        # Keep the filename as-is only if its extension is a known document type;
        # otherwise append .pdf (handles arXiv IDs like "1706.03762" where
        # pathlib misreads ".03762" as a suffix).
        suffix = Path(raw_name).suffix.lower()
        filename = raw_name if suffix in _KNOWN_DOC_EXTS else raw_name + ".pdf"
        dest_path = dl_dir / filename
        headers   = {"User-Agent": "Mozilla/5.0"}
        req2      = urllib.request.Request(url, headers=headers)
        resp_ctype = ""
        with urllib.request.urlopen(req2, timeout=60) as resp:
            resp_ctype = resp.headers.get("Content-Type", "")
            total      = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = round(downloaded / total * 100, 1)
                        job["progress"] = pct
                        _db_update_job(job_id, progress=pct)

        # Reject HTML responses (login walls, error pages)
        if _is_html_content(dest_path):
            dest_path.unlink(missing_ok=True)
            job["status"] = "error"
            job["error"]  = "Server returned an HTML page — the resource may require login or is not directly downloadable."
            _db_update_job(job_id, status="error", error=job["error"])
            return

        # Rename to correct extension if needed
        correct_ext = _infer_ext(resp_ctype, dest_path)
        if correct_ext and dest_path.suffix.lower() != correct_ext:
            new_path = dest_path.with_suffix(correct_ext)
            dest_path.rename(new_path)
            dest_path = new_path
            filename  = dest_path.name

        job["status"]   = "done"
        job["progress"] = 100
        job["file"]     = filename
        _db_update_job(job_id, status="done", progress=100, filename=filename)

        source  = urllib.parse.urlparse(url).netloc or "Direct"
        size_kb = int(dest_path.stat().st_size / 1024)
        meta    = dict(req_data.get("meta", {}))

        # Extract title from PDF metadata when not supplied by caller
        if not meta.get("title") and dest_path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                reader    = PdfReader(str(dest_path))
                pdf_title = ((reader.metadata or {}).get("/Title") or "").strip()
                if pdf_title:
                    meta["title"] = pdf_title
            except Exception:
                pass

        try:
            db = get_db()
            history_repo.add_history_entry(
                db, url, meta.get("title") or filename, source, filename, size_kb,
                authors=meta.get("authors"), year=meta.get("year"),
                journal=meta.get("journal"), language=meta.get("language"),
            )
            db.close()
        except Exception:
            pass
    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e)
        _db_update_job(job_id, status="error", error=str(e))


def _db_update_job(job_id: str, **kwargs):
    try:
        db = get_db()
        queue_repo.update_job(db, job_id, **kwargs)
        db.close()
    except Exception:
        pass


def _worker():
    while True:
        job_id, req_data = _dl_queue.get()
        job = download_jobs.get(job_id)
        if job and job["status"] != "cancelled":
            _run_download_job(job_id, req_data)
        _dl_queue.task_done()


def load_jobs_from_db():
    """Restore queued/running jobs from DB into memory on startup."""
    try:
        db   = get_db()
        rows = queue_repo.load_interrupted_jobs(db)
        db.close()
        for row in rows:
            job_id, url = row["job_id"], row["url"]
            download_jobs[job_id] = {
                "job_id": job_id, "url": url, "status": "queued",
                "position": 0, "progress": 0, "speed": "", "eta": "",
                "file": "", "error": "", "method": "direct",
            }
            _dl_queue.put((job_id, {"url": url}))
    except Exception:
        pass


def start_workers():
    for _ in range(_MAX_CONCURRENT):
        threading.Thread(target=_worker, daemon=True).start()
