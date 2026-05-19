import sqlite3


def log(db: sqlite3.Connection, user_id: int, action: str, target: str = "") -> None:
    db.execute(
        "INSERT INTO audit_logs (user_id, action, target, created_at)"
        " VALUES (?, ?, ?, datetime('now'))",
        (user_id, action, target),
    )
    db.commit()


def list_logs(db: sqlite3.Connection, limit: int = 100) -> list:
    rows = db.execute(
        "SELECT id, user_id, action, target, created_at"
        " FROM audit_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
