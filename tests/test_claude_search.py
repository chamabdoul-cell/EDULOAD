"""Tests for AI-powered search routing."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from core.ai_router import AISearchRouter, _parse_routing
from core.fallback import fallback_routing


class TestParseRouting:

    def test_parses_valid_json(self):
        raw = '{"sources": ["arxiv"], "queries": {"arxiv": "q"}, "confidence": "high"}'
        result = _parse_routing(raw)
        assert result["sources"] == ["arxiv"]

    def test_parses_xml_wrapped_json(self):
        raw = '<output>{"sources": ["doaj"], "confidence": "medium"}</output>'
        result = _parse_routing(raw)
        assert result["sources"] == ["doaj"]

    def test_returns_empty_on_bad_input(self):
        result = _parse_routing("not json at all")
        assert result == {}


class TestFallbackRouting:

    def test_academic_keywords_trigger_arxiv(self):
        result = fallback_routing("research paper on transformers")
        assert "arxiv" in result["sources"]

    def test_book_keywords_trigger_gutenberg(self):
        result = fallback_routing("classic novel by Balzac")
        assert "gutenberg" in result["sources"]

    def test_unknown_query_defaults_to_arxiv_openalex(self):
        result = fallback_routing("some random query")
        assert "arxiv" in result["sources"] or "openalex" in result["sources"]

    def test_fallback_flag_is_set(self):
        result = fallback_routing("any query")
        assert result["fallback"] is True

    def test_french_query_triggers_hal(self):
        result = fallback_routing("recherche sur les transformeurs en apprentissage automatique")
        assert "hal" in result["sources"]
        assert result["query_language"] == "fr"

    def test_french_accents_detected(self):
        result = fallback_routing("étude sur l'économie africaine")
        assert result["query_language"] == "fr"
        assert "hal" in result["sources"]

    def test_french_humanities_triggers_persee_openedition(self):
        result = fallback_routing("histoire de la société française au 19ème siècle")
        assert "persee" in result["sources"] or "openedition" in result["sources"]

    def test_french_quebec_triggers_erudit(self):
        result = fallback_routing("sociologie québécoise contemporaine")
        assert "erudit" in result["sources"]

    def test_english_query_language_is_en(self):
        result = fallback_routing("machine learning neural networks")
        assert result["query_language"] == "en"


class TestAISearchRouter:

    def test_router_falls_back_to_keyword(self):
        router = AISearchRouter()
        # With no Ollama and no DeepSeek key, should fall back
        with patch.object(router, "_route_ollama", new=AsyncMock(return_value=None)):
            with patch.object(router, "_route_deepseek", new=AsyncMock(return_value=None)):
                result = asyncio.get_event_loop().run_until_complete(
                    router.route("research paper on transformers")
                )
        assert "sources" in result
        assert result["fallback"] is True

    def test_router_uses_ollama_when_available(self):
        router = AISearchRouter()
        mock_result = {"sources": ["arxiv"], "queries": {"arxiv": "transformers"}, "confidence": "high"}
        with patch.object(router, "_route_ollama", new=AsyncMock(return_value=mock_result)):
            result = asyncio.get_event_loop().run_until_complete(
                router.route("research paper on transformers")
            )
        assert result["sources"] == ["arxiv"]

    def test_router_caches_results(self):
        router = AISearchRouter()
        mock_result = {"sources": ["openalex"], "queries": {}, "confidence": "high"}
        call_count = 0

        async def mock_ollama(q):
            nonlocal call_count
            call_count += 1
            return mock_result

        with patch.object(router, "_route_ollama", side_effect=mock_ollama):
            asyncio.get_event_loop().run_until_complete(router.route("same query"))
            asyncio.get_event_loop().run_until_complete(router.route("same query"))

        assert call_count == 1  # second call should hit cache
