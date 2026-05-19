from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_db
import repositories.history as history_repo

router = APIRouter(prefix="/api", tags=["history"])


class TagRequest(BaseModel):
    tags: str


@router.get("/history")
def get_history(limit: int = 50):
    db   = get_db()
    rows = history_repo.get_history(db, limit)
    db.close()
    return rows


@router.post("/history/{id}/tag")
def tag_history(id: int, req: TagRequest):
    db = get_db()
    history_repo.tag_entry(db, id, req.tags)
    db.close()
    return {"status": "ok"}


@router.delete("/history/{id}")
def delete_history(id: int):
    db = get_db()
    history_repo.delete_entry(db, id)
    db.close()
    return {"status": "ok"}
