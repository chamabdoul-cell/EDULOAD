"""
Scholara — Open-Access Research Platform
Run: python app.py
"""
import os, re, json, shutil, subprocess, threading, webbrowser, sqlite3, time
from uuid import uuid4
from pathlib import Path
from queue import Queue
import urllib.request, urllib.parse, urllib.error

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from core.ai_router import AISearchRouter
from core.fallback import fallback_routing
from config.settings import AIConfig

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
    url: str

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
    con.commit()
    con.close()

def _history_insert(url, title, source, filename, size_kb):
    try:
        con = _db()
        cur = con.execute(
            "INSERT INTO history (url,title,source,filename,size_kb) VALUES (?,?,?,?,?)",
            (url, title or filename, source, filename, size_kb))
        rowid = cur.lastrowid
        con.commit()
        con.close()
        return rowid
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Download Queue
# ══════════════════════════════════════════════════════════════════════════════
download_jobs: dict[str, dict] = {}
_dl_queue: Queue = Queue()
_MAX_CONCURRENT = 3


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
    url    = req_data["url"]
    dl_dir = _get_download_dir()

    if not _is_allowed_url(url):
        job["status"] = "error"
        job["error"]  = "URL not from an allowed open-access source."
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
                        job["progress"] = round(downloaded / total * 100, 1)
        job["status"]   = "done"
        job["progress"] = 100
        job["file"]     = filename
        source  = urllib.parse.urlparse(url).netloc or "Direct"
        size_kb = int(dest_path.stat().st_size / 1024)
        _history_insert(url, filename, source, filename, size_kb)
    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e)


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

def _check_ollama() -> bool:
    try:
        with urllib.request.urlopen(
            f"{AIConfig.OLLAMA_URL}/api/tags", timeout=2
        ) as r:
            return r.status == 200
    except Exception:
        return False

def _tools_status():
    return {
        "ffmpeg": _ffmpeg_available(),
        "pandoc": _pandoc_available(),
    }

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

def _enqueue_job(url: str) -> str:
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
    _dl_queue.put((job_id, {"url": url}))
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
    for _ in range(_MAX_CONCURRENT):
        threading.Thread(target=_worker, daemon=True).start()

    ollama_ok = _check_ollama()
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
def status():
    dl_dir = _get_download_dir()
    files  = []
    for f in sorted(dl_dir.iterdir()):
        if f.is_file():
            files.append({"name": f.name, "size": f.stat().st_size,
                          "ext": f.suffix.lower().lstrip(".")})
    ollama_ok = _check_ollama()
    return {
        "tools":               _tools_status(),
        "files":               files,
        "ollama_available":    ollama_ok,
        "ollama_model":        AIConfig.OLLAMA_MODEL,
        "deepseek_configured": bool(AIConfig.DEEPSEEK_API_KEY),
        "ai_backend":          AIConfig.BACKEND,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Download
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/download")
def download_url(req: DownloadRequest):
    url = req.url.strip()
    if not _is_allowed_url(url):
        raise HTTPException(
            403,
            "URL not from an allowed open-access source. "
            "Allowed: arxiv.org, doaj.org, archive.org, gutenberg.org, openalex.org, hal.science, and more."
        )
    job_id = _enqueue_job(url)
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
            pdf_id = link.group(1).split("/abs/")[-1] if link else ""
            results.append({
                "source":  "arXiv", "icon": "📄",
                "title":   (title.group(1).strip() if title else "—"),
                "authors": ", ".join(auth[:3]),
                "url":     link.group(1).strip() if link else "",
                "pdf_url": f"https://arxiv.org/pdf/{pdf_id}.pdf" if pdf_id else "",
                "snippet": (summ.group(1).strip()[:200] if summ else ""),
                "open_access": True,
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
            results.append({
                "source":  "Gutenberg", "icon": "📚",
                "title":   b.get("title", "—"),
                "authors": ", ".join(a["name"] for a in b.get("authors", [])),
                "url":     f"https://www.gutenberg.org/ebooks/{b['id']}",
                "pdf_url": pdf or txt,
                "snippet": f"Language: {', '.join(b.get('languages',[]))} | Subjects: {', '.join(b.get('subjects',[])[:3])}",
                "open_access": True,
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
            results.append({
                "source":  "DOAJ", "icon": "🔓",
                "title":   bib.get("title", "—"),
                "authors": ", ".join(a.get("name", "") for a in bib.get("author", [])[:3]),
                "url":     link,
                "pdf_url": link,
                "snippet": bib.get("abstract", "")[:200],
                "open_access": True,
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

@app.post("/api/search")
def search(req: SearchRequest):
    results = []
    src_map = {
        "arxiv":     _search_arxiv,
        "gutenberg": _search_gutenberg,
        "doaj":      _search_doaj,
        "openalex":  _search_openalex,
        "archive":   _search_archive,
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

    if not user_query:
        return {"error": "No query provided", "results": []}

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


def _search_source(source: str, query: str) -> list:
    src_map = {
        "arxiv":            _search_arxiv,
        "gutenberg":        _search_gutenberg,
        "doaj":             _search_doaj,
        "openalex":         _search_openalex,
        "internet_archive": _search_archive,
        "archive":          _search_archive,
    }
    fn = src_map.get(source)
    return fn(query) if fn else []


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
