"""In-memory sliding-window rate limiter.

Single instance per process — thread-safe via a single lock.
Keys are typically "ip:<addr>" (single_user) or "user:<id>" (multi_user).
"""
import time
import threading
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from config.settings import AIConfig

_windows: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def check(key: str, limit: int, window_secs: int = 60) -> bool:
    """Return True if the request is within the rate limit, False if exceeded."""
    now    = time.monotonic()
    cutoff = now - window_secs
    with _lock:
        q = _windows[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def reset(key: str | None = None) -> None:
    """Clear rate-limit state for a key (or all keys). Used in tests."""
    with _lock:
        if key is None:
            _windows.clear()
        else:
            _windows.pop(key, None)


def apply(request: Request, user: dict) -> None:
    """Apply rate limiting to the current request; raise HTTP 429 if exceeded.

    single_user: 30 req/min per IP
    multi_user:  20 req/min per user_id
    """
    if AIConfig.is_multi_user():
        key, limit = f"user:{user['id']}", 20
    else:
        host = (request.client.host if request.client else None) or "unknown"
        key, limit = f"ip:{host}", 30
    if not check(key, limit):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded — try again in a minute")
