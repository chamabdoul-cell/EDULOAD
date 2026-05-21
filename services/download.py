"""Download queue service — job state, workers, URL validation, directory helper."""
import re as _re
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from queue import Queue
from uuid import uuid4

import requests as _requests

ARCHIVE_ORG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Referer": "https://archive.org/",
    "Connection": "keep-alive",
}

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


def _find_pdf_url_in_html(html_bytes: bytes, original_url: str) -> str | None:
    """Extract a direct PDF download URL from an HTML landing page.

    Handles source-specific rewrites first (arXiv, bioRxiv, medRxiv), then
    falls back to scanning all href attributes for PDF candidates.
    Returns None when no usable URL is found.
    """
    # ── Source-specific URL rewrites ─────────────────────────────────
    # arXiv abstract page → PDF: .../abs/ID  →  .../pdf/ID
    m = _re.search(r'arxiv\.org/abs/([^\s"\'?#>]+)', original_url, _re.I)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}"

    # bioRxiv / medRxiv: append .full.pdf when not already a PDF
    if any(d in original_url for d in ("biorxiv.org", "medrxiv.org")):
        if not original_url.lower().endswith(".pdf"):
            return original_url.rstrip("/") + ".full.pdf"

    # ── Generic: parse href attributes ───────────────────────────────
    try:
        text = html_bytes[:300_000].decode("utf-8", errors="replace")
        base_p = urllib.parse.urlparse(original_url)
        origin = f"{base_p.scheme}://{base_p.netloc}"

        def _abs(href: str) -> str | None:
            h = href.strip()
            if not h or h.startswith(("#", "javascript:", "mailto:")):
                return None
            if h.startswith("http"):    return h
            if h.startswith("//"):      return base_p.scheme + ":" + h
            if h.startswith("/"):       return origin + h
            return None

        hrefs = _re.findall(r'href=["\']([^"\']{4,300})["\']', text, _re.I)

        # Three passes, most-specific first
        for predicate in (
            lambda h: ".pdf" in h.lower(),
            lambda h: "/pdf/" in h.lower(),
            lambda h: "download" in h.lower() and "pdf" in h.lower(),
        ):
            for raw in hrefs:
                if not predicate(raw):
                    continue
                cand = _abs(raw)
                if cand and is_allowed_url(cand):
                    return cand
    except Exception:
        pass

    return None

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
    "youtube.com", "youtu.be",
]

_YTDLP_DOMAINS = {"youtube.com", "youtu.be"}

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
        "offset":   0,
        "resumed":  False,
    }
    try:
        db = get_db()
        queue_repo.enqueue_job(db, job_id, url)
        db.close()
    except Exception:
        pass
    _dl_queue.put((job_id, {"url": url, "meta": meta or {}}))
    return job_id


def _ytdlp_download(job: dict, job_id: str, url: str, dl_dir: Path) -> str:
    """Download via yt-dlp (YouTube etc). Returns saved filename."""
    import yt_dlp
    result: dict = {}

    def _hook(d: dict):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done  = d.get("downloaded_bytes", 0)
            pct   = round(done / total * 100, 1) if total else 0
            job["progress"] = pct
            job["speed"]    = d.get("_speed_str", "").strip()
            job["eta"]      = d.get("_eta_str", "").strip()
            _db_update_job(job_id, progress=pct)
        elif d["status"] == "finished":
            result["filepath"] = d.get("filename", "")

    ydl_opts = {
        "outtmpl":             str(dl_dir / "%(title)s.%(ext)s"),
        "progress_hooks":      [_hook],
        "quiet":               True,
        "no_warnings":         True,
        "format":              "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if not result.get("filepath"):
            result["filepath"] = ydl.prepare_filename(info)

    fp = Path(result["filepath"])
    if not fp.exists():
        candidates = list(dl_dir.glob(fp.stem + ".*"))
        fp = candidates[0] if candidates else fp
    return fp.name


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

    # Route YouTube URLs through yt-dlp
    try:
        _host = urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        _host = ""
    if any(_host == d or _host.endswith("." + d) for d in _YTDLP_DOMAINS):
        job["method"] = "ytdlp"
        try:
            filename = _ytdlp_download(job, job_id, url, dl_dir)
            job["status"] = "done"; job["progress"] = 100; job["file"] = filename
            _db_update_job(job_id, status="done", progress=100, filename=filename)
            dest = dl_dir / filename
            size_kb = int(dest.stat().st_size / 1024) if dest.exists() else 0
            meta = dict(req_data.get("meta", {}))
            try:
                db = get_db()
                history_repo.add_history_entry(
                    db, url, meta.get("title") or filename,
                    urllib.parse.urlparse(url).netloc or "YouTube",
                    filename, size_kb,
                    authors=meta.get("authors"), year=meta.get("year"),
                    journal=meta.get("journal"), language=meta.get("language"),
                )
                db.close()
            except Exception:
                pass
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e)
            _db_update_job(job_id, status="error", error=str(e))
        return

    try:
        parsed   = urllib.parse.urlparse(url)
        raw_name = Path(parsed.path).name or "document"
        # Keep the filename as-is only if its extension is a known document type;
        # otherwise append .pdf (handles arXiv IDs like "1706.03762" where
        # pathlib misreads ".03762" as a suffix).
        suffix = Path(raw_name).suffix.lower()
        filename  = raw_name if suffix in _KNOWN_DOC_EXTS else raw_name + ".pdf"
        dest_path = dl_dir / filename
        part_path = dl_dir / (filename + ".part")
        resp_ctype = ""

        # Check for a partial download to resume
        offset  = 0
        resumed = False
        if part_path.exists():
            offset  = part_path.stat().st_size
            resumed = True
            job["offset"]  = offset
            job["resumed"] = True

        if _host.endswith("archive.org"):
            # archive.org blocks the default Python UA — prime cookies by
            # visiting the item detail page before the download CDN.
            sess_headers = dict(ARCHIVE_ORG_HEADERS)
            if offset > 0:
                sess_headers["Range"] = f"bytes={offset}-"
            _sess = _requests.Session()
            _sess.headers.update(sess_headers)
            try:
                path_parts = urllib.parse.urlparse(url).path.strip("/").split("/")
                # path: download/{identifier}/{filename} → item detail page
                if len(path_parts) >= 2 and path_parts[0] == "download":
                    item_id = path_parts[1]
                    _sess.get(f"https://archive.org/details/{item_id}",
                              timeout=10, allow_redirects=True)
                else:
                    _sess.head("https://archive.org/", timeout=10, allow_redirects=True)
            except Exception:
                pass
            _resp = _sess.get(url, stream=True, timeout=60, allow_redirects=True)
            if _resp.status_code == 403:
                raise Exception(
                    "HTTP Error 403: archive.org blocked this download. "
                    "The item may require an Internet Archive account or borrowing. "
                    "Try opening it directly at archive.org."
                )
            _resp.raise_for_status()
            # If server ignores Range and returns 200, restart from scratch
            if _resp.status_code == 200 and offset > 0:
                offset = 0; resumed = False
                part_path.unlink(missing_ok=True)
                job["offset"] = 0; job["resumed"] = False
            resp_ctype  = _resp.headers.get("Content-Type", "")
            remaining   = int(_resp.headers.get("Content-Length", 0))
            total       = offset + remaining
            downloaded  = offset
            file_mode   = "ab" if offset > 0 else "wb"
            with open(part_path, file_mode) as f:
                for chunk in _resp.iter_content(65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = round(downloaded / total * 100, 1)
                        job["progress"] = pct
                        _db_update_job(job_id, progress=pct)
        else:
            req_headers = {"User-Agent": "Mozilla/5.0"}
            if offset > 0:
                req_headers["Range"] = f"bytes={offset}-"
            req2 = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req2, timeout=60) as resp:
                # If server returns 200 (ignores Range), restart from scratch
                if getattr(resp, "status", 200) == 200 and offset > 0:
                    offset = 0; resumed = False
                    part_path.unlink(missing_ok=True)
                    job["offset"] = 0; job["resumed"] = False
                resp_ctype = resp.headers.get("Content-Type", "")
                remaining  = int(resp.headers.get("Content-Length", 0))
                total      = offset + remaining
                downloaded = offset
                file_mode  = "ab" if offset > 0 else "wb"
                with open(part_path, file_mode) as f:
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

        # Reject HTML responses — but first try to extract a direct PDF link
        if _is_html_content(part_path):
            html_bytes = part_path.read_bytes()
            part_path.unlink(missing_ok=True)
            fallback = _find_pdf_url_in_html(html_bytes, url)
            if fallback and fallback != url:
                # One retry with the resolved URL — no range on a different URL
                try:
                    req3 = urllib.request.Request(fallback, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req3, timeout=60) as resp2:
                        resp_ctype = resp2.headers.get("Content-Type", "")
                        total      = int(resp2.headers.get("Content-Length", 0))
                        downloaded = 0
                        with open(part_path, "wb") as f:
                            while True:
                                chunk = resp2.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total:
                                    pct = round(downloaded / total * 100, 1)
                                    job["progress"] = pct
                                    _db_update_job(job_id, progress=pct)
                except Exception as retry_e:
                    job["status"] = "error"
                    job["error"]  = f"Could not follow landing page to PDF: {retry_e}"
                    _db_update_job(job_id, status="error", error=job["error"])
                    return
                if _is_html_content(part_path):
                    part_path.unlink(missing_ok=True)
                    job["status"] = "error"
                    job["error"]  = "Server returned an HTML page — the resource may require login or is not directly downloadable."
                    _db_update_job(job_id, status="error", error=job["error"])
                    return
            else:
                job["status"] = "error"
                job["error"]  = "Server returned an HTML page — the resource may require login or is not directly downloadable."
                _db_update_job(job_id, status="error", error=job["error"])
                return

        # Rename to correct extension if needed
        correct_ext = _infer_ext(resp_ctype, part_path)
        target_ext  = correct_ext or dest_path.suffix.lower()
        final_dest  = dest_path if not correct_ext or dest_path.suffix.lower() == target_ext \
                      else dest_path.with_suffix(correct_ext)
        # Atomically rename .part → final filename
        part_path.rename(final_dest)
        dest_path = final_dest
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
        # Leave the .part file intact so the next attempt can resume
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
                "offset": 0, "resumed": False,
            }
            _dl_queue.put((job_id, {"url": url}))
    except Exception:
        pass


def start_workers():
    for _ in range(_MAX_CONCURRENT):
        threading.Thread(target=_worker, daemon=True).start()
