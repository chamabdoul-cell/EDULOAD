"""Tests for the DirectDownloader."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.downloader import DirectDownloader, PerformanceMonitor


@pytest.fixture
def dl(tmp_path):
    return DirectDownloader(output_dir=str(tmp_path))


class TestPerformanceMonitor:

    def test_records_entry(self):
        m = PerformanceMonitor()
        m.record("direct", 3.5, True)
        stats = m.stats()
        assert "direct" in stats
        assert stats["direct"]["count"] == 1
        assert stats["direct"]["success_rate_pct"] == 100.0

    def test_failure_reduces_success_rate(self):
        m = PerformanceMonitor()
        m.record("direct", 1.0, True)
        m.record("direct", 1.0, False)
        assert m.stats()["direct"]["success_rate_pct"] == 50.0


class TestDirectDownloader:

    def test_get_stats_structure(self, dl):
        stats = dl.get_stats()
        for key in ("method_direct", "failed", "total_success", "success_rate"):
            assert key in stats

    def test_download_direct_success(self, dl):
        with patch("core.downloader.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-type": "application/pdf"}
            mock_resp.iter_content.return_value = [b"fake pdf content"]
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp
            result = dl._download_direct(
                "https://arxiv.org/pdf/1706.03762.pdf", dl.output_dir
            )
        assert result["success"]
        assert "file" in result

    def test_download_failed_increments_counter(self, dl):
        with patch("core.downloader.requests.get", side_effect=Exception("Network error")):
            result = dl.download("https://arxiv.org/pdf/test.pdf", dl.output_dir)
        assert not result["success"]
        assert dl.counts["failed"] == 1

    def test_success_increments_direct_counter(self, dl):
        with patch.object(dl, "_download_direct", return_value={"success": True, "file": "test.pdf"}):
            result = dl.download("https://arxiv.org/pdf/test.pdf", dl.output_dir)
        assert result["success"]
        assert dl.counts["direct"] == 1
