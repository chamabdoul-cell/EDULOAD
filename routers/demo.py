"""POST /api/demo — AI-powered actions on selected text/documents."""
import json
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth.dependencies import get_current_user
from config.settings import AIConfig
from services.audit import record_usage
from services.rate_limit import check as rl_check

router = APIRouter(prefix="/api", tags=["demo"])

DEEPSEEK_URL  = "https://api.deepseek.com/chat/completions"
_PROMPT_DIR   = Path("prompts/demo")
_VALID_ACTIONS = {"explain", "summary", "chat", "presentation", "flowchart"}
_CANNED_MSG   = "AI backend unavailable. Please start Ollama or configure a DeepSeek API key."


class DemoRequest(BaseModel):
    action:   str
    text:     str
    message:  Optional[str] = None
    history:  Optional[list[dict]] = None
    language: str = "en"


def _load_prompt(action: str) -> str:
    p = _PROMPT_DIR / f"{action}.txt"
    return p.read_text() if p.exists() else "{text}"


def _build_prompt(action: str, text: str, language: str,
                  message: str = "", history: list | None = None) -> str:
    tpl = _load_prompt(action)
    # Replace named placeholders manually to avoid conflicts with JSON curly braces
    result = tpl.replace("{text}", text)
    result = result.replace("{language}", language)
    result = result.replace("{message}", message or "")
    return result.strip()


def _history_to_str(history: list[dict]) -> str:
    lines = []
    for turn in history[-6:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        lines.append(f"{role.capitalize()}: {content}")
    return "\n".join(lines)


def _rate_key(request: Request, user: dict) -> str:
    if AIConfig.is_multi_user():
        return f"demo:user:{user['id']}"
    host = (request.client.host if request.client else None) or "unknown"
    return f"demo:ip:{host}"


async def _call_ollama(prompt: str, history: list | None, action: str) -> str | None:
    messages = []
    if history and action == "chat":
        # Concatenate history into prompt for Ollama (single-turn generate endpoint)
        history_str = _history_to_str(history)
        prompt = history_str + "\n\n" + prompt
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{AIConfig.OLLAMA_URL}/api/generate",
                json={"model": AIConfig.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
        return resp.json().get("response", "").strip() or None
    except Exception:
        return None


async def _call_deepseek(prompt: str, history: list | None, action: str) -> str | None:
    messages = []
    if history and action == "chat":
        for turn in history[-6:]:
            messages.append({"role": turn.get("role", "user"),
                             "content": turn.get("content", "")})
    messages.append({"role": "user", "content": prompt})
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {AIConfig.DEEPSEEK_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": messages, "max_tokens": 1200},
            )
        return resp.json()["choices"][0]["message"]["content"].strip() or None
    except Exception:
        return None


async def _ai_call(prompt: str, history: list | None, action: str) -> tuple[str, str]:
    """Returns (text, backend_used)."""
    if AIConfig.BACKEND in ("ollama", "auto"):
        raw = await _call_ollama(prompt, history, action)
        if raw:
            return raw, "ollama"

    if AIConfig.DEEPSEEK_API_KEY and AIConfig.BACKEND in ("deepseek", "auto"):
        raw = await _call_deepseek(prompt, history, action)
        if raw:
            return raw, "deepseek"

    return _CANNED_MSG, "fallback"


@router.post("/demo")
async def demo(req: DemoRequest, request: Request,
               user: dict = Depends(get_current_user)):
    if req.action not in _VALID_ACTIONS:
        raise HTTPException(400, f"Invalid action. Must be one of: {', '.join(_VALID_ACTIONS)}")

    # Text length cap (Phase 5 guard also enforced here)
    if len(req.text) > 12_000:
        raise HTTPException(413, "text exceeds 12 000 character limit")

    # Rate limit: 20/min
    key = _rate_key(request, user)
    if not rl_check(key, limit=20, window_secs=60):
        raise HTTPException(429, "Rate limit exceeded — 20 demo requests/min")

    prompt = _build_prompt(req.action, req.text, req.language,
                           message=req.message or "", history=req.history)
    raw, backend = await _ai_call(prompt, req.history, req.action)

    record_usage(user["id"], "/api/demo")

    response: dict = {"action": req.action, "backend_used": backend}

    if req.action == "presentation":
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[:-1])
        try:
            slides = json.loads(cleaned.strip())
            response["result"] = raw
            response["slides"] = slides
            response["parse_error"] = False
        except Exception:
            response["result"] = raw
            response["slides"] = []
            response["parse_error"] = True
    elif req.action == "flowchart":
        response["result"] = raw
    else:
        response["result"] = raw

    return response
