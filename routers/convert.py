from fastapi import APIRouter
from pydantic import BaseModel

from services.convert import do_convert
from services.download import get_download_dir

router = APIRouter(prefix="/api", tags=["convert"])


class ConvertRequest(BaseModel):
    filename: str
    to_fmt:   str


@router.post("/convert")
def convert(req: ConvertRequest):
    dl_dir   = get_download_dir()
    out_name = do_convert(req.filename, req.to_fmt, dl_dir)
    return {"status": "ok", "file": out_name}
