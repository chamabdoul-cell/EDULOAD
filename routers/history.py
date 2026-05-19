from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import get_current_user
from db import get_db
import repositories.history as history_repo

router = APIRouter(prefix="/api", tags=["history"])


class TagRequest(BaseModel):
    tags: str


@router.get("/history")
def get_history(limit: int = 50, user: dict = Depends(get_current_user)):
    db   = get_db()
    rows = history_repo.get_history(db, limit)
    db.close()
    return rows


@router.post("/history/{id}/tag")
def tag_history(id: int, req: TagRequest, user: dict = Depends(get_current_user)):
    db = get_db()
    history_repo.tag_entry(db, id, req.tags)
    db.close()
    return {"status": "ok"}


@router.delete("/history/{id}")
def delete_history(id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    history_repo.delete_entry(db, id)
    db.close()
    return {"status": "ok"}
