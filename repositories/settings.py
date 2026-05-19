import sqlite3


def get_all_settings(db: sqlite3.Connection) -> dict:
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_setting(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def upsert_settings(db: sqlite3.Connection, data: dict) -> None:
    for k, v in data.items():
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))
    db.commit()
