"""
Scholara — Open-Access Research Platform
Run: python app.py
"""
import os, re, json, shutil, subprocess, threading, webbrowser, sqlite3, time
from uuid import uuid4
from pathlib import Path
from queue import Queue
import urllib.request, urllib.parse, urllib.error

from fastapi import FastAPI, HTTPException, Body, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import httpx

from core.ai_router import AISearchRouter
from core.fallback import fallback_routing
from config.settings import AIConfig

# ── Bilingual helpers ─────────────────────────────────────────────

def _get_lang(request: Request) -> str:
    return request.headers.get("Accept-Language", "en")[:2].lower()

_MESSAGES: dict[str, dict[str, str]] = {
    "download_not_allowed": {
        "en": "URL not from an allowed open-access source. Allowed: arxiv.org, doaj.org, archive.org, hal.science, and others.",
        "fr": "Cette URL ne provient pas d'une source en libre accès autorisée. Autorisées : arxiv.org, doaj.org, archive.org, hal.science, et autres.",
    },
    "no_query": {
        "en": "No query provided.",
        "fr": "Aucune requête fournie.",
    },
    "file_not_found": {
        "en": "File not found",
        "fr": "Fichier introuvable",
    },
}

def _msg(key: str, lang: str) -> str:
    return _MESSAGES.get(key, {}).get(lang) or _MESSAGES.get(key, {}).get("en") or key

BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DL_DIR     = BASE_DIR / "downloads"
DB_PATH    = BASE_DIR / "scholara.db"
DL_DIR.mkdir(exist_ok=True)

ALLOWED_DOWNLOAD_DOMAINS = [
    "arxiv.org", "export.arxiv.org", "doaj.org", "openalex.org",
    "gutenberg.org", "archive.org", "plos.org", "ncbi.nlm.nih.gov",
    "biorxiv.org", "medrxiv.org", "hal.science", "persee.fr",
    "openedition.org", "erudit.org", "africarxiv.org", "ajol.info",
]

app = FastAPI(title="Scholara")
app.mount("/static",    StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/downloads", StaticFiles(directory=str(DL_DIR)),     name="downloads")


# ══════════════════════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════════════════════
class DownloadRequest(BaseModel):
    url:      str
    title:    str = ""
    authors:  list[str] = []
    year:     int | None = None
    journal:  str = ""
    language: str = ""

class SearchRequest(BaseModel):
    query:   str
    sources: list[str] = ["arxiv", "gutenberg", "doaj", "openalex", "archive"]
    limit:   int = 10

class ConvertRequest(BaseModel):
    filename: str
    to_fmt:   str

class CollectionCreate(BaseModel):
    name:        str
    description: str = ""

class CollectionAddItem(BaseModel):
    history_id: int
    position:   int = 0

class TagRequest(BaseModel):
    tags: str


# ══════════════════════════════════════════════════════════════════════════════
# Database
# ══════════════════════════════════════════════════════════════════════════════
def _db():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con

def _init_db():
    con = _db()
    con.execute("""CREATE TABLE IF NOT EXISTS history (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        ts       TEXT DEFAULT (datetime('now')),
        url      TEXT,
        title    TEXT,
        source   TEXT,
        filename TEXT,
        size_kb  INTEGER,
        tags     TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS collections (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        description TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS collection_items (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
        history_id    INTEGER REFERENCES history(id)    ON DELETE CASCADE,
        position      INTEGER DEFAULT 0
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS download_queue (
        job_id          TEXT PRIMARY KEY,
        url             TEXT NOT NULL,
        status          TEXT DEFAULT 'queued',
        progress        REAL DEFAULT 0,
        error           TEXT,
        result_filename TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    )""")
    con.commit()

    # Migrate history table — add citation columns if missing
    existing = {row[1] for row in con.execute("PRAGMA table_info(history)")}
    for col, typedef in [
        ("authors",  "TEXT"),
        ("year",     "INTEGER"),
        ("journal",  "TEXT"),
        ("language", "TEXT"),
    ]:
        if col not in existing:
            con.execute(f"ALTER TABLE history ADD COLUMN {col} {typedef}")
    con.commit()
    con.close()

def _history_insert(url, title, source, filename, size_kb,
                    authors=None, year=None, journal=None, language=None):
    try:
        authors_str = json.dumps(authors) if authors else None
        con = _db()
        cur = con.execute(
            """INSERT INTO history (url,title,source,filename,size_kb,authors,year,journal,language)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (url, title or filename, source, filename, size_kb,
             authors_str, year, journal, language))
        rowid = cur.lastrowid
        con.commit()
        con.close()
        return rowid
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Persistent Download Queue
# ══════════════════════════════════════════════════════════════════════════════
download_jobs: dict[str, dict] = {}
_dl_queue: Queue = Queue()
_MAX_CONCURRENT = 3


def _enqueue_job_db(job_id: str, url: str):
    try:
        con = _db()
        con.execute("INSERT OR IGNORE INTO download_queue (job_id, url) VALUES (?, ?)", (job_id, url))
        con.commit()
        con.close()
    except Exception:
        pass


def _update_job_db(job_id: str, status: str = None, progress: float = None,
                   error: str = None, filename: str = None):
    try:
        updates = ["updated_at = datetime('now')"]
        params  = []
        if status   is not None: updates.append("status = ?");          params.append(status)
        if progress is not None: updates.append("progress = ?");        params.append(progress)
        if error    is not None: updates.append("error = ?");           params.append(error)
        if filename is not None: updates.append("result_filename = ?"); params.append(filename)
        params.append(job_id)
        con = _db()
        con.execute(f"UPDATE download_queue SET {', '.join(updates)} WHERE job_id = ?", params)
        con.commit()
        con.close()
    except Exception:
        pass


def _load_jobs_from_db():
    """On startup: restore queued/running jobs into memory and re-enqueue them."""
    try:
        con = _db()
        rows = con.execute(
            "SELECT job_id, url FROM download_queue WHERE status IN ('queued','running')"
        ).fetchall()
        con.execute(
            "UPDATE download_queue SET status='queued' WHERE status='running'"
        )
        con.commit()
        con.close()
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


def _is_allowed_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return any(host == d or host.endswith("." + d) for d in ALLOWED_DOWNLOAD_DOMAINS)
    except Exception:
        return False


def _run_download_job(job_id: str, req_data: dict):
    job = download_jobs[job_id]
    job["status"] = "running"
    _update_job_db(job_id, status="running")
    url    = req_data["url"]
    dl_dir = _get_download_dir()

    if not _is_allowed_url(url):
        job["status"] = "error"
        job["error"]  = "URL not from an allowed open-access source."
        _update_job_db(job_id, status="error", error=job["error"])
        return

    try:
        parsed   = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or "document"
        if not Path(filename).suffix:
            filename += ".pdf"
        dest_path = dl_dir / filename
        headers = {"User-Agent": "Mozilla/5.0"}
        req2 = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req2, timeout=60) as resp:
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
                        _update_job_db(job_id, progress=pct)
        job["status"]   = "done"
        job["progress"] = 100
        job["file"]     = filename
        _update_job_db(job_id, status="done", progress=100, filename=filename)

        source  = urllib.parse.urlparse(url).netloc or "Direct"
        size_kb = int(dest_path.stat().st_size / 1024)
        meta = req_data.get("meta", {})
        _history_insert(
            url, meta.get("title") or filename, source, filename, size_kb,
            authors=meta.get("authors"), year=meta.get("year"),
            journal=meta.get("journal"), language=meta.get("language"),
        )
    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e)
        _update_job_db(job_id, status="error", error=str(e))


def _worker():
    while True:
        job_id, req_data = _dl_queue.get()
        job = download_jobs.get(job_id)
        if job and job["status"] != "cancelled":
            _run_download_job(job_id, req_data)
        _dl_queue.task_done()


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

def _ffmpeg_available():
    return shutil.which("ffmpeg") is not None

def _ffmpeg_exe() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"

def _pandoc_available():
    return shutil.which("pandoc") is not None

def _get_download_dir() -> Path:
    try:
        con = sqlite3.connect(str(DB_PATH))
        row = con.execute("SELECT value FROM settings WHERE key='download_dir'").fetchone()
        con.close()
        if row and row[0] and row[0].strip():
            p = Path(row[0].strip())
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass
    return DL_DIR

def _enqueue_job(url: str, meta: dict | None = None) -> str:
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
    _enqueue_job_db(job_id, url)
    _dl_queue.put((job_id, {"url": url, "meta": meta or {}}))
    return job_id


# ── Document conversion helpers (pure-Python, no pandoc) ─────────────────────

def _doc_to_html(src: Path) -> str:
    ext = src.suffix.lower()
    if ext in (".html", ".htm"):
        return src.read_text(encoding="utf-8")
    if ext == ".md":
        try:
            import markdown as md_lib
            return md_lib.markdown(src.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
        except ImportError:
            raise HTTPException(400, "markdown not installed — run: pip install markdown")
    if ext == ".txt":
        import html as html_lib
        return f"<pre>{html_lib.escape(src.read_text(encoding='utf-8'))}</pre>"
    if ext == ".docx":
        try:
            import mammoth
            return mammoth.convert_to_html(open(str(src), "rb")).value
        except ImportError:
            raise HTTPException(400, "mammoth not installed — run: pip install mammoth")
    raise HTTPException(400, f"Cannot read {ext} as source document")


def _html_to_dest(html_str: str, dest: Path):
    to = dest.suffix.lower()
    if to in (".html", ".htm"):
        dest.write_text(html_str, encoding="utf-8")
        return
    if to in (".txt", ".md"):
        try:
            import html2text as h2t
        except ImportError:
            raise HTTPException(400, "html2text not installed — run: pip install html2text")
        h = h2t.HTML2Text()
        h.body_width = 0
        h.ignore_links = (to == ".txt")
        dest.write_text(h.handle(html_str), encoding="utf-8")
        return
    if to == ".pdf":
        try:
            from xhtml2pdf import pisa
        except ImportError:
            raise HTTPException(400, "xhtml2pdf not installed — run: pip install xhtml2pdf")
        with open(dest, "wb") as f:
            res = pisa.CreatePDF(html_str, dest=f)
        if res.err:
            raise HTTPException(500, "xhtml2pdf: PDF creation failed")
        return
    if to == ".docx":
        try:
            from docx import Document
            import html2text as h2t
        except ImportError:
            raise HTTPException(400, "python-docx / html2text not installed")
        h = h2t.HTML2Text()
        h.body_width = 0
        text = h.handle(html_str)
        doc = Document()
        for para in text.split("\n\n"):
            p = para.strip()
            if p:
                doc.add_paragraph(p)
        doc.save(str(dest))
        return
    raise HTTPException(400, f"Unsupported output format: {to}")


# ══════════════════════════════════════════════════════════════════════════════
# Startup
# ══════════════════════════════════════════════════════════════════════════════
def _generate_pwa_icons():
    import struct, zlib
    def _png(size):
        bg = (0xC8, 0x43, 0x0B)
        fg = (0xFF, 0xFF, 0xFF)
        raw = []
        for y in range(size):
            row = [0]
            cx, cy, r = size // 2, size // 2, size * 0.28
            for x in range(size):
                dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                row += list(fg if dist < r else bg)
            raw.append(bytes(row))
        def chunk(tag, data):
            c = zlib.crc32(tag + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)
        ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
        idat = zlib.compress(b"".join(raw))
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    for sz, name in [(192, "icon-192.png"), (512, "icon-512.png")]:
        p = STATIC_DIR / name
        if not p.exists():
            p.write_bytes(_png(sz))


@app.on_event("startup")
def startup_event():
    _init_db()
    _generate_pwa_icons()
    _load_jobs_from_db()
    for _ in range(_MAX_CONCURRENT):
        threading.Thread(target=_worker, daemon=True).start()

    # Sync Ollama check for startup banner
    ollama_ok = False
    try:
        with urllib.request.urlopen(f"{AIConfig.OLLAMA_URL}/api/tags", timeout=2) as r:
            ollama_ok = r.status == 200
    except Exception:
        pass

    print("\n=== Scholara Status ===")
    print(f"  {'[OK]' if ollama_ok else '[--]'} Ollama ({AIConfig.OLLAMA_MODEL})")
    print(f"  {'[OK]' if AIConfig.DEEPSEEK_API_KEY else '[--]'} DeepSeek API")
    print(f"  {'[OK]' if _ffmpeg_available() else '[--]'} ffmpeg (conversion)")
    print("  [OK] Direct HTTP: always available")
    print("======================\n")


# ══════════════════════════════════════════════════════════════════════════════
# Routes – System
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/api/status")
async def status():
    dl_dir = _get_download_dir()
    files  = []
    for f in sorted(dl_dir.iterdir()):
        if f.is_file():
            files.append({"name": f.name, "size": f.stat().st_size,
                          "ext": f.suffix.lower().lstrip(".")})

    ollama_available = False
    ollama_model     = AIConfig.OLLAMA_MODEL
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{AIConfig.OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                ollama_available = True
                models = resp.json().get("models", [])
                if models:
                    ollama_model = models[0].get("name", AIConfig.OLLAMA_MODEL)
    except Exception:
        pass

    return {
        "tools":               {"ffmpeg": _ffmpeg_available(), "pandoc": _pandoc_available()},
        "files":               files,
        "ollama_available":    ollama_available,
        "ollama_model":        ollama_model,
        "ollama_url":          AIConfig.OLLAMA_URL,
        "deepseek_configured": bool(AIConfig.DEEPSEEK_API_KEY),
        "ai_backend":          AIConfig.BACKEND,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Download
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/download")
def download_url(req: DownloadRequest, request: Request):
    url  = req.url.strip()
    lang = _get_lang(request)
    if not _is_allowed_url(url):
        raise HTTPException(403, _msg("download_not_allowed", lang))
    meta = {
        "title":    req.title,
        "authors":  req.authors,
        "year":     req.year,
        "journal":  req.journal,
        "language": req.language,
    }
    job_id = _enqueue_job(url, meta=meta)
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/progress/{job_id}")
def progress_sse(job_id: str):
    def gen():
        while True:
            job = download_jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'status':'not_found'})}\n\n"
                break
            yield f"data: {json.dumps(job)}\n\n"
            if job["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})

@app.get("/api/queue")
def get_queue():
    jobs = list(download_jobs.values())
    queued = [j for j in jobs if j["status"] == "queued"]
    for i, j in enumerate(queued):
        j["position"] = i
    return jobs

@app.delete("/api/queue/{job_id}")
def cancel_job(job_id: str):
    job = download_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "queued":
        raise HTTPException(400, "Can only cancel queued jobs")
    job["status"] = "cancelled"
    _update_job_db(job_id, status="cancelled")
    return {"status": "cancelled"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Search
# ══════════════════════════════════════════════════════════════════════════════
def _search_arxiv(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&max_results={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            xml = r.read().decode()
        entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
        results = []
        for e in entries:
            title  = re.search(r'<title>(.*?)</title>', e, re.DOTALL)
            link   = re.search(r'<id>(.*?)</id>', e)
            summ   = re.search(r'<summary>(.*?)</summary>', e, re.DOTALL)
            auth   = re.findall(r'<name>(.*?)</name>', e)
            pub    = re.search(r'<published>(.*?)</published>', e)
            pdf_id = link.group(1).split("/abs/")[-1] if link else ""
            year   = int(pub.group(1)[:4]) if pub else None
            results.append({
                "source":  "arXiv", "icon": "📄",
                "title":   (title.group(1).strip() if title else "—"),
                "authors": ", ".join(auth[:3]),
                "url":     link.group(1).strip() if link else "",
                "pdf_url": f"https://arxiv.org/pdf/{pdf_id}.pdf" if pdf_id else "",
                "snippet": (summ.group(1).strip()[:200] if summ else ""),
                "open_access": True,
                "year": year, "language": "en",
            })
        return results
    except Exception as ex:
        return [{"source":"arXiv","icon":"📄","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_gutenberg(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://gutendex.com/books/?search={q}&languages=en,fr"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for b in data.get("results", [])[:limit]:
            fmts = b.get("formats", {})
            pdf  = fmts.get("application/pdf", "")
            txt  = fmts.get("text/plain; charset=utf-8", fmts.get("text/plain", ""))
            langs = b.get("languages", [])
            results.append({
                "source":  "Gutenberg", "icon": "📚",
                "title":   b.get("title", "—"),
                "authors": ", ".join(a["name"] for a in b.get("authors", [])),
                "url":     f"https://www.gutenberg.org/ebooks/{b['id']}",
                "pdf_url": pdf or txt,
                "snippet": f"Language: {', '.join(langs)} | Subjects: {', '.join(b.get('subjects',[])[:3])}",
                "open_access": True,
                "language": langs[0] if langs else None,
            })
        return results
    except Exception as ex:
        return [{"source":"Gutenberg","icon":"📚","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_doaj(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://doaj.org/api/search/articles/{q}?pageSize={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for art in data.get("results", [])[:limit]:
            bib  = art.get("bibjson", {})
            link = next((l["url"] for l in bib.get("link", []) if l.get("type") == "fulltext"), "")
            year = bib.get("year")
            results.append({
                "source":  "DOAJ", "icon": "🔓",
                "title":   bib.get("title", "—"),
                "authors": ", ".join(a.get("name", "") for a in bib.get("author", [])[:3]),
                "url":     link,
                "pdf_url": link,
                "snippet": bib.get("abstract", "")[:200],
                "open_access": True,
                "year": int(year) if year else None,
                "journal": bib.get("journal", {}).get("title", ""),
            })
        return results
    except Exception as ex:
        return [{"source":"DOAJ","icon":"🔓","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_openalex(query, limit=5):
    q   = urllib.parse.quote(query)
    url = (f"https://api.openalex.org/works?search={q}"
           f"&filter=is_oa:true&per-page={limit}&mailto=scholara@open.edu")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for w in data.get("results", []):
            pdf = w.get("open_access", {}).get("oa_url", "") or ""
            doi = w.get("doi", "")
            results.append({
                "source":  "OpenAlex", "icon": "🔬",
                "title":   w.get("title", "—"),
                "authors": ", ".join(a["author"]["display_name"]
                                     for a in w.get("authorships", [])[:3]),
                "url":     doi or pdf,
                "pdf_url": pdf,
                "snippet": f"Cited by {w.get('cited_by_count',0)} | {w.get('publication_year','')}",
                "open_access": True,
                "year": w.get("publication_year"),
            })
        return results
    except Exception as ex:
        return [{"source":"OpenAlex","icon":"🔬","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_archive(query, limit=5):
    q   = urllib.parse.quote(query)
    url = (f"https://archive.org/advancedsearch.php"
           f"?q={q}+AND+mediatype:texts"
           f"&fl[]=identifier,title,creator,description,mediatype"
           f"&rows={limit}&output=json")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results  = []
        for doc in data.get("response", {}).get("docs", []):
            idf = doc.get("identifier", "")
            results.append({
                "source":  "Archive.org", "icon": "📚",
                "title":   doc.get("title", "—"),
                "authors": doc.get("creator", ""),
                "url":     f"https://archive.org/details/{idf}",
                "pdf_url": f"https://archive.org/download/{idf}/{idf}.pdf",
                "snippet": (doc.get("description", "") or "")[:200],
                "open_access": True,
            })
        return results
    except Exception as ex:
        return [{"source":"Archive.org","icon":"📚","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_hal(query, limit=5):
    q   = urllib.parse.quote(query)
    fl  = "title_s,abstract_s,author_s,halId_s,uri_s,publicationDate_tdate,journalTitle_s"
    url = (f"https://api.archives-ouvertes.fr/search/"
           f"?q={q}&fl={fl}&rows={limit}&wt=json")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for doc in data.get("response", {}).get("docs", []):
            hal_id  = (doc.get("halId_s") or [""])[0] if isinstance(doc.get("halId_s"), list) else doc.get("halId_s", "")
            uri_val = doc.get("uri_s", "")
            uri     = uri_val[0] if isinstance(uri_val, list) else uri_val
            pdf_url = uri if uri.endswith(".pdf") else f"https://hal.science/{hal_id}/document" if hal_id else ""
            title_v = doc.get("title_s", ["—"])
            title   = title_v[0] if isinstance(title_v, list) else title_v
            abst_v  = doc.get("abstract_s", [""])
            snippet = (abst_v[0] if isinstance(abst_v, list) else abst_v)[:300]
            authors = doc.get("author_s", [])
            pub     = doc.get("publicationDate_tdate", "")
            year    = int(pub[:4]) if pub and len(pub) >= 4 else None
            journal_v = doc.get("journalTitle_s", "")
            journal   = journal_v[0] if isinstance(journal_v, list) else journal_v
            results.append({
                "source":  "HAL", "icon": "🏛️",
                "title":   title,
                "authors": ", ".join(authors[:3]) if isinstance(authors, list) else authors,
                "url":     uri or f"https://hal.science/{hal_id}",
                "pdf_url": pdf_url,
                "snippet": snippet,
                "open_access": True,
                "year": year, "journal": journal, "language": "fr",
            })
        return results
    except Exception as ex:
        return [{"source":"HAL","icon":"🏛️","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_persee(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://www.persee.fr/search/list?q={q}&rows={limit}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for item in (data.get("items") or data.get("results") or [])[:limit]:
            results.append({
                "source":  "Persée", "icon": "📰",
                "title":   item.get("title", "—"),
                "authors": item.get("author", ""),
                "url":     item.get("link", ""),
                "pdf_url": item.get("pdfLink", ""),
                "snippet": (item.get("abstract", "") or "")[:300],
                "open_access": True,
                "language": "fr",
            })
        if not results:
            raise ValueError("empty")
        return results
    except Exception:
        # Fallback: HTML scraping with BeautifulSoup
        try:
            from bs4 import BeautifulSoup
            q2  = urllib.parse.quote(query)
            url2 = f"https://www.persee.fr/search?q={q2}"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=10) as r:
                html = r.read().decode("utf-8", errors="replace")
            soup    = BeautifulSoup(html, "html.parser")
            results = []
            for card in soup.select(".result-item, .search-result, article")[:limit]:
                t_el = card.find(["h2", "h3", "a"])
                link_el = card.find("a", href=True)
                snip_el = card.find("p")
                title = t_el.get_text(strip=True) if t_el else "—"
                link  = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.persee.fr" + link
                results.append({
                    "source": "Persée", "icon": "📰",
                    "title": title, "authors": "", "url": link, "pdf_url": "",
                    "snippet": snip_el.get_text(strip=True)[:300] if snip_el else "",
                    "open_access": True, "language": "fr",
                })
            return results or [{"source":"Persée","icon":"📰","title":"No results","url":"","pdf_url":"","snippet":"","authors":""}]
        except Exception as ex2:
            return [{"source":"Persée","icon":"📰","title":f"Error: {ex2}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_openedition(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://api.openedition.org/?q={q}&format=json&rows={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        docs = data.get("docs") or data.get("items") or data.get("results") or []
        for doc in docs[:limit]:
            results.append({
                "source":  "OpenEdition", "icon": "📖",
                "title":   doc.get("title", "—"),
                "authors": doc.get("creator", doc.get("author", "")),
                "url":     doc.get("identifier", doc.get("url", "")),
                "pdf_url": "",
                "snippet": (doc.get("description", "") or "")[:300],
                "open_access": True,
                "journal": doc.get("source", ""),
                "language": "fr",
            })
        return results or [{"source":"OpenEdition","icon":"📖","title":"No results","url":"","pdf_url":"","snippet":"","authors":""}]
    except Exception as ex:
        return [{"source":"OpenEdition","icon":"📖","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_erudit(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://apropos.erudit.org/api/items?q={q}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        for item in items[:limit]:
            author = item.get("author", "")
            results.append({
                "source":  "Érudit", "icon": "📚",
                "title":   item.get("title", "—"),
                "authors": author if isinstance(author, str) else ", ".join(author[:3]),
                "url":     item.get("url", ""),
                "pdf_url": item.get("pdf_url", ""),
                "snippet": (item.get("abstract", "") or "")[:300],
                "open_access": True,
                "language": "fr",
            })
        return results or [{"source":"Érudit","icon":"📚","title":"No results","url":"","pdf_url":"","snippet":"","authors":""}]
    except Exception as ex:
        return [{"source":"Érudit","icon":"📚","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]


@app.post("/api/search")
def search(req: SearchRequest):
    results = []
    src_map = {
        "arxiv":       _search_arxiv,
        "gutenberg":   _search_gutenberg,
        "doaj":        _search_doaj,
        "openalex":    _search_openalex,
        "archive":     _search_archive,
        "hal":         _search_hal,
        "persee":      _search_persee,
        "openedition": _search_openedition,
        "erudit":      _search_erudit,
    }
    per = req.limit // max(len(req.sources), 1) + 2
    for src in req.sources:
        fn = src_map.get(src)
        if fn:
            results.extend(fn(req.query, per))
    return {"results": results[:req.limit * 2]}


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Natural Language → Search
# ══════════════════════════════════════════════════════════════════════════════
_ai_router: AISearchRouter | None = None

def _get_ai_router() -> AISearchRouter:
    global _ai_router
    if _ai_router is None:
        _ai_router = AISearchRouter()
    return _ai_router


@app.post("/api/nl_search")
async def nl_search(request: Request):
    body = await request.json()
    user_query = body.get("text", body.get("query", ""))
    lang = _get_lang(request)

    if not user_query:
        return {"error": _msg("no_query", lang), "results": []}

    router = _get_ai_router()
    routing = await router.route(user_query)

    if not routing.get("sources"):
        return {"routing": routing, "results": [], "message": "No sources selected."}

    results = []
    for source in routing["sources"]:
        query = routing.get("queries", {}).get(source, user_query)
        results.extend(_search_source(source, query))

    return {
        "success":    True,
        "routing":    routing,
        "results":    results[:50],
        "ai_backend": AIConfig.BACKEND,
    }


def _search_source(source: str, query: str, limit: int = 5) -> list:
    src_map = {
        "arxiv":            _search_arxiv,
        "gutenberg":        _search_gutenberg,
        "doaj":             _search_doaj,
        "openalex":         _search_openalex,
        "internet_archive": _search_archive,
        "archive":          _search_archive,
        "hal":              _search_hal,
        "persee":           _search_persee,
        "openedition":      _search_openedition,
        "erudit":           _search_erudit,
    }
    fn = src_map.get(source)
    return fn(query, limit) if fn else []


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Citation Export
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/cite/{history_id}")
def cite_document(history_id: int, format: str = "bibtex"):
    con = _db()
    row = con.execute(
        "SELECT title, url, authors, year, journal, source FROM history WHERE id = ?",
        (history_id,)
    ).fetchone()
    con.close()

    if not row:
        raise HTTPException(404, "Document not found")

    title    = row["title"] or "Untitled"
    url      = row["url"] or ""
    authors  = json.loads(row["authors"]) if row["authors"] else []
    year     = row["year"]
    journal  = row["journal"] or row["source"] or ""
    year_str = str(year) if year else "n.d."

    if format == "bibtex":
        content = (
            f"@article{{scholara:{history_id},\n"
            f"  title   = {{{title}}},\n"
            f"  author  = {{{' and '.join(authors) if authors else 'Unknown'}}},\n"
            f"  year    = {{{year_str}}},\n"
            f"  journal = {{{journal}}},\n"
            f"  url     = {{{url}}}\n"
            f"}}"
        )
        return Response(content=content, media_type="text/plain",
                        headers={"Content-Disposition": f"attachment; filename=scholara_{history_id}.bib"})

    elif format == "ris":
        lines = ["TY  - JOUR", f"TI  - {title}"]
        for a in authors:
            lines.append(f"AU  - {a}")
        if year:
            lines.append(f"PY  - {year}")
        if journal:
            lines.append(f"JF  - {journal}")
        if url:
            lines.append(f"UR  - {url}")
        lines.append("ER  -")
        content = "\n".join(lines)
        return Response(content=content, media_type="application/x-research-info-systems",
                        headers={"Content-Disposition": f"attachment; filename=scholara_{history_id}.ris"})

    elif format == "apa":
        author_str = ", ".join(authors) if authors else "Unknown"
        content = f"{author_str} ({year_str}). {title}. {journal}. {url}"
        return Response(content=content, media_type="text/plain")

    else:
        raise HTTPException(400, f"Unknown format '{format}'. Use bibtex, ris, or apa.")


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Conversion
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/convert")
def convert(req: ConvertRequest):
    dl_dir = _get_download_dir()
    src    = dl_dir / req.filename
    if not src.exists():
        raise HTTPException(404, f"File not found: {req.filename}")

    ext  = src.suffix.lower()
    to   = req.to_fmt.lower().lstrip(".")
    dest = dl_dir / f"{src.stem}_converted.{to}"

    VIDEO_EXTS   = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv"}
    AUDIO_CODECS = {"wav": "pcm_s16le", "aac": "aac", "ogg": "libvorbis", "flac": "flac"}
    DOC_EXTS     = {".docx", ".html", ".htm", ".md", ".txt"}

    if ext in VIDEO_EXTS and to in ("mp3", "wav", "aac", "ogg", "flac"):
        if not _ffmpeg_available():
            raise HTTPException(400, "ffmpeg not available — install ffmpeg")
        codec = "libmp3lame" if to == "mp3" else AUDIO_CODECS[to]
        extra = ["-ab", "192k"] if to == "mp3" else []
        r = _run([_ffmpeg_exe(), "-y", "-i", str(src), "-vn", "-acodec", codec] + extra + [str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    elif ext in VIDEO_EXTS and to in ("mp4", "webm", "avi", "mkv", "mov"):
        if not _ffmpeg_available():
            raise HTTPException(400, "ffmpeg not available — install ffmpeg")
        r = _run([_ffmpeg_exe(), "-y", "-i", str(src), str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    elif ext == ".pdf" and to == "docx":
        try:
            from pdf2docx import Converter
        except ImportError:
            raise HTTPException(400, "pdf2docx not installed — run: pip install pdf2docx")
        cv = Converter(str(src))
        cv.convert(str(dest))
        cv.close()

    elif ext == ".pdf" and to in ("txt", "html"):
        try:
            import pypdf
            import html as html_lib
        except ImportError:
            raise HTTPException(400, "pypdf not installed — run: pip install pypdf")
        reader = pypdf.PdfReader(str(src))
        text   = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if to == "txt":
            dest.write_text(text, encoding="utf-8")
        else:
            dest.write_text(f"<pre>{html_lib.escape(text)}</pre>", encoding="utf-8")

    elif ext in DOC_EXTS and to in ("html", "htm", "txt", "md", "pdf", "docx"):
        html_str = _doc_to_html(src)
        _html_to_dest(html_str, dest)

    else:
        raise HTTPException(400,
            f"Conversion {ext}→.{to} not supported. "
            "Supported: video→mp3/wav, pdf→docx/txt/html, docx/md/html/txt↔pdf/docx/md/html/txt")

    return {"status": "ok", "file": dest.name}


# ══════════════════════════════════════════════════════════════════════════════
# Routes – File serving
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/file/{filename}")
def get_file(filename: str):
    f = _get_download_dir() / filename
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(str(f))

@app.delete("/api/file/{filename}")
def delete_file(filename: str):
    f = _get_download_dir() / filename
    if f.exists():
        f.unlink()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes – History
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/history")
def get_history(limit: int = 50):
    con  = _db()
    rows = con.execute(
        "SELECT * FROM history ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/history/{id}/tag")
def tag_history(id: int, req: TagRequest):
    con = _db()
    con.execute("UPDATE history SET tags=? WHERE id=?", (req.tags, id))
    con.commit()
    con.close()
    return {"status": "ok"}

@app.delete("/api/history/{id}")
def delete_history(id: int):
    con = _db()
    con.execute("DELETE FROM history WHERE id=?", (id,))
    con.commit()
    con.close()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Settings
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/settings")
def get_settings():
    con  = _db()
    rows = con.execute("SELECT key, value FROM settings").fetchall()
    con.close()
    return {r["key"]: r["value"] for r in rows}

@app.post("/api/settings")
def save_settings(data: dict = Body(...)):
    con = _db()
    for k, v in data.items():
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
    con.commit()
    con.close()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Collections
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/collections")
def list_collections():
    con  = _db()
    rows = con.execute("SELECT * FROM collections ORDER BY created_at DESC").fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/collections")
def create_collection(req: CollectionCreate):
    con = _db()
    cur = con.execute("INSERT INTO collections (name,description) VALUES (?,?)",
                      (req.name, req.description))
    rowid = cur.lastrowid
    con.commit()
    con.close()
    return {"id": rowid, "status": "ok"}

@app.get("/api/collections/{id}")
def get_collection(id: int):
    con = _db()
    col = con.execute("SELECT * FROM collections WHERE id=?", (id,)).fetchone()
    if not col:
        con.close()
        raise HTTPException(404, "Collection not found")
    items = con.execute("""
        SELECT ci.id as item_id, ci.position, h.*
        FROM collection_items ci
        JOIN history h ON h.id = ci.history_id
        WHERE ci.collection_id=?
        ORDER BY ci.position
    """, (id,)).fetchall()
    con.close()
    return {"collection": dict(col), "items": [dict(i) for i in items]}

@app.post("/api/collections/{id}/items")
def add_to_collection(id: int, req: CollectionAddItem):
    con = _db()
    col = con.execute("SELECT id FROM collections WHERE id=?", (id,)).fetchone()
    if not col:
        con.close()
        raise HTTPException(404, "Collection not found")
    cur = con.execute(
        "INSERT INTO collection_items (collection_id,history_id,position) VALUES (?,?,?)",
        (id, req.history_id, req.position))
    rowid = cur.lastrowid
    con.commit()
    con.close()
    return {"id": rowid, "status": "ok"}

@app.delete("/api/collections/{id}/items/{item_id}")
def remove_from_collection(id: int, item_id: int):
    con = _db()
    con.execute("DELETE FROM collection_items WHERE id=? AND collection_id=?", (item_id, id))
    con.commit()
    con.close()
    return {"status": "ok"}

@app.delete("/api/collections/{id}")
def delete_collection(id: int):
    con = _db()
    con.execute("DELETE FROM collection_items WHERE collection_id=?", (id,))
    con.execute("DELETE FROM collections WHERE id=?", (id,))
    con.commit()
    con.close()
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# Launch
# ══════════════════════════════════════════════════════════════════════════════
def _open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:7860")

if __name__ == "__main__":
    print("=" * 54)
    print("  Scholara — Open Knowledge, Everywhere")
    print("  http://127.0.0.1:7860")
    print("=" * 54)
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app:app", host="127.0.0.1", port=7860, reload=False)
