from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import get_current_user
from db import get_db
import repositories.collections as collections_repo
import repositories.history as history_repo

router = APIRouter(prefix="/api", tags=["collections"])


class CollectionCreate(BaseModel):
    name:        str
    description: str = ""


class CollectionAddItem(BaseModel):
    history_id: int | None = None
    position:   int = 0
    # Metadata-only path (no download required)
    title:      str = ""
    url:        str = ""
    source:     str = ""
    authors:    list[str] = []
    year:       int | None = None
    journal:    str = ""
    language:   str = ""


@router.get("/collections")
def list_collections(user: dict = Depends(get_current_user)):
    db   = get_db()
    rows = collections_repo.list_collections(db)
    db.close()
    return rows


@router.post("/collections")
def create_collection(req: CollectionCreate, user: dict = Depends(get_current_user)):
    db    = get_db()
    rowid = collections_repo.create_collection(db, req.name, req.description,
                                               owner_id=user.get("id"))
    db.close()
    return {"id": rowid, "status": "ok"}


@router.get("/collections/shared")
def list_shared_collections(user: dict = Depends(get_current_user)):
    institution_id = user.get("institution_id")
    if not institution_id:
        return []
    db   = get_db()
    rows = collections_repo.list_shared_collections(db, institution_id)
    db.close()
    return rows


@router.post("/collections/{id}/share")
def share_collection(id: int, user: dict = Depends(get_current_user)):
    institution_id = user.get("institution_id")
    if not institution_id:
        raise HTTPException(400, "User has no institution")
    db = get_db()
    col = collections_repo.get_collection(db, id)
    if not col:
        db.close()
        raise HTTPException(404, "Collection not found")
    collections_repo.share_collection(db, id, institution_id)
    db.close()
    return {"status": "shared"}


@router.get("/collections/{id}")
def get_collection(id: int, user: dict = Depends(get_current_user)):
    db  = get_db()
    col = collections_repo.get_collection(db, id)
    if not col:
        db.close()
        raise HTTPException(404, "Collection not found")
    items = collections_repo.get_collection_items(db, id)
    db.close()
    return {"collection": col, "items": items}


@router.post("/collections/{id}/items")
def add_to_collection(id: int, req: CollectionAddItem,
                      user: dict = Depends(get_current_user)):
    db  = get_db()
    col = collections_repo.get_collection(db, id)
    if not col:
        db.close()
        raise HTTPException(404, "Collection not found")

    history_id = req.history_id
    if history_id is None:
        # Metadata-only path: create a history entry without a file
        if not req.url:
            db.close()
            raise HTTPException(422, "Provide either history_id or url+title")
        history_id = history_repo.add_history_entry_metadata_only(
            db, req.url, req.title, req.source or "bookmarked",
            authors=req.authors or None, year=req.year,
            journal=req.journal, language=req.language,
        )

    rowid = collections_repo.add_item(db, id, history_id, req.position)
    db.close()
    return {"id": rowid, "status": "ok", "history_id": history_id}


@router.delete("/collections/{id}/items/{item_id}")
def remove_from_collection(id: int, item_id: int,
                            user: dict = Depends(get_current_user)):
    db = get_db()
    collections_repo.remove_item(db, id, item_id)
    db.close()
    return {"status": "ok"}


@router.delete("/collections/{id}")
def delete_collection(id: int, user: dict = Depends(get_current_user)):
    db = get_db()
    collections_repo.delete_collection(db, id)
    db.close()
    return {"status": "ok"}
