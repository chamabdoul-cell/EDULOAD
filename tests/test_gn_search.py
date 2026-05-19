"""Smoke tests for Global North search functions."""
import pytest
from unittest.mock import patch, MagicMock

from services.search import (
    _search_semantic_scholar,
    _search_pubmed,
    _search_crossref,
    _search_core,
    _search_base,
)

REQUIRED_KEYS = {"title", "authors", "snippet", "url", "source", "icon"}


def _mock_response(json_data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def _assert_shape(results: list, source_key: str):
    assert isinstance(results, list)
    assert len(results) > 0
    for item in results:
        for key in REQUIRED_KEYS:
            assert key in item, f"Missing key '{key}' in {source_key} result"
        assert item["source"] == source_key


class TestSemanticScholar:

    def test_result_shape(self):
        payload = {
            "data": [{
                "paperId": "abc123",
                "title": "Test Paper",
                "authors": [{"name": "Alice"}],
                "abstract": "An abstract.",
                "year": 2023,
                "journal": {"name": "Nature"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
            }]
        }
        with patch("services.search.requests.get", return_value=_mock_response(payload)):
            results = _search_semantic_scholar("machine learning", 1)
        _assert_shape(results, "semantic_scholar")
        assert results[0]["title"] == "Test Paper"
        assert results[0]["pdf_url"] == "https://example.com/paper.pdf"


class TestPubMed:

    def test_result_shape(self):
        search_payload = {"esearchresult": {"idlist": ["12345"]}}
        summary_payload = {
            "result": {
                "12345": {
                    "title": "PubMed Paper",
                    "authors": [{"name": "Bob"}],
                    "pubdate": "2022",
                    "fulljournalname": "The Lancet",
                }
            }
        }
        responses = [_mock_response(search_payload), _mock_response(summary_payload)]
        with patch("services.search.requests.get", side_effect=responses):
            results = _search_pubmed("cancer treatment", 1)
        _assert_shape(results, "pubmed")
        assert results[0]["title"] == "PubMed Paper"


class TestCrossRef:

    def test_result_shape(self):
        payload = {
            "message": {
                "items": [{
                    "title": ["CrossRef Paper"],
                    "author": [{"given": "Carol", "family": "Smith"}],
                    "abstract": "Abstract text.",
                    "DOI": "10.1000/xyz123",
                    "published": {"date-parts": [[2021]]},
                    "container-title": ["Science"],
                }]
            }
        }
        with patch("services.search.requests.get", return_value=_mock_response(payload)):
            results = _search_crossref("climate change", 1)
        _assert_shape(results, "crossref")
        assert results[0]["title"] == "CrossRef Paper"
        assert "doi.org" in results[0]["url"]


class TestCORE:

    def test_returns_empty_without_api_key(self):
        from config.settings import AIConfig
        with patch.object(AIConfig, "CORE_API_KEY", ""):
            results = _search_core("education", 5)
        assert results == []

    def test_result_shape_with_key(self):
        from config.settings import AIConfig
        payload = {
            "results": [{
                "title": "CORE Paper",
                "authors": [{"name": "Dave"}],
                "abstract": "Summary.",
                "downloadUrl": "https://core.ac.uk/download/pdf/1.pdf",
                "yearPublished": 2020,
                "publisher": "Elsevier",
            }]
        }
        with patch.object(AIConfig, "CORE_API_KEY", "test-key"), \
             patch("services.search.requests.get", return_value=_mock_response(payload)):
            results = _search_core("open access", 1)
        _assert_shape(results, "core")
        assert results[0]["title"] == "CORE Paper"


class TestBASE:

    def test_result_shape(self):
        payload = {
            "response": {
                "docs": [{
                    "dctitle": ["BASE Paper"],
                    "dccreator": ["Eve Johnson"],
                    "dcdescription": ["Some description about research."],
                    "dcidentifier": ["https://base-search.net/doc/1"],
                    "dcdate": ["2019"],
                }]
            }
        }
        with patch("services.search.requests.get", return_value=_mock_response(payload)):
            results = _search_base("sociology", 1)
        _assert_shape(results, "base")
        assert results[0]["title"] == "BASE Paper"
