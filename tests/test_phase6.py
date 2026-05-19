"""Phase 6 tests — search deduplication, reranking, and response headers.

TDD: all tests written before implementation.
"""
import datetime
import pytest


# ══════════════════════════════════════════════════════════════════════════════
# 1. Title normalisation helper
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeTitle:

    def test_lowercases(self):
        from services.search import _normalize_title
        assert _normalize_title("Hello World") == "hello world"

    def test_strips_punctuation(self):
        from services.search import _normalize_title
        assert _normalize_title("Hello, World!") == "hello world"

    def test_empty_string(self):
        from services.search import _normalize_title
        assert _normalize_title("") == ""

    def test_none_returns_empty(self):
        from services.search import _normalize_title
        assert _normalize_title(None) == ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. Jaccard similarity
# ══════════════════════════════════════════════════════════════════════════════

class TestJaccard:

    def test_identical(self):
        from services.search import _jaccard, _title_tokens
        a = _title_tokens("deep learning for nlp")
        assert _jaccard(a, a) == 1.0

    def test_completely_different(self):
        from services.search import _jaccard, _title_tokens
        a = _title_tokens("deep learning")
        b = _title_tokens("quantum physics")
        assert _jaccard(a, b) == 0.0

    def test_partial_overlap(self):
        from services.search import _jaccard, _title_tokens
        a = _title_tokens("deep learning for image recognition")
        b = _title_tokens("deep learning for text recognition")
        j = _jaccard(a, b)
        assert 0.0 < j < 1.0

    def test_near_identical_above_threshold(self):
        from services.search import _jaccard, _title_tokens
        # Same title, just different punctuation — should be > 0.9
        a = _title_tokens("Transformers: Attention Is All You Need")
        b = _title_tokens("Transformers Attention Is All You Need")
        assert _jaccard(a, b) > 0.9

    def test_both_empty(self):
        from services.search import _jaccard
        assert _jaccard(frozenset(), frozenset()) == 1.0


# ══════════════════════════════════════════════════════════════════════════════
# 3. Deduplication
# ══════════════════════════════════════════════════════════════════════════════

class TestDeduplicate:

    def test_removes_doi_duplicates(self):
        from services.search import deduplicate
        results = [
            {"title": "Paper A", "doi": "10.1234/abc", "url": "http://a.com"},
            {"title": "Paper A (preprint)", "doi": "10.1234/abc", "url": "http://b.com"},
            {"title": "Paper B", "doi": "10.5678/xyz", "url": "http://c.com"},
        ]
        out, n_removed = deduplicate(results)
        assert n_removed == 1
        assert len(out) == 2

    def test_keeps_first_doi_occurrence(self):
        from services.search import deduplicate
        results = [
            {"title": "First",  "doi": "10.1/a"},
            {"title": "Second", "doi": "10.1/a"},
        ]
        out, _ = deduplicate(results)
        assert out[0]["title"] == "First"

    def test_removes_near_identical_titles(self):
        from services.search import deduplicate
        results = [
            {"title": "Attention Is All You Need", "doi": None},
            {"title": "Attention Is All You Need.", "doi": None},  # trailing dot
        ]
        out, n_removed = deduplicate(results)
        assert n_removed == 1
        assert len(out) == 1

    def test_keeps_different_titles(self):
        from services.search import deduplicate
        results = [
            {"title": "Paper on Neural Networks", "doi": None},
            {"title": "Introduction to Quantum Computing", "doi": None},
        ]
        out, n_removed = deduplicate(results)
        assert n_removed == 0
        assert len(out) == 2

    def test_empty_doi_not_treated_as_duplicate(self):
        from services.search import deduplicate
        results = [
            {"title": "Paper X", "doi": ""},
            {"title": "Paper Y", "doi": ""},
            {"title": "Paper Z", "doi": None},
        ]
        out, n_removed = deduplicate(results)
        # All have different titles — none should be deduped
        assert n_removed == 0

    def test_returns_count_of_removed(self):
        from services.search import deduplicate
        results = [
            {"title": "Same", "doi": "10.1/x"},
            {"title": "Same", "doi": "10.1/x"},
            {"title": "Same", "doi": "10.1/x"},
        ]
        _, n_removed = deduplicate(results)
        assert n_removed == 2


# ══════════════════════════════════════════════════════════════════════════════
# 4. Scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestScoring:

    def test_language_match_adds_3(self):
        from services.search import _score
        r = {"language": "fr", "doi": None, "abstract": None, "year": None}
        assert _score(r, "fr") == 3

    def test_language_mismatch_adds_0(self):
        from services.search import _score
        r = {"language": "en", "doi": None, "abstract": None, "year": None}
        assert _score(r, "fr") == 0

    def test_doi_adds_2(self):
        from services.search import _score
        r = {"language": "", "doi": "10.1/x", "abstract": None, "year": None}
        assert _score(r, "en") == 2

    def test_abstract_adds_2(self):
        from services.search import _score
        r = {"language": "", "doi": None, "abstract": "Some abstract text", "year": None}
        assert _score(r, "en") == 2

    def test_recent_year_adds_1(self):
        from services.search import _score
        recent = datetime.date.today().year - 2
        r = {"language": "", "doi": None, "abstract": None, "year": recent}
        assert _score(r, "en") == 1

    def test_old_year_adds_0(self):
        from services.search import _score
        old = datetime.date.today().year - 10
        r = {"language": "", "doi": None, "abstract": None, "year": old}
        assert _score(r, "en") == 0

    def test_open_access_adds_1(self):
        from services.search import _score
        r = {"language": "", "doi": None, "abstract": None, "year": None, "open_access": True}
        assert _score(r, "en") == 1

    def test_max_score_all_signals(self):
        from services.search import _score
        recent = datetime.date.today().year - 1
        r = {
            "language": "en", "doi": "10.1/x",
            "abstract": "An abstract", "year": recent, "open_access": True
        }
        assert _score(r, "en") == 3 + 2 + 2 + 1 + 1  # = 9


# ══════════════════════════════════════════════════════════════════════════════
# 5. Reranking
# ══════════════════════════════════════════════════════════════════════════════

class TestRerank:

    def test_highest_scored_first(self):
        from services.search import rerank
        results = [
            {"language": "", "doi": None, "abstract": None, "year": None, "title": "Low"},
            {"language": "en", "doi": "10.1/x", "abstract": "yes", "year": None, "title": "High"},
        ]
        ranked = rerank(results, "en")
        assert ranked[0]["title"] == "High"

    def test_preserves_all_results(self):
        from services.search import rerank
        results = [{"title": str(i), "language": "", "doi": None, "abstract": None, "year": None}
                   for i in range(10)]
        ranked = rerank(results, "en")
        assert len(ranked) == 10

    def test_stable_for_equal_scores(self):
        from services.search import rerank
        # Two items with identical fields — order should be deterministic (stable sort)
        results = [
            {"title": "A", "language": "en", "doi": "10.1/a", "abstract": None, "year": None},
            {"title": "B", "language": "en", "doi": "10.1/b", "abstract": None, "year": None},
        ]
        ranked = rerank(results, "en")
        assert len(ranked) == 2  # just checks it doesn't crash or lose items


# ══════════════════════════════════════════════════════════════════════════════
# 6. aggregate_search returns dedup/rerank counts
# ══════════════════════════════════════════════════════════════════════════════

class TestAggregateSearchCounts:

    def test_returns_deduped_count_key(self, monkeypatch):
        import services.search as svc
        monkeypatch.setattr(svc, "_build_source_map", lambda: {
            "arxiv": lambda q, n, **kw: [
                {"title": "Dup", "doi": "10.1/dup", "url": "a", "language": "en",
                 "abstract": None, "year": None},
                {"title": "Dup", "doi": "10.1/dup", "url": "b", "language": "en",
                 "abstract": None, "year": None},
                {"title": "Unique", "doi": "10.2/u", "url": "c", "language": "en",
                 "abstract": None, "year": None},
            ]
        })
        result = svc.aggregate_search("test", ["arxiv"], limit=10, lang="en")
        assert "_deduped_count" in result
        assert result["_deduped_count"] == 1

    def test_results_capped_at_limit(self, monkeypatch):
        import services.search as svc
        monkeypatch.setattr(svc, "_build_source_map", lambda: {
            "arxiv": lambda q, n, **kw: [
                {"title": f"Paper {i}", "doi": f"10.1/{i}", "url": f"http://x/{i}",
                 "language": "en", "abstract": None, "year": None}
                for i in range(30)
            ]
        })
        result = svc.aggregate_search("test", ["arxiv"], limit=5, lang="en")
        assert len(result["results"]) <= 5


# ══════════════════════════════════════════════════════════════════════════════
# 7. Response headers from the router
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchResponseHeaders:

    def _make_client(self):
        from fastapi.testclient import TestClient
        import app as application
        from auth.dependencies import get_current_user
        application.app.dependency_overrides[get_current_user] = lambda: {
            "id": 0, "email": "test@x.com", "role": "admin", "institution_id": None
        }
        return TestClient(application.app)

    def test_x_search_deduped_header_present(self, monkeypatch):
        import services.search as svc
        monkeypatch.setattr(svc, "aggregate_search", lambda q, s, limit, lang: {
            "results": [], "detected_lang": "en",
            "_deduped_count": 3, "_reranked_count": 0,
        })
        client = self._make_client()
        r = client.post("/api/search", json={"query": "test", "sources": ["arxiv"]})
        assert "x-search-deduped" in r.headers

    def test_x_search_reranked_header_present(self, monkeypatch):
        import services.search as svc
        monkeypatch.setattr(svc, "aggregate_search", lambda q, s, limit, lang: {
            "results": [], "detected_lang": "en",
            "_deduped_count": 0, "_reranked_count": 7,
        })
        client = self._make_client()
        r = client.post("/api/search", json={"query": "test", "sources": ["arxiv"]})
        assert "x-search-reranked" in r.headers
