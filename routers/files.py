from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.download import get_download_dir

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/file/{filename}")
def get_file(filename: str):
    f = get_download_dir() / filename
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(str(f), content_disposition_type="inline")


@router.delete("/file/{filename}")
def delete_file(filename: str):
    f = get_download_dir() / filename
    if f.exists():
        f.unlink()
    return {"status": "ok"}
