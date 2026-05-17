"""AI-powered search router: Ollama (local) → DeepSeek (cloud) → keyword fallback."""
import json
import re
from pathlib import Path

import httpx

from config.settings import AIConfig
from core.fallback import fallback_routing
from utils.cache import ResponseCache

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
_SYSTEM_PROMPT_PATH = Path("prompts/router_system.txt")


def _build_prompt(user_query: str) -> str:
    system = _SYSTEM_PROMPT_PATH.read_text() if _SYSTEM_PROMPT_PATH.exists() else ""
    return (
        f"{system}\n\n"
        f"User query: {user_query}\n\n"
        "Output JSON only, wrapped in <output>...</output> tags."
    )


def _parse_routing(raw: str) -> dict:
    if "<output>" in raw:
        m = re.search(r"<output>(.*?)</output>", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    try:
        return json.loads(raw.strip())
    except Exception:
        return {}


class AISearchRouter:
    def __init__(self):
        self.cache = ResponseCache(ttl=AIConfig.CACHE_TTL)

    async def route(self, user_query: str) -> dict:
        cache_key = user_query.lower().strip()
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        result = None

        if AIConfig.BACKEND in ("ollama", "auto"):
            result = await self._route_ollama(user_query)

        if not result and AIConfig.DEEPSEEK_API_KEY and AIConfig.BACKEND in ("deepseek", "auto"):
            result = await self._route_deepseek(user_query)

        if not result:
            result = fallback_routing(user_query)

        self.cache.set(cache_key, result)
        return result

    async def _route_ollama(self, user_query: str) -> dict | None:
        prompt = _build_prompt(user_query)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{AIConfig.OLLAMA_URL}/api/generate",
                    json={"model": AIConfig.OLLAMA_MODEL, "prompt": prompt, "stream": False},
                )
            raw = resp.json().get("response", "")
            result = _parse_routing(raw)
            return result if result.get("sources") else None
        except Exception:
            return None

    async def _route_deepseek(self, user_query: str) -> dict | None:
        prompt = _build_prompt(user_query)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    DEEPSEEK_URL,
                    headers={
                        "Authorization": f"Bearer {AIConfig.DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 300,
                    },
                )
            raw = resp.json()["choices"][0]["message"]["content"]
            result = _parse_routing(raw)
            return result if result.get("sources") else None
        except Exception:
            return None
