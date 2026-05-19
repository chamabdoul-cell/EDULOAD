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


def record_query(db: sqlite3.Connection, query_stem: str) -> None:
    db.execute(
        "INSERT INTO search_queries (query_stem) VALUES (?)", (query_stem,)
    )
    db.commit()


def top_queries(db: sqlite3.Connection, limit: int = 10) -> list:
    rows = db.execute(
        """SELECT query_stem, COUNT(*) AS count
           FROM search_queries GROUP BY query_stem ORDER BY count DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def downloads_by_day(db: sqlite3.Connection, days: int = 30) -> list:
    rows = db.execute(
        """SELECT date(ts) AS day, COUNT(*) AS count FROM history
           WHERE ts >= datetime('now', ? || ' days')
           GROUP BY day ORDER BY day""",
        (f"-{days}",),
    ).fetchall()
    return [dict(r) for r in rows]


def active_users_per_week(db: sqlite3.Connection) -> int:
    row = db.execute(
        """SELECT COUNT(DISTINCT user_id) FROM usage
           WHERE created_at >= datetime('now', '-7 days')"""
    ).fetchone()
    return row[0] if row else 0
