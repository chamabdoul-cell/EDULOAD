from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from auth.dependencies import get_current_user
from services.convert import do_convert
from services.download import get_download_dir
from services.rate_limit import apply as rate_limit

router = APIRouter(prefix="/api", tags=["convert"])


class ConvertRequest(BaseModel):
    filename: str
    to_fmt:   str


@router.post("/convert")
def convert(req: ConvertRequest, request: Request,
            user: dict = Depends(get_current_user)):
    rate_limit(request, user)
    dl_dir   = get_download_dir()
    out_name = do_convert(req.filename, req.to_fmt, dl_dir)
    return {"status": "ok", "file": out_name}
