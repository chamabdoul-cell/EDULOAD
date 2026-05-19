import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from auth.dependencies import get_current_user
from db import get_db
import repositories.history as history_repo

router = APIRouter(prefix="/api", tags=["citations"])


@router.get("/cite/{history_id}")
def cite_document(history_id: int, format: str = "bibtex",
                  user: dict = Depends(get_current_user)):
    db  = get_db()
    row = history_repo.get_entry(db, history_id)
    db.close()

    if not row:
        raise HTTPException(404, "Document not found")

    title    = row.get("title") or "Untitled"
    url      = row.get("url") or ""
    authors  = json.loads(row["authors"]) if row.get("authors") else []
    year     = row.get("year")
    journal  = row.get("journal") or row.get("source") or ""
    year_str = str(year) if year else "n.d."

    if format == "bibtex":
        content = (
            f"@article{{scholara:{history_id},\n"
            f"  title   = {{{title}}},\n"
            f"  author  = {{{' and '.join(authors) if authors else 'Unknown'}}},\n"
            f"  year    = {{{year_str}}},\n"
            f"  journal = {{{journal}}},\n"
            f"  url     = {{{url}}}\n"
            f"}}"
        )
        return Response(content=content, media_type="text/plain",
                        headers={"Content-Disposition": f"attachment; filename=scholara_{history_id}.bib"})

    if format == "ris":
        lines = ["TY  - JOUR", f"TI  - {title}"]
        for a in authors:
            lines.append(f"AU  - {a}")
        if year:
            lines.append(f"PY  - {year}")
        if journal:
            lines.append(f"JF  - {journal}")
        if url:
            lines.append(f"UR  - {url}")
        lines.append("ER  -")
        content = "\n".join(lines)
        return Response(content=content, media_type="application/x-research-info-systems",
                        headers={"Content-Disposition": f"attachment; filename=scholara_{history_id}.ris"})

    if format == "apa":
        author_str = ", ".join(authors) if authors else "Unknown"
        content    = f"{author_str} ({year_str}). {title}. {journal}. {url}"
        return Response(content=content, media_type="text/plain")

    raise HTTPException(400, f"Unknown format '{format}'. Use bibtex, ris, or apa.")
