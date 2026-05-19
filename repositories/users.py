import sqlite3


def get_user_by_email(db: sqlite3.Connection, email: str) -> dict | None:
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(db: sqlite3.Connection, user_id: int) -> dict | None:
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_user(db: sqlite3.Connection, email: str, password_hash: str,
                role: str, institution_id: int | None) -> int:
    cur = db.execute(
        "INSERT INTO users (email, password_hash, role, institution_id, created_at)"
        " VALUES (?, ?, ?, ?, datetime('now'))",
        (email, password_hash, role, institution_id),
    )
    db.commit()
    return cur.lastrowid


def list_users(db: sqlite3.Connection) -> list:
    rows = db.execute(
        "SELECT id, email, role, institution_id, created_at FROM users ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_user(db: sqlite3.Connection, user_id: int) -> bool:
    changed = db.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount
    db.commit()
    return changed > 0


def update_role(db: sqlite3.Connection, user_id: int, role: str) -> None:
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    db.commit()
