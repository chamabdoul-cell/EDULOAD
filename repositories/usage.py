import sqlite3


def record(db: sqlite3.Connection, user_id: int, endpoint: str, tokens: int = 0) -> None:
    db.execute(
        "INSERT INTO usage (user_id, endpoint, tokens_used, created_at)"
        " VALUES (?, ?, ?, datetime('now'))",
        (user_id, endpoint, tokens),
    )
    db.commit()


def get_stats(db: sqlite3.Connection) -> list:
    rows = db.execute(
        """SELECT endpoint, COUNT(*) AS count, COALESCE(SUM(tokens_used), 0) AS tokens
           FROM usage GROUP BY endpoint ORDER BY count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def count_today(db: sqlite3.Connection, user_id: int, endpoint: str) -> int:
    return db.execute(
        """SELECT COUNT(*) FROM usage
           WHERE user_id = ? AND endpoint = ? AND date(created_at) = date('now')""",
        (user_id, endpoint),
    ).fetchone()[0]
