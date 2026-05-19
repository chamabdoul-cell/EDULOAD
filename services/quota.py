"""Per-user daily download quota.

Reads MAX_DOWNLOADS_PER_DAY from env (default 50).
No-op in single_user mode.
"""
import os
from fastapi import HTTPException
from config.settings import AIConfig
from db import get_db
import repositories.usage as usage_repo

MAX_DOWNLOADS_PER_DAY = int(os.getenv("MAX_DOWNLOADS_PER_DAY", "50"))


def check_quota(user_id: int) -> None:
    """Raise HTTP 429 if the user has reached their daily download quota."""
    if not AIConfig.is_multi_user():
        return
    con   = get_db()
    count = usage_repo.count_today(con, user_id, "/api/download")
    con.close()
    if count >= MAX_DOWNLOADS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily download quota of {MAX_DOWNLOADS_PER_DAY} exceeded. Try again tomorrow.",
        )
