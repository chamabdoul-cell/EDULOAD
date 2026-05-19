import sqlite3


def enqueue_job(db: sqlite3.Connection, job_id: str, url: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO download_queue (job_id, url) VALUES (?, ?)", (job_id, url)
    )
    db.commit()


def update_job(db: sqlite3.Connection, job_id: str, status: str = None,
               progress: float = None, error: str = None, filename: str = None) -> None:
    updates = ["updated_at = datetime('now')"]
    params = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    if error is not None:
        updates.append("error = ?")
        params.append(error)
    if filename is not None:
        updates.append("result_filename = ?")
        params.append(filename)
    params.append(job_id)
    db.execute(f"UPDATE download_queue SET {', '.join(updates)} WHERE job_id = ?", params)
    db.commit()


def load_interrupted_jobs(db: sqlite3.Connection) -> list:
    rows = db.execute(
        "SELECT job_id, url FROM download_queue WHERE status IN ('queued','running')"
    ).fetchall()
    db.execute("UPDATE download_queue SET status='queued' WHERE status='running'")
    db.commit()
    return [{"job_id": r["job_id"], "url": r["url"]} for r in rows]


def get_job(db: sqlite3.Connection, job_id: str) -> dict | None:
    row = db.execute("SELECT * FROM download_queue WHERE job_id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(db: sqlite3.Connection) -> list:
    rows = db.execute(
        "SELECT * FROM download_queue ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def cancel_job(db: sqlite3.Connection, job_id: str) -> None:
    db.execute("UPDATE download_queue SET status='cancelled' WHERE job_id = ?", (job_id,))
    db.commit()
