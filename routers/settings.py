from fastapi import APIRouter, Body, Depends

from auth.dependencies import get_current_user, require_role
from db import get_db
import repositories.settings as settings_repo

router = APIRouter(prefix="/api", tags=["settings"])

_admin = require_role("admin")


@router.get("/settings")
def get_settings(user: dict = Depends(get_current_user)):
    db   = get_db()
    data = settings_repo.get_all_settings(db)
    db.close()
    return data


@router.post("/settings")
def save_settings(data: dict = Body(...), user: dict = Depends(_admin)):
    db = get_db()
    settings_repo.upsert_settings(db, data)
    db.close()
    return {"status": "ok"}
