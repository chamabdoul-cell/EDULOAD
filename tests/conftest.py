"""Shared test fixtures — fresh temp DB that patches db.DB_PATH for each test."""
import sqlite3
import pytest


def _create_all_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS history (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT DEFAULT (datetime('now')),
            url      TEXT, title TEXT, source TEXT, filename TEXT,
            size_kb  INTEGER, tags TEXT, authors TEXT,
            year INTEGER, journal TEXT, language TEXT
        );
        CREATE TABLE IF NOT EXISTS usage (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            endpoint    TEXT,
            tokens_used INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT NOT NULL,
            role           TEXT NOT NULL DEFAULT 'researcher',
            institution_id INTEGER,
            created_at     TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, country TEXT,
            logo_url TEXT, primary_color TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, description TEXT,
            owner_id INTEGER, institution_id INTEGER, is_shared INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS search_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_stem TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS collection_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER, history_id INTEGER, position INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS download_queue (
            job_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            status TEXT DEFAULT 'queued',
            progress REAL DEFAULT 0,
            error TEXT, result_filename TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT, target TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point db.DB_PATH at a fresh temp file and create all tables."""
    db_file = tmp_path / "scholara_test.db"
    monkeypatch.setattr("db.DB_PATH", db_file)
    import db as db_module
    con = db_module.get_db()
    _create_all_tables(con)
    con.close()
    yield db_file
