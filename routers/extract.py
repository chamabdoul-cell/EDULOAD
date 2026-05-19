"""POST /api/extract — text extraction from downloaded files or raw input."""
import math
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth.dependencies import get_current_user
from config.settings import AIConfig
from services.audit import record_usage
from services.download import get_download_dir
from services.rate_limit import check as rl_check

router = APIRouter(prefix="/api", tags=["extract"])

MAX_EXTRACT_BYTES = int(os.environ.get("MAX_EXTRACT_SIZE_MB", 50)) * 1024 * 1024
_ALLOWED_EXTS = {".pdf", ".docx", ".txt", ".html", ".md"}
_CHUNK_SIZE = 2000


class ExtractRequest(BaseModel):
    filename: Optional[str] = None
    text:     Optional[str] = None
    max_chars: int = 12000


def _rate_key(request: Request, user: dict) -> str:
    if AIConfig.is_multi_user():
        return f"extract:user:{user['id']}"
    host = (request.client.host if request.client else None) or "unknown"
    return f"extract:ip:{host}"


def _clean(text: str) -> str:
    text = "".join(c for c in text if c == "\n" or not unicodedata.category(c).startswith("C"))
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
    lines = [ln.strip() for ln in text.splitlines()]
    # Collapse 3+ blank lines to 2
    out, blanks = [], 0
    for ln in lines:
        if ln == "":
            blanks += 1
            if blanks <= 2:
                out.append("")
        else:
            blanks = 0
            out.append(ln)
    return "\n".join(out).strip()


def _chunk(text: str, max_chars: int) -> list[dict]:
    max_chunks = math.ceil(max_chars / _CHUNK_SIZE)
    # Split on sentence boundaries
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks, current, offset, current_offset = [], "", 0, 0
    for part in parts:
        if len(current) + len(part) + 1 > _CHUNK_SIZE and current:
            chunks.append({"index": len(chunks), "offset": current_offset, "text": current.strip()})
            if len(chunks) >= max_chunks:
                return chunks
            current_offset = offset
            current = part
        else:
            if current:
                current += " " + part
            else:
                current = part
        offset += len(part) + 1
    if current and len(chunks) < max_chunks:
        chunks.append({"index": len(chunks), "offset": current_offset, "text": current.strip()})
    return chunks


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            import mammoth
            with open(path, "rb") as f:
                result = mammoth.extract_raw_text(f)
            return result.value
        if ext in (".txt", ".md"):
            return path.read_text(errors="replace")
        if ext == ".html":
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            return h.handle(path.read_text(errors="replace"))
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail={"error": "extraction_failed", "detail": str(exc)})
    raise HTTPException(status_code=400, detail="Unsupported file type")


@router.post("/extract")
def extract(req: ExtractRequest, request: Request,
            user: dict = Depends(get_current_user)):
    # Rate limit: 10/min
    key = _rate_key(request, user)
    if not rl_check(key, limit=10, window_secs=60):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded — 10 extractions/min")

    dl_dir = get_download_dir()

    if req.filename:
        # Path traversal check
        if ".." in req.filename or req.filename.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid filename")
        path = (dl_dir / req.filename).resolve()
        if not str(path).startswith(str(dl_dir.resolve())):
            raise HTTPException(status_code=400, detail="Invalid filename")
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        if path.stat().st_size > MAX_EXTRACT_BYTES:
            raise HTTPException(status_code=413, detail="File too large")
        if path.suffix.lower() not in _ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        raw = _extract_text(path)
        source = "filename"
        filename = req.filename
    elif req.text:
        raw = req.text.strip()
        if not raw:
            raise HTTPException(status_code=400, detail="text is empty")
        if len(raw) > 50_000:
            raise HTTPException(status_code=413, detail="text too long (max 50 000 chars)")
        source = "manual"
        filename = None
    else:
        raise HTTPException(status_code=400, detail="Provide filename or text")

    cleaned    = _clean(raw)
    chunks     = _chunk(cleaned, req.max_chars)
    total_text = cleaned[: req.max_chars]
    truncated  = len(cleaned) > req.max_chars

    record_usage(user["id"], "/api/extract")
    return {
        "source":      source,
        "filename":    filename,
        "total_chars": len(cleaned),
        "chunks":      chunks,
        "truncated":   truncated,
    }
