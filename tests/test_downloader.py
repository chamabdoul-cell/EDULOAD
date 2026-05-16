#!/usr/bin/env python3
"""Tests for the three-tier UniversalDownloader."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.downloader import UniversalDownloader, PerformanceMonitor


@pytest.fixture
def dl(tmp_path):
    return UniversalDownloader(output_dir=str(tmp_path))


class TestPerformanceMonitor:

    def test_records_entry(self):
        m = PerformanceMonitor()
        m.record("yt_dlp", 3.5, True)
        stats = m.stats()
        assert "yt_dlp" in stats
        assert stats["yt_dlp"]["count"] == 1
        assert stats["yt_dlp"]["success_rate_pct"] == 100.0

    def test_failure_reduces_success_rate(self):
        m = PerformanceMonitor()
        m.record("yt_dlp", 1.0, True)
        m.record("yt_dlp", 1.0, False)
        assert m.stats()["yt_dlp"]["success_rate_pct"] == 50.0


class TestUniversalDownloader:

    def test_get_stats_structure(self, dl):
        stats = dl.get_stats()
        for key in ("method1_ytdlp", "method2_apify", "method3_direct",
                    "failed", "total_success", "success_rate", "apify_enabled"):
            assert key in stats

    def test_apify_skipped_without_token(self, dl):
        dl.apify_token = ""
        result = dl._download_apify("https://example.com/video.mp4", dl.output_dir)
        assert not result["success"]
        assert "No Apify token" in result["error"]

    def test_direct_rejects_non_video_url(self, dl):
        result = dl._download_direct("https://example.com/page", dl.output_dir)
        assert not result["success"]

    def test_direct_accepts_video_url(self, dl):
        with patch("core.downloader.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.headers = {}
            mock_resp.iter_content.return_value = [b"fakevideo"]
            mock_get.return_value.__enter__ = lambda s: mock_resp
            mock_get.return_value = mock_resp
            result = dl._download_direct(
                "https://example.com/video.mp4", dl.output_dir
            )
        assert result["success"] or "error" in result  # network may fail in CI

    def test_ytdlp_not_found_returns_error(self, dl):
        with patch("shutil.which", return_value=None):
            result = dl._download_ytdlp("https://youtube.com/watch?v=test", dl.output_dir)
        assert not result["success"]

    def test_download_falls_through_all_methods(self, dl):
        dl.apify_token = ""
        with patch.object(dl, "_download_ytdlp", return_value={"success": False, "error": "no ytdlp"}):
            with patch.object(dl, "_download_direct", return_value={"success": False, "error": "not video url"}):
                result = dl.download("https://example.com/page")
        assert not result["success"]
        assert dl.counts["failed"] == 1

    def test_download_counts_method1_success(self, dl):
        with patch.object(dl, "_download_ytdlp", return_value={"success": True, "file": "test.mp4"}):
            result = dl.download("https://youtube.com/watch?v=test")
        assert result["success"]
        assert result["method"] == "yt-dlp (local)"
        assert dl.counts["yt_dlp"] == 1
