from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from auth.dependencies import get_current_user
from services.search import aggregate_search, detect_lang, search_source, get_ai_router
from services.rate_limit import apply as rate_limit
from config.settings import AIConfig

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    query:   str
    sources: list[str] = ["arxiv", "gutenberg", "doaj", "openalex", "archive"]
    limit:   int = 50
    lang:    str = ""


_MESSAGES = {
    "no_query": {
        "en": "No query provided.",
        "fr": "Aucune requête fournie.",
    },
}


def _get_lang(request: Request) -> str:
    return request.headers.get("Accept-Language", "en")[:2].lower()


def _msg(key: str, lang: str) -> str:
    return _MESSAGES.get(key, {}).get(lang) or _MESSAGES.get(key, {}).get("en") or key


@router.post("/search")
def search(req: SearchRequest, user: dict = Depends(get_current_user)):
    lang = req.lang or detect_lang(req.query)
    return aggregate_search(req.query, req.sources, req.limit, lang)


@router.post("/nl_search")
async def nl_search(request: Request, user: dict = Depends(get_current_user)):
    rate_limit(request, user)
    body       = await request.json()
    user_query = body.get("text", body.get("query", ""))
    lang       = _get_lang(request)

    if not user_query:
        return {"error": _msg("no_query", lang), "results": []}

    router_svc = get_ai_router()
    routing    = await router_svc.route(user_query)

    if not routing.get("sources"):
        return {"routing": routing, "results": [], "message": "No sources selected."}

    query_lang = detect_lang(user_query)
    results    = []
    for source in routing["sources"]:
        query = routing.get("queries", {}).get(source, user_query)
        results.extend(search_source(source, query, lang=query_lang))

    results.sort(key=lambda r: 0 if (r.get("language") or "").lower() == query_lang else 1)

    return {
        "success":       True,
        "routing":       routing,
        "results":       results[:50],
        "ai_backend":    AIConfig.BACKEND,
        "detected_lang": query_lang,
    }
