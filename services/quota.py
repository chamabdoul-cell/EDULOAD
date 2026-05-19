"""Per-user daily download quota.

Reads MAX_DOWNLOADS_PER_DAY from env (default 50).
No-op in single_user mode.
"""
import os
from fastapi import HTTPException
from config.settings import AIConfig
from db import get_db

MAX_DOWNLOADS_PER_DAY = int(os.getenv("MAX_DOWNLOADS_PER_DAY", "50"))


def check_quota(user_id: int) -> None:
    """Raise HTTP 429 if the user has reached their daily download quota."""
    if not AIConfig.is_multi_user():
        return
    db    = get_db()
    count = db.execute(
        """SELECT COUNT(*) FROM usage
           WHERE user_id = ? AND endpoint = '/api/download'
           AND date(created_at) = date('now')""",
        (user_id,),
    ).fetchone()[0]
    db.close()
    if count >= MAX_DOWNLOADS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily download quota of {MAX_DOWNLOADS_PER_DAY} exceeded. Try again tomorrow.",
        )
