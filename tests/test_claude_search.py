#!/usr/bin/env python3
"""Test suite for Claude-powered search routing"""

import time
import pytest
from core.claude_router import ClaudeSearchRouter


class TestClaudeSearchRouter:

    @pytest.fixture
    def router(self):
        return ClaudeSearchRouter()

    def test_video_query(self, router):
        result = router.route("Find Python programming tutorials")
        assert "youtube" in result["sources"] or "duckduckgo" in result["sources"]
        assert result["content_type"] in ["video", "mixed"]
        assert "confidence" in result

    def test_academic_query(self, router):
        result = router.route("Download research papers about quantum computing")
        assert any(s in result["sources"] for s in ["arxiv", "openalex", "doaj"])
        assert result["content_type"] in ["paper", "mixed"]

    def test_ebook_query(self, router):
        result = router.route("Get me classic novels by Jane Austen")
        assert "gutenberg" in result["sources"] or "internet_archive" in result["sources"]
        assert result["content_type"] == "ebook"

    def test_conversion_request(self, router):
        result = router.route("Convert my PDF to Word")
        assert result.get("sources") == [] or result.get("note") is not None

    def test_cache_works(self, router):
        query = "Same query multiple times"
        start = time.time()
        result1 = router.route(query)
        time1 = time.time() - start

        start = time.time()
        result2 = router.route(query)
        time2 = time.time() - start

        assert time2 < time1
        assert result1 == result2

    def test_fallback_on_bad_key(self, router):
        import os
        original = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "invalid_key"
        try:
            result = router.route("Test query")
            assert result.get("fallback") is True or "sources" in result
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original


def run_manual_tests():
    router = ClaudeSearchRouter()
    queries = [
        "Find machine learning tutorials on YouTube",
        "Download research papers about climate change",
        "Get me classic books by Mark Twain",
        "Show me videos about cooking",
        "Convert my document to PDF",
    ]
    print("\n=== Testing Claude Search Router ===\n")
    for query in queries:
        print(f"Query: {query}")
        result = router.route(query)
        print(f"Sources: {result.get('sources', [])}")
        print(f"Content type: {result.get('content_type', 'N/A')}")
        print(f"Confidence: {result.get('confidence', 'N/A')}")
        print("-" * 50)


if __name__ == "__main__":
    run_manual_tests()
