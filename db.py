"""Shared SQLite connection helper used by app.py and all routers."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "scholara.db"


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con
