from fastapi import APIRouter, Body

from db import get_db
import repositories.settings as settings_repo

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings():
    db   = get_db()
    data = settings_repo.get_all_settings(db)
    db.close()
    return data


@router.post("/settings")
def save_settings(data: dict = Body(...)):
    db = get_db()
    settings_repo.upsert_settings(db, data)
    db.close()
    return {"status": "ok"}
