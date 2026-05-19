"""Phase 3 tests — conversion sandboxing.

Written BEFORE implementation (TDD for security-critical changes).
Tests each of the five hardening measures independently via the
module-level helper functions, then an integration smoke test.
"""
import time
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# 1. Path traversal prevention
# ══════════════════════════════════════════════════════════════════════════════

class TestPathTraversal:

    def test_rejects_dotdot_sequence(self, tmp_path):
        from services.convert import _check_path
        with pytest.raises(HTTPException) as exc:
            _check_path("../secrets.txt", tmp_path)
        assert exc.value.status_code == 400

    def test_rejects_nested_dotdot(self, tmp_path):
        from services.convert import _check_path
        with pytest.raises(HTTPException) as exc:
            _check_path("subdir/../../etc/passwd", tmp_path)
        assert exc.value.status_code == 400

    def test_rejects_absolute_path(self, tmp_path):
        from services.convert import _check_path
        with pytest.raises(HTTPException) as exc:
            _check_path("/etc/passwd", tmp_path)
        assert exc.value.status_code == 400

    def test_accepts_valid_filename(self, tmp_path):
        from services.convert import _check_path
        f = tmp_path / "paper.pdf"
        f.write_bytes(b"%PDF-1.4")
        result = _check_path("paper.pdf", tmp_path)
        assert result == f.resolve()

    def test_accepted_path_is_within_dl_dir(self, tmp_path):
        from services.convert import _check_path
        f = tmp_path / "thesis.pdf"
        f.write_bytes(b"%PDF-1.4")
        result = _check_path("thesis.pdf", tmp_path)
        result.relative_to(tmp_path.resolve())  # must not raise ValueError


# ══════════════════════════════════════════════════════════════════════════════
# 2. File size limit
# ══════════════════════════════════════════════════════════════════════════════

class TestFileSizeLimit:

    def test_rejects_file_over_limit(self, tmp_path, monkeypatch):
        import services.convert as conv
        monkeypatch.setattr(conv, "MAX_CONVERT_SIZE_MB", 0.001)  # ~1 KB limit
        f = tmp_path / "big.txt"
        f.write_bytes(b"x" * 2048)  # 2 KB
        with pytest.raises(HTTPException) as exc:
            conv._check_size(f)
        assert exc.value.status_code == 413

    def test_accepts_file_under_limit(self, tmp_path, monkeypatch):
        import services.convert as conv
        monkeypatch.setattr(conv, "MAX_CONVERT_SIZE_MB", 1)
        f = tmp_path / "small.txt"
        f.write_bytes(b"hello world")
        conv._check_size(f)  # must not raise

    def test_413_message_mentions_size(self, tmp_path, monkeypatch):
        import services.convert as conv
        monkeypatch.setattr(conv, "MAX_CONVERT_SIZE_MB", 0.001)
        f = tmp_path / "big.txt"
        f.write_bytes(b"x" * 2048)
        with pytest.raises(HTTPException) as exc:
            conv._check_size(f)
        assert "MB" in exc.value.detail


# ══════════════════════════════════════════════════════════════════════════════
# 3. MIME / magic-byte validation
# ══════════════════════════════════════════════════════════════════════════════

class TestMimeValidation:

    def test_rejects_pdf_extension_with_zip_magic(self, tmp_path):
        from services.convert import _check_mime
        f = tmp_path / "fake.pdf"
        f.write_bytes(b"PK\x03\x04" + b"\x00" * 20)  # ZIP header, not PDF
        with pytest.raises(HTTPException) as exc:
            _check_mime(f)
        assert exc.value.status_code == 415

    def test_accepts_valid_pdf_magic(self, tmp_path):
        from services.convert import _check_mime
        f = tmp_path / "real.pdf"
        f.write_bytes(b"%PDF-1.4\n%fake content")
        _check_mime(f)  # must not raise

    def test_accepts_valid_docx_magic(self, tmp_path):
        from services.convert import _check_mime
        f = tmp_path / "doc.docx"
        f.write_bytes(b"PK\x03\x04" + b"\x00" * 20)  # ZIP header is valid for DOCX
        _check_mime(f)  # must not raise

    def test_skips_check_for_txt(self, tmp_path):
        """txt has no magic-byte definition — any content is accepted."""
        from services.convert import _check_mime
        f = tmp_path / "data.txt"
        f.write_bytes(b"PK\x03\x04 this is not a zip really")
        _check_mime(f)  # must not raise

    def test_skips_check_for_md(self, tmp_path):
        from services.convert import _check_mime
        f = tmp_path / "readme.md"
        f.write_bytes(b"\x00\x01\x02 binary garbage")
        _check_mime(f)  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# 4. Timeout enforcement
# ══════════════════════════════════════════════════════════════════════════════

class TestTimeoutEnforcement:

    def test_timeout_call_returns_result_normally(self):
        from services.convert import _timeout_call
        result = _timeout_call(lambda: 42)
        assert result == 42

    def test_timeout_call_raises_504_on_timeout(self, monkeypatch):
        import services.convert as conv
        monkeypatch.setattr(conv, "CONVERT_TIMEOUT", 0.05)  # 50 ms
        from services.convert import _timeout_call

        def slow():
            time.sleep(5)

        with pytest.raises(HTTPException) as exc:
            _timeout_call(slow)
        assert exc.value.status_code == 504

    def test_timeout_call_propagates_http_exception(self):
        from services.convert import _timeout_call

        def boom():
            raise HTTPException(400, "bad format")

        with pytest.raises(HTTPException) as exc:
            _timeout_call(boom)
        assert exc.value.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 5. Temp-directory isolation — output lands in dl_dir, not a temp location
# ══════════════════════════════════════════════════════════════════════════════

class TestTempDirIsolation:

    def test_txt_to_html_output_is_in_dl_dir(self, tmp_path):
        from services.convert import do_convert
        src = tmp_path / "note.txt"
        src.write_text("Hello, Scholara!")
        out = do_convert("note.txt", "html", tmp_path)
        assert (tmp_path / out).exists()
        assert (tmp_path / out).parent == tmp_path

    def test_output_name_matches_expected_stem(self, tmp_path):
        from services.convert import do_convert
        src = tmp_path / "paper.txt"
        src.write_text("Abstract: ...")
        out = do_convert("paper.txt", "html", tmp_path)
        assert out == "paper_converted.html"

    def test_do_convert_rejects_missing_file(self, tmp_path):
        from services.convert import do_convert
        with pytest.raises(HTTPException) as exc:
            do_convert("nonexistent.txt", "html", tmp_path)
        assert exc.value.status_code == 404

    def test_do_convert_rejects_path_traversal(self, tmp_path):
        from services.convert import do_convert
        with pytest.raises(HTTPException) as exc:
            do_convert("../etc/passwd", "txt", tmp_path)
        assert exc.value.status_code == 400
