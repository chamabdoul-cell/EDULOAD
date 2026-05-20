"""FastAPI dependency injection for authentication and role enforcement.

In single_user mode every request is treated as an authenticated admin —
existing single-user workflows are completely unaffected.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config.settings import AIConfig
from auth.jwt_handler import decode_token
from db import get_db

_bearer = HTTPBearer(auto_error=False)

# Synthetic user returned in single_user mode — no DB lookup needed.
_SINGLE_USER = {"id": 0, "email": "local@scholara", "role": "admin", "institution_id": None}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not AIConfig.is_multi_user():
        return _SINGLE_USER

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    con = get_db()
    row = con.execute(
        "SELECT id, email, role, institution_id FROM users WHERE id = ?",
        (payload["sub"],),
    ).fetchone()
    con.close()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(row)


def require_role(*roles: str):
    """Return a dependency that enforces one of the given roles."""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _dep
