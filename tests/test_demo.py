"""Tests for /api/extract and /api/demo endpoints."""
import io
import json
import struct
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_client(temp_db):
    from fastapi.testclient import TestClient
    import app as application
    from auth.dependencies import get_current_user
    application.app.dependency_overrides[get_current_user] = lambda: {
        "id": 1, "email": "u@x.com", "role": "admin", "institution_id": None
    }
    return TestClient(application.app)


def _minimal_pdf(text: str = "Hello world.") -> bytes:
    """Build the smallest valid PDF that pypdf can read."""
    body  = f"%PDF-1.4\n"
    body += "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    body += "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    body += f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
    body += "   /Contents 4 0 R /Resources << >> >>\nendobj\n"
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    body += f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj\n"
    xref_offset = len(body.encode())
    body += "xref\n0 5\n"
    body += "0000000000 65535 f \n" * 5
    body += f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    return body.encode()


def _minimal_txt(text: str = "This is a test document.") -> bytes:
    return text.encode()


# ─── Phase 1: /api/extract ────────────────────────────────────────────────────

class TestExtractEndpoint:

    def test_extract_txt_from_file(self, temp_db, tmp_path, monkeypatch):
        dl = tmp_path / "downloads"
        dl.mkdir()
        (dl / "test.txt").write_bytes(_minimal_txt("Quantum computing is fascinating."))
        monkeypatch.setattr("routers.extract.get_download_dir", lambda: dl)
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"filename": "test.txt"})
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "filename"
        assert data["filename"] == "test.txt"
        assert len(data["chunks"]) >= 1
        assert "Quantum" in data["chunks"][0]["text"]

    def test_extract_manual_text(self, temp_db):
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"text": "This is a short test passage about machine learning."})
        assert r.status_code == 200
        data = r.json()
        assert data["source"] == "manual"
        assert data["filename"] is None
        assert len(data["chunks"]) >= 1

    def test_path_traversal_rejected(self, temp_db):
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"filename": "../etc/passwd"})
        assert r.status_code == 400

    def test_path_traversal_abs_rejected(self, temp_db):
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"filename": "/etc/passwd"})
        assert r.status_code == 400

    def test_file_not_found_returns_404(self, temp_db, tmp_path, monkeypatch):
        dl = tmp_path / "downloads"
        dl.mkdir()
        monkeypatch.setattr("routers.extract.get_download_dir", lambda: dl)
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"filename": "missing.txt"})
        assert r.status_code == 404

    def test_unsupported_extension_rejected(self, temp_db, tmp_path, monkeypatch):
        dl = tmp_path / "downloads"
        dl.mkdir()
        (dl / "archive.zip").write_bytes(b"PK\x03\x04")
        monkeypatch.setattr("routers.extract.get_download_dir", lambda: dl)
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"filename": "archive.zip"})
        assert r.status_code == 400

    def test_missing_both_filename_and_text(self, temp_db):
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={})
        assert r.status_code == 400

    def test_text_too_long_rejected(self, temp_db):
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"text": "x" * 50_001})
        assert r.status_code == 413

    def test_chunking_respects_max_chars(self, temp_db):
        client = _make_client(temp_db)
        big = "This is a sentence about science. " * 500  # ~17 000 chars
        r = client.post("/api/extract", json={"text": big, "max_chars": 4000})
        assert r.status_code == 200
        data = r.json()
        assert len(data["chunks"]) <= 2  # ceil(4000/2000) = 2

    def test_extract_md_file(self, temp_db, tmp_path, monkeypatch):
        dl = tmp_path / "downloads"
        dl.mkdir()
        (dl / "notes.md").write_bytes(b"# Title\n\nSome **bold** text here.")
        monkeypatch.setattr("routers.extract.get_download_dir", lambda: dl)
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"filename": "notes.md"})
        assert r.status_code == 200
        assert r.json()["chunks"][0]["text"]

    def test_response_shape(self, temp_db):
        from services.rate_limit import reset
        reset()
        client = _make_client(temp_db)
        r = client.post("/api/extract", json={"text": "Short but valid test content here."})
        assert r.status_code == 200
        data = r.json()
        assert {"source", "filename", "total_chars", "chunks", "truncated"} <= data.keys()
        assert isinstance(data["chunks"], list)
        assert all({"index", "offset", "text"} <= set(c.keys()) for c in data["chunks"])


# ─── Phase 2: /api/demo ───────────────────────────────────────────────────────

class TestDemoEndpoint:

    def _post(self, client, payload):
        return client.post("/api/demo", json=payload)

    def test_explain_with_mocked_ollama(self, temp_db):
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value="Plain explanation.")):
            r = self._post(client, {"action": "explain", "text": "Quantum entanglement is a physical phenomenon.", "language": "en"})
        assert r.status_code == 200
        data = r.json()
        assert data["action"] == "explain"
        assert "result" in data
        assert data["backend_used"] == "ollama"

    def test_summary_action(self, temp_db):
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value="Summary here.")):
            r = self._post(client, {"action": "summary", "text": "Long academic content " * 20, "language": "en"})
        assert r.status_code == 200
        assert r.json()["action"] == "summary"

    def test_chat_with_history(self, temp_db):
        client = _make_client(temp_db)
        history = [{"role": "user", "content": "What is this about?"},
                   {"role": "assistant", "content": "It is about machine learning."}]
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value="Follow-up answer.")):
            r = self._post(client, {
                "action": "chat", "text": "ML transforms data into models.",
                "message": "What does it transform?", "history": history, "language": "en"
            })
        assert r.status_code == 200
        assert r.json()["result"] == "Follow-up answer."

    def test_presentation_parses_json_slides(self, temp_db):
        slides_json = json.dumps([
            {"slide": 1, "title": "Intro", "bullets": ["Point A", "Point B"]},
            {"slide": 2, "title": "Methods", "bullets": ["Step 1"]}
        ])
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value=slides_json)):
            r = self._post(client, {"action": "presentation", "text": "Academic content.", "language": "en"})
        assert r.status_code == 200
        data = r.json()
        assert data["parse_error"] is False
        assert len(data["slides"]) == 2
        assert data["slides"][0]["title"] == "Intro"

    def test_presentation_handles_parse_error(self, temp_db):
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value="not valid json {")):
            r = self._post(client, {"action": "presentation", "text": "Content.", "language": "en"})
        assert r.status_code == 200
        data = r.json()
        assert data["parse_error"] is True
        assert data["slides"] == []

    def test_flowchart_returns_mermaid(self, temp_db):
        mermaid = "flowchart TD\n  A --> B\n  B --> C"
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value=mermaid)):
            r = self._post(client, {"action": "flowchart", "text": "A causes B which leads to C.", "language": "en"})
        assert r.status_code == 200
        assert "flowchart" in r.json()["result"]

    def test_text_too_long_returns_413(self, temp_db):
        client = _make_client(temp_db)
        r = self._post(client, {"action": "explain", "text": "x" * 12_001, "language": "en"})
        assert r.status_code == 413

    def test_invalid_action_returns_400(self, temp_db):
        client = _make_client(temp_db)
        r = self._post(client, {"action": "magic", "text": "Some text.", "language": "en"})
        assert r.status_code == 400

    def test_fallback_when_no_ai(self, temp_db):
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value=None)), \
             patch("routers.demo._call_deepseek", new=AsyncMock(return_value=None)):
            r = self._post(client, {"action": "explain", "text": "Some text.", "language": "en"})
        assert r.status_code == 200
        data = r.json()
        assert data["backend_used"] == "fallback"
        assert "unavailable" in data["result"].lower()

    def test_french_language_accepted(self, temp_db):
        client = _make_client(temp_db)
        with patch("routers.demo._call_ollama", new=AsyncMock(return_value="Explication en français.")):
            r = self._post(client, {"action": "explain", "text": "Contenu académique.", "language": "fr"})
        assert r.status_code == 200


class TestRateLimit:

    def test_extract_rate_limit_returns_429(self, temp_db):
        from services.rate_limit import reset
        reset()
        client = _make_client(temp_db)
        # 10/min limit — exhaust it
        for _ in range(10):
            client.post("/api/extract", json={"text": "short passage for rate limit test"})
        r = client.post("/api/extract", json={"text": "one more"})
        assert r.status_code == 429
        assert "rate limit" in r.json()["detail"].lower()
        reset()

    def test_demo_rate_limit_returns_429(self, temp_db):
        from services.rate_limit import reset
        reset()
        client = _make_client(temp_db)
        # /api/demo uses the global apply() limiter: 30 req/min in single_user
        for _ in range(30):
            client.post("/api/demo", json={"action": "explain", "text": "x", "language": "en"})
        r = client.post("/api/demo", json={"action": "explain", "text": "x", "language": "en"})
        assert r.status_code == 429
        reset()
