import sqlite3


def list_institutions(db: sqlite3.Connection) -> list:
    rows = db.execute("SELECT * FROM institutions ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_institution(db: sqlite3.Connection, name: str, country: str = "") -> int:
    cur = db.execute(
        "INSERT INTO institutions (name, country, created_at) VALUES (?, ?, datetime('now'))",
        (name, country),
    )
    db.commit()
    return cur.lastrowid
