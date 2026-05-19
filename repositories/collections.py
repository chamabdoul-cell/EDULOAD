import sqlite3


def list_collections(db: sqlite3.Connection) -> list:
    rows = db.execute("SELECT * FROM collections ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def create_collection(db: sqlite3.Connection, name: str, description: str = "") -> int:
    cur = db.execute(
        "INSERT INTO collections (name,description) VALUES (?,?)", (name, description)
    )
    db.commit()
    return cur.lastrowid


def get_collection(db: sqlite3.Connection, id: int) -> dict | None:
    row = db.execute("SELECT * FROM collections WHERE id=?", (id,)).fetchone()
    return dict(row) if row else None


def get_collection_items(db: sqlite3.Connection, collection_id: int) -> list:
    rows = db.execute(
        """SELECT ci.id as item_id, ci.position, h.*
           FROM collection_items ci
           JOIN history h ON h.id = ci.history_id
           WHERE ci.collection_id=?
           ORDER BY ci.position""",
        (collection_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_item(db: sqlite3.Connection, collection_id: int, history_id: int,
             position: int = 0) -> int:
    cur = db.execute(
        "INSERT INTO collection_items (collection_id,history_id,position) VALUES (?,?,?)",
        (collection_id, history_id, position),
    )
    db.commit()
    return cur.lastrowid


def remove_item(db: sqlite3.Connection, collection_id: int, item_id: int) -> None:
    db.execute(
        "DELETE FROM collection_items WHERE id=? AND collection_id=?", (item_id, collection_id)
    )
    db.commit()


def delete_collection(db: sqlite3.Connection, id: int) -> None:
    db.execute("DELETE FROM collection_items WHERE collection_id=?", (id,))
    db.execute("DELETE FROM collections WHERE id=?", (id,))
    db.commit()
