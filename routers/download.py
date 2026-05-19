import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.download import download_jobs, enqueue_job, is_allowed_url
from db import get_db
import repositories.queue as queue_repo

router = APIRouter(prefix="/api", tags=["download"])

_MESSAGES = {
    "download_not_allowed": {
        "en": "URL not from an allowed open-access source. Allowed: arxiv.org, doaj.org, archive.org, hal.science, and others.",
        "fr": "Cette URL ne provient pas d'une source en libre accès autorisée. Autorisées : arxiv.org, doaj.org, archive.org, hal.science, et autres.",
    },
}


def _get_lang(request: Request) -> str:
    return request.headers.get("Accept-Language", "en")[:2].lower()


def _msg(key: str, lang: str) -> str:
    return _MESSAGES.get(key, {}).get(lang) or _MESSAGES.get(key, {}).get("en") or key


class DownloadRequest(BaseModel):
    url:                 str
    title:               str = ""
    authors:             list[str] = []
    year:                int | None = None
    journal:             str = ""
    language:            str = ""
    disclaimer_accepted: bool = False


@router.post("/download")
def download_url(req: DownloadRequest, request: Request):
    url  = req.url.strip()
    lang = _get_lang(request)
    if not is_allowed_url(url):
        raise HTTPException(403, _msg("download_not_allowed", lang))
    meta = {
        "title":    req.title,
        "authors":  req.authors,
        "year":     req.year,
        "journal":  req.journal,
        "language": req.language,
    }
    job_id = enqueue_job(url, meta=meta)
    return {"job_id": job_id, "status": "queued"}


@router.get("/progress/{job_id}")
def progress_sse(job_id: str):
    def gen():
        while True:
            job = download_jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break
            yield f"data: {json.dumps(job)}\n\n"
            if job["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/queue")
def get_queue():
    jobs   = list(download_jobs.values())
    queued = [j for j in jobs if j["status"] == "queued"]
    for i, j in enumerate(queued):
        j["position"] = i
    return jobs


@router.delete("/queue/{job_id}")
def cancel_job(job_id: str):
    job = download_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "queued":
        raise HTTPException(400, "Can only cancel queued jobs")
    job["status"] = "cancelled"
    try:
        db = get_db()
        queue_repo.update_job(db, job_id, status="cancelled")
        db.close()
    except Exception:
        pass
    return {"status": "cancelled"}
