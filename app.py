"""
EduLoad — Educational Resource Downloader & Viewer
Run: python app.py
"""
import os, re, json, shutil, subprocess, threading, webbrowser, sqlite3, time
from uuid import uuid4
from pathlib import Path
from queue import Queue
from typing import Optional
import urllib.request, urllib.parse, urllib.error

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from core.claude_router import ClaudeSearchRouter
from core.downloader import downloader as _downloader

BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DL_DIR     = BASE_DIR / "downloads"
DB_PATH    = BASE_DIR / "adm_app.db"
DL_DIR.mkdir(exist_ok=True)

app = FastAPI(title="EduLoad")
app.mount("/static",    StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/downloads", StaticFiles(directory=str(DL_DIR)),     name="downloads")


# ══════════════════════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════════════════════
class DownloadRequest(BaseModel):
    url:     str
    quality: str = "best"
    subs:    list[str] = []
    fmt:     str = "mp4"

class SearchRequest(BaseModel):
    query:   str
    sources: list[str] = ["arxiv","gutenberg","doaj","youtube","openalex","archive","web"]
    limit:   int = 10

class ConvertRequest(BaseModel):
    filename: str
    to_fmt:   str

class NLRequest(BaseModel):
    text: str

class CollectionCreate(BaseModel):
    name:        str
    description: str = ""

class CollectionAddItem(BaseModel):
    history_id: int
    position:   int = 0

class TagRequest(BaseModel):
    tags: str

class BatchRequest(BaseModel):
    urls:    list[str]
    quality: str = "best"
    subs:    list[str] = []
    fmt:     str = "mp4"


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


def _run_download_job(job_id: str, req_data: dict):
    job    = download_jobs[job_id]
    job["status"] = "running"
    url    = req_data["url"]
    dl_dir = _get_download_dir()

    is_video = any(x in url for x in
                   ["youtube", "youtu.be", "vimeo", "dailymotion", "twitch", "tiktok"])

    if is_video:
        ytdlp_ok = _yt_dlp_available()

        if ytdlp_ok:
            out_tmpl = str(dl_dir / "%(title)s.%(ext)s")
            cmd = ["yt-dlp", "--output", out_tmpl, "--no-playlist", "--newline"]

            fmt     = req_data.get("fmt", "mp4")
            quality = req_data.get("quality", "best")
            if fmt == "mp3" or quality == "audio":
                cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
            else:
                h = quality if str(quality).isdigit() else "1080"
                cmd += ["-f", f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
                        "--merge-output-format", "mp4"]

            subs = req_data.get("subs", [])
            if subs:
                cmd += ["--write-subs", "--write-auto-subs",
                        "--sub-langs", ",".join(subs), "--convert-subs", "srt"]
            cmd.append(url)

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            dest = None
            for line in (proc.stdout or []):
                line = line.strip()
                m = re.search(r'\[download\]\s+([\d.]+)%.*?at\s+(\S+)\s+ETA\s+(\S+)', line)
                if m:
                    job["progress"] = float(m.group(1))
                    job["speed"]    = m.group(2)
                    job["eta"]      = m.group(3)
                for pat in [r'\[Merger\] Merging formats into "(.+?)"',
                            r'\[download\] Destination: (.+)',
                            r'\[ExtractAudio\] Destination: (.+)']:
                    m2 = re.search(pat, line)
                    if m2:
                        dest = Path(m2.group(1)).name
                        job["file"] = dest
            proc.wait()
            if proc.returncode == 0:
                job["status"] = "done"
                job["progress"] = 100
                job["method"]   = "yt-dlp"
                size_kb = 0
                if dest and (dl_dir / dest).exists():
                    size_kb = int((dl_dir / dest).stat().st_size / 1024)
                _history_insert(url, dest, "YouTube", dest, size_kb)
                return

        # yt-dlp unavailable or failed — try Apify then Direct HTTP
        job["error"] = ""
        for fb_method, fb_fn, fb_label, fb_source in [
            ("Apify API",   lambda: _downloader._download_apify(url, dl_dir),  "Apify API",   "Apify"),
            ("Direct HTTP", lambda: _downloader._download_direct(url, dl_dir), "Direct HTTP", "Direct"),
        ]:
            res = fb_fn()
            if res["success"]:
                fname = res["file"]
                job["status"]   = "done"
                job["progress"] = 100
                job["file"]     = fname
                job["method"]   = fb_label
                size_kb = int((dl_dir / fname).stat().st_size / 1024) if (dl_dir / fname).exists() else 0
                _history_insert(url, fname, fb_source, fname, size_kb)
                return

        job["status"] = "error"
        job["error"]  = "All download methods failed (yt-dlp, Apify, Direct)"
        return

    # direct file download with chunked progress
    try:
        parsed   = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or "download"
        if not Path(filename).suffix:
            filename += ".bin"
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

def _yt_dlp_available():
    return shutil.which("yt-dlp") is not None

def _ffmpeg_available():
    return shutil.which("ffmpeg") is not None

def _pandoc_available():
    return shutil.which("pandoc") is not None

def _tools_status():
    return {
        "yt_dlp":  _yt_dlp_available(),
        "ffmpeg":  _ffmpeg_available(),
        "pandoc":  _pandoc_available(),
    }

_ytdlp_info: dict = {"version": "unknown", "updated": False}

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

def _enqueue_job(url: str, quality: str = "best", subs: list = None, fmt: str = "mp4") -> str:
    subs = subs or []
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
        "method":   "",
    }
    _dl_queue.put((job_id, {"url": url, "quality": quality, "subs": subs, "fmt": fmt}))
    return job_id

def _auto_update_ytdlp():
    try:
        r = _run(["yt-dlp", "--version"])
        if r.returncode == 0:
            _ytdlp_info["version"] = r.stdout.strip()
        _run(["yt-dlp", "-U"])
        _ytdlp_info["updated"] = True
        r2 = _run(["yt-dlp", "--version"])
        if r2.returncode == 0:
            _ytdlp_info["version"] = r2.stdout.strip()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Startup
# ══════════════════════════════════════════════════════════════════════════════
@app.on_event("startup")
def startup_event():
    _init_db()
    for _ in range(_MAX_CONCURRENT):
        threading.Thread(target=_worker, daemon=True).start()
    if _yt_dlp_available():
        threading.Thread(target=_auto_update_ytdlp, daemon=True).start()

    print("\n=== Downloader Status ===")
    ytdlp_ver = _run(["yt-dlp", "--version"])
    if ytdlp_ver.returncode == 0:
        print(f"  [OK] yt-dlp v{ytdlp_ver.stdout.strip()}")
    else:
        print("  [--] yt-dlp: not available")
    apify_tok = _downloader.apify_token
    print(f"  {'[OK]' if apify_tok else '[--]'} Apify API: {'configured' if apify_tok else 'no token (disabled)'}")
    print("  [OK] Direct HTTP: always available")
    print("=========================\n")


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
    return {"tools": _tools_status(), "files": files}

@app.get("/api/ytdlp_version")
def ytdlp_version():
    return _ytdlp_info

@app.get("/api/download_stats")
def download_stats():
    return _downloader.get_stats()


# ══════════════════════════════════════════════════════════════════════════════
# Routes – Download
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/download")
def download_url(req: DownloadRequest):
    job_id = _enqueue_job(req.url.strip(), req.quality, req.subs, req.fmt)
    return {"job_id": job_id, "status": "queued"}

@app.post("/api/batch")
def batch_download(req: BatchRequest):
    job_ids = []
    for url in req.urls:
        url = url.strip()
        if not url:
            continue
        job_ids.append(_enqueue_job(url, req.quality, req.subs, req.fmt))
    return {"job_ids": job_ids, "count": len(job_ids)}

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
            })
        return results
    except Exception as ex:
        return [{"source":"DOAJ","icon":"🔓","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_youtube(query, limit=5):
    if not _yt_dlp_available():
        return []
    cmd = ["yt-dlp", f"ytsearch{limit}:{query} educational",
           "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(duration_string)s",
           "--no-download", "--no-warnings"]
    try:
        r = _run(cmd, timeout=20)
        results = []
        for line in r.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            vid_id   = parts[0]
            title    = parts[1]
            uploader = parts[2] if len(parts) > 2 else ""
            duration = parts[3] if len(parts) > 3 else ""
            results.append({
                "source":    "YouTube", "icon": "▶️",
                "title":     title,
                "authors":   uploader,
                "url":       f"https://www.youtube.com/watch?v={vid_id}",
                "pdf_url":   "",
                "snippet":   f"Duration: {duration}",
                "thumbnail": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
            })
        return results
    except Exception as ex:
        return [{"source":"YouTube","icon":"▶️","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_openalex(query, limit=5):
    q   = urllib.parse.quote(query)
    url = (f"https://api.openalex.org/works?search={q}"
           f"&filter=is_oa:true&per-page={limit}&mailto=app@adm_app.local")
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
            })
        return results
    except Exception as ex:
        return [{"source":"OpenAlex","icon":"🔬","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_archive(query, limit=5):
    q   = urllib.parse.quote(query)
    url = (f"https://archive.org/advancedsearch.php"
           f"?q={q}+AND+mediatype:(texts+OR+movies+OR+audio)"
           f"&fl[]=identifier,title,creator,description,mediatype"
           f"&rows={limit}&output=json")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        icon_map = {"texts": "📚", "movies": "🎬", "audio": "🎵"}
        results  = []
        for doc in data.get("response", {}).get("docs", []):
            idf = doc.get("identifier", "")
            mt  = doc.get("mediatype", "texts")
            results.append({
                "source":  "Archive.org", "icon": icon_map.get(mt, "📁"),
                "title":   doc.get("title", "—"),
                "authors": doc.get("creator", ""),
                "url":     f"https://archive.org/details/{idf}",
                "pdf_url": f"https://archive.org/download/{idf}/{idf}.pdf" if mt == "texts" else "",
                "snippet": (doc.get("description", "") or "")[:200],
            })
        return results
    except Exception as ex:
        return [{"source":"Archive.org","icon":"📚","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

def _search_web(query, limit=5):
    q   = urllib.parse.quote(query + " filetype:pdf OR site:archive.org OR open access")
    url = f"https://html.duckduckgo.com/html/?q={q}"
    try:
        req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=10) as r:
            html = r.read().decode("utf-8", "ignore")
        titles   = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
        links    = re.findall(r'class="result__url"[^>]*>(.*?)<', html, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
        results  = []
        for i in range(min(limit, len(titles))):
            clean = lambda s: re.sub(r'<[^>]+>', '', s).strip()
            href  = links[i].strip() if i < len(links) else ""
            if href and not href.startswith("http"):
                href = "https://" + href
            results.append({
                "source":  "Web", "icon": "🌐",
                "title":   clean(titles[i]),
                "authors": "",
                "url":     href,
                "pdf_url": href if href.endswith(".pdf") else "",
                "snippet": clean(snippets[i]) if i < len(snippets) else "",
            })
        return results
    except Exception as ex:
        return [{"source":"Web","icon":"🌐","title":f"Error: {ex}","url":"","pdf_url":"","snippet":"","authors":""}]

@app.post("/api/search")
def search(req: SearchRequest):
    results = []
    src_map = {
        "arxiv":     _search_arxiv,
        "gutenberg": _search_gutenberg,
        "doaj":      _search_doaj,
        "youtube":   _search_youtube,
        "openalex":  _search_openalex,
        "archive":   _search_archive,
        "web":       _search_web,
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
@app.post("/api/nl_search")
async def nl_search(request: Request):
    """Natural language search using Claude for intelligent source routing"""
    body = await request.json()
    user_query = body.get("query", "")

    if not user_query:
        return {"error": "No query provided", "results": []}

    router = ClaudeSearchRouter()
    routing = router.route(user_query)

    if not routing.get("sources"):
        return {
            "routing": routing,
            "results": [],
            "message": "This appears to be a conversion request. Use the /api/convert endpoint."
        }

    results = []
    for source in routing["sources"]:
        if source in routing.get("queries", {}):
            results.extend(_search_source(source, routing["queries"][source]))

    return {
        "success": True,
        "routing": routing,
        "results": results[:50],
        "claude_model": router.model
    }


def _search_source(source: str, query: str) -> list:
    src_map = {
        "youtube":          _search_youtube,
        "arxiv":            _search_arxiv,
        "gutenberg":        _search_gutenberg,
        "doaj":             _search_doaj,
        "openalex":         _search_openalex,
        "internet_archive": _search_archive,
        "duckduckgo":       _search_web,
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
    to   = req.to_fmt.lower()
    dest = dl_dir / f"{src.stem}_converted.{to}"

    if ext in (".mp4", ".webm", ".mkv", ".avi") and to == "mp3":
        if not _ffmpeg_available():
            raise HTTPException(400, "ffmpeg not installed")
        r = _run(["ffmpeg", "-y", "-i", str(src), "-vn", "-acodec", "libmp3lame",
                  "-ab", "192k", str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    elif to == "pdf" and ext in (".docx", ".html", ".htm", ".md", ".odt"):
        if not _pandoc_available():
            raise HTTPException(400, "pandoc not installed")
        r = _run(["pandoc", str(src), "-o", str(dest), "--pdf-engine=weasyprint"])
        if r.returncode != 0:
            r = _run(["pandoc", str(src), "-o", str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    elif ext == ".pdf" and to == "docx":
        try:
            from pdf2docx import Converter
        except ImportError:
            raise HTTPException(400, "pdf2docx not installed. Run: pip install pdf2docx")
        cv = Converter(str(src))
        cv.convert(str(dest))
        cv.close()

    elif ext in (".html", ".htm") and to == "docx":
        if not _pandoc_available():
            raise HTTPException(400, "pandoc not installed")
        r = _run(["pandoc", str(src), "-o", str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    else:
        raise HTTPException(400, f"Conversion {ext} → .{to} not supported")

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
    print("  EduLoad — Educational Resource Downloader")
    print("  http://127.0.0.1:7860")
    print("=" * 54)
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app:app", host="127.0.0.1", port=7860, reload=False)
