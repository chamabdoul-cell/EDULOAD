import sqlite3


def list_institutions(db: sqlite3.Connection) -> list:
    rows = db.execute("SELECT * FROM institutions ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_institution(db: sqlite3.Connection, name: str, country: str = "",
                       logo_url: str | None = None, primary_color: str | None = None) -> int:
    cur = db.execute(
        "INSERT INTO institutions (name, country, logo_url, primary_color, created_at)"
        " VALUES (?, ?, ?, ?, datetime('now'))",
        (name, country, logo_url, primary_color),
    )
    db.commit()
    return cur.lastrowid


def get_institution_branding(db: sqlite3.Connection, institution_id: int) -> dict | None:
    row = db.execute(
        "SELECT logo_url, primary_color FROM institutions WHERE id=?", (institution_id,)
    ).fetchone()
    if row is None:
        return None
    if row["logo_url"] is None and row["primary_color"] is None:
        return None
    return dict(row)
