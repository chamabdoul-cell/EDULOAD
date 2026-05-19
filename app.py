"""
Scholara — Open-Access Research Platform
Run: python app.py
"""
import os
import sqlite3
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.settings import AIConfig
from db import get_db

# ── Routers ───────────────────────────────────────────────────────────────────
from routers.auth import router as auth_router
from routers.admin import router as admin_router
from routers.search import router as search_router
from routers.download import router as download_router
from routers.history import router as history_router
from routers.collections import router as collections_router
from routers.files import router as files_router
from routers.convert import router as convert_router
from routers.settings import router as settings_router
from routers.citations import router as citations_router

# ── Services ──────────────────────────────────────────────────────────────────
from services.download import load_jobs_from_db, start_workers, get_download_dir
from services.convert import ffmpeg_available, pandoc_available
import repositories.institutions as inst_repo

BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH    = BASE_DIR / "scholara.db"

app = FastAPI(title="Scholara")
app.mount("/static",    StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/downloads", StaticFiles(directory=str(BASE_DIR / "downloads")), name="downloads")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(search_router)
app.include_router(download_router)
app.include_router(history_router)
app.include_router(collections_router)
app.include_router(files_router)
app.include_router(convert_router)
app.include_router(settings_router)
app.include_router(citations_router)


# ══════════════════════════════════════════════════════════════════════════════
# Database initialisation
# ══════════════════════════════════════════════════════════════════════════════
def _init_db():
    con = get_db()
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
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        name           TEXT NOT NULL,
        description    TEXT,
        owner_id       INTEGER,
        institution_id INTEGER,
        is_shared      INTEGER DEFAULT 0,
        created_at     TEXT DEFAULT (datetime('now'))
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
    con.execute("""CREATE TABLE IF NOT EXISTS institutions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        country       TEXT,
        logo_url      TEXT,
        primary_color TEXT,
        created_at    TEXT DEFAULT (datetime('now'))
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        email          TEXT UNIQUE NOT NULL,
        password_hash  TEXT NOT NULL,
        role           TEXT NOT NULL DEFAULT 'researcher',
        institution_id INTEGER REFERENCES institutions(id),
        created_at     TEXT DEFAULT (datetime('now'))
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS usage (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER REFERENCES users(id),
        endpoint    TEXT,
        tokens_used INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER REFERENCES users(id),
        action     TEXT,
        target     TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS search_queries (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        query_stem TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    con.commit()

    # Migrate collections table
    coll_cols = {row[1] for row in con.execute("PRAGMA table_info(collections)")}
    for col, typedef in [("owner_id", "INTEGER"), ("institution_id", "INTEGER"),
                         ("is_shared", "INTEGER DEFAULT 0")]:
        if col not in coll_cols:
            con.execute(f"ALTER TABLE collections ADD COLUMN {col} {typedef}")

    # Migrate institutions table
    inst_cols = {row[1] for row in con.execute("PRAGMA table_info(institutions)")}
    for col, typedef in [("logo_url", "TEXT"), ("primary_color", "TEXT")]:
        if col not in inst_cols:
            con.execute(f"ALTER TABLE institutions ADD COLUMN {col} {typedef}")

    con.commit()

    existing = {row[1] for row in con.execute("PRAGMA table_info(history)")}
    for col, typedef in [("authors", "TEXT"), ("year", "INTEGER"),
                         ("journal", "TEXT"), ("language", "TEXT")]:
        if col not in existing:
            con.execute(f"ALTER TABLE history ADD COLUMN {col} {typedef}")
    con.commit()
    con.close()


# ══════════════════════════════════════════════════════════════════════════════
# PWA icon generation
# ══════════════════════════════════════════════════════════════════════════════
def _generate_pwa_icons():
    import struct, zlib

    def _png(size):
        bg  = (0xC8, 0x43, 0x0B)
        fg  = (0xFF, 0xFF, 0xFF)
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


# ══════════════════════════════════════════════════════════════════════════════
# Routes — System
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/status")
async def status():
    dl_dir = get_download_dir()
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

    institution_branding = None
    if AIConfig.APP_MODE == "multi_user":
        try:
            from auth.dependencies import get_current_user
            con = get_db()
            institutions = inst_repo.list_institutions(con)
            con.close()
            if institutions:
                institution_branding = inst_repo.get_institution_branding(
                    get_db(), institutions[0]["id"]
                )
        except Exception:
            pass

    return {
        "tools":               {"ffmpeg": ffmpeg_available(), "pandoc": pandoc_available()},
        "files":               files,
        "ollama_available":    ollama_available,
        "ollama_model":        ollama_model,
        "ollama_url":          AIConfig.OLLAMA_URL,
        "deepseek_configured": bool(AIConfig.DEEPSEEK_API_KEY),
        "ai_backend":          AIConfig.BACKEND,
        "market_segment":      AIConfig.MARKET_SEGMENT.value,
        "app_mode":            AIConfig.APP_MODE,
        "active_sources":      (
            ["arxiv", "gutenberg", "doaj", "openalex", "internet_archive",
             "hal", "persee", "openedition", "erudit"]
            + (["semantic_scholar", "pubmed", "crossref", "core", "base"]
               if AIConfig.is_north() else [])
        ),
        "ytdlp_available":        AIConfig.is_north(),
        "institution_branding":   institution_branding,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Startup / shutdown
# ══════════════════════════════════════════════════════════════════════════════
@app.on_event("startup")
def startup_event():
    _init_db()
    _generate_pwa_icons()
    load_jobs_from_db()
    start_workers()

    ollama_ok = False
    try:
        with urllib.request.urlopen(f"{AIConfig.OLLAMA_URL}/api/tags", timeout=2) as r:
            ollama_ok = r.status == 200
    except Exception:
        pass

    print("\n=== Scholara Status ===")
    print(f"  {'[OK]' if ollama_ok else '[--]'} Ollama ({AIConfig.OLLAMA_MODEL})")
    print(f"  {'[OK]' if AIConfig.DEEPSEEK_API_KEY else '[--]'} DeepSeek API")
    print(f"  {'[OK]' if ffmpeg_available() else '[--]'} ffmpeg (conversion)")
    print("  [OK] Direct HTTP: always available")
    print(f"  [OK] Mode: {AIConfig.APP_MODE}  |  Segment: {AIConfig.MARKET_SEGMENT.value}")
    print("======================\n")


# ══════════════════════════════════════════════════════════════════════════════
# Launch
# ══════════════════════════════════════════════════════════════════════════════
def _open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:7860")


def _free_port(port: int):
    import signal, socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return
    except Exception:
        return
    try:
        import subprocess as sp
        out = sp.check_output(["lsof", "-ti", f":{port}"], text=True).strip()
        for pid in out.splitlines():
            try:
                os.kill(int(pid), signal.SIGTERM)
                print(f"  [info] Released port {port} (pid {pid})")
            except Exception:
                pass
        time.sleep(0.5)
    except Exception:
        pass


if __name__ == "__main__":
    _free_port(7860)
    print("=" * 54)
    print("  Scholara — Open Knowledge, Everywhere")
    print("  http://127.0.0.1:7860")
    print("=" * 54)
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app:app", host="127.0.0.1", port=7860, reload=False)
