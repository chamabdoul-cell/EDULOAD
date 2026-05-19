from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_db
import repositories.collections as collections_repo

router = APIRouter(prefix="/api", tags=["collections"])


class CollectionCreate(BaseModel):
    name:        str
    description: str = ""


class CollectionAddItem(BaseModel):
    history_id: int
    position:   int = 0


@router.get("/collections")
def list_collections():
    db   = get_db()
    rows = collections_repo.list_collections(db)
    db.close()
    return rows


@router.post("/collections")
def create_collection(req: CollectionCreate):
    db    = get_db()
    rowid = collections_repo.create_collection(db, req.name, req.description)
    db.close()
    return {"id": rowid, "status": "ok"}


@router.get("/collections/{id}")
def get_collection(id: int):
    db  = get_db()
    col = collections_repo.get_collection(db, id)
    if not col:
        db.close()
        raise HTTPException(404, "Collection not found")
    items = collections_repo.get_collection_items(db, id)
    db.close()
    return {"collection": col, "items": items}


@router.post("/collections/{id}/items")
def add_to_collection(id: int, req: CollectionAddItem):
    db  = get_db()
    col = collections_repo.get_collection(db, id)
    if not col:
        db.close()
        raise HTTPException(404, "Collection not found")
    rowid = collections_repo.add_item(db, id, req.history_id, req.position)
    db.close()
    return {"id": rowid, "status": "ok"}


@router.delete("/collections/{id}/items/{item_id}")
def remove_from_collection(id: int, item_id: int):
    db = get_db()
    collections_repo.remove_item(db, id, item_id)
    db.close()
    return {"status": "ok"}


@router.delete("/collections/{id}")
def delete_collection(id: int):
    db = get_db()
    collections_repo.delete_collection(db, id)
    db.close()
    return {"status": "ok"}
