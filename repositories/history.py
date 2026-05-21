import json
import sqlite3


def get_history(db: sqlite3.Connection, limit: int = 50) -> list:
    rows = db.execute("SELECT * FROM history ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def add_history_entry(db: sqlite3.Connection, url: str, title: str, source: str,
                      filename: str, size_kb: int, authors=None, year=None,
                      journal=None, language=None) -> int | None:
    try:
        authors_str = json.dumps(authors) if authors else None
        cur = db.execute(
            """INSERT INTO history (url,title,source,filename,size_kb,authors,year,journal,language)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (url, title or filename, source, filename, size_kb,
             authors_str, year, journal, language),
        )
        db.commit()
        return cur.lastrowid
    except Exception:
        return None


def tag_entry(db: sqlite3.Connection, id: int, tags: str) -> None:
    db.execute("UPDATE history SET tags=? WHERE id=?", (tags, id))
    db.commit()


def delete_entry(db: sqlite3.Connection, id: int) -> None:
    db.execute("DELETE FROM history WHERE id=?", (id,))
    db.commit()


def get_entry(db: sqlite3.Connection, id: int) -> dict | None:
    row = db.execute("SELECT * FROM history WHERE id=?", (id,)).fetchone()
    return dict(row) if row else None


def add_history_entry_metadata_only(
    db: sqlite3.Connection, url: str, title: str, source: str,
    authors=None, year=None, journal=None, language=None
) -> int | None:
    """Insert a bookmarked-but-not-downloaded entry (filename=NULL, size_kb=0)."""
    try:
        authors_str = json.dumps(authors) if authors else None
        cur = db.execute(
            """INSERT INTO history (url,title,source,filename,size_kb,authors,year,journal,language)
               VALUES (?,?,?,NULL,0,?,?,?,?)""",
            (url, title or url, source, authors_str, year, journal, language),
        )
        db.commit()
        return cur.lastrowid
    except Exception:
        return None


def top_sources(db: sqlite3.Connection, limit: int = 5) -> list:
    rows = db.execute(
        """SELECT source, COUNT(*) AS n FROM history
           GROUP BY source ORDER BY n DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
