#!/usr/bin/env python3
"""Tests for keyword-based fallback routing"""

import pytest
from core.fallback import fallback_routing


class TestFallbackRouting:

    def test_video_keywords(self):
        for kw in ["video", "watch", "youtube", "tutorial", "course"]:
            result = fallback_routing(f"I want to {kw} something")
            assert "youtube" in result["sources"]
            assert result["fallback"] is True

    def test_academic_keywords(self):
        for kw in ["paper", "research", "study", "arxiv", "academic"]:
            result = fallback_routing(f"Find a {kw} on ML")
            assert "arxiv" in result["sources"]

    def test_book_keywords(self):
        for kw in ["book", "novel", "read", "gutenberg", "classic"]:
            result = fallback_routing(f"Get me a {kw}")
            assert "gutenberg" in result["sources"]

    def test_unknown_query_defaults_to_duckduckgo(self):
        result = fallback_routing("something completely unrelated")
        assert result["sources"] == ["duckduckgo"]
        assert "duckduckgo" in result["queries"]

    def test_result_structure(self):
        result = fallback_routing("any query")
        assert "sources" in result
        assert "queries" in result
        assert "content_type" in result
        assert "confidence" in result
        assert result["confidence"] == "low"
        assert result["fallback"] is True

    def test_queries_match_sources(self):
        result = fallback_routing("watch a tutorial video")
        for source in result["sources"]:
            assert source in result["queries"]
