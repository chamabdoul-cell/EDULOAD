import os
import re
import time
import hashlib
import subprocess
import requests
from pathlib import Path
from urllib.parse import urlparse
from collections import deque


class PerformanceMonitor:
    """Rolling 60-minute window of download timing per method."""

    def __init__(self, window_minutes: int = 60):
        self._records: deque = deque()
        self._window = window_minutes * 60

    def record(self, method: str, duration: float, success: bool):
        self._records.append({
            "method": method, "duration": duration,
            "success": success, "ts": time.time(),
        })
        cutoff = time.time() - self._window
        while self._records and self._records[0]["ts"] < cutoff:
            self._records.popleft()

    def stats(self) -> dict:
        methods: dict = {}
        for item in self._records:
            m = item["method"]
            if m not in methods:
                methods[m] = {"count": 0, "success": 0, "total_time": 0.0}
            methods[m]["count"] += 1
            methods[m]["total_time"] += item["duration"]
            if item["success"]:
                methods[m]["success"] += 1
        for m in methods:
            c = methods[m]["count"]
            methods[m]["avg_time_s"] = round(methods[m]["total_time"] / c, 2)
            methods[m]["success_rate_pct"] = round(methods[m]["success"] / c * 100, 1)
        return methods


class UniversalDownloader:
    """Three-tier fallback downloader: yt-dlp → Apify API → Direct HTTP."""

    VIDEO_EXTS = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv"}

    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.apify_token = os.getenv("APIFY_TOKEN", "")
        self.apify_actor_id = "aG9sYZ5h6NpYtW5cD"
        self.counts = {"yt_dlp": 0, "apify": 0, "direct": 0, "failed": 0}
        self.monitor = PerformanceMonitor()

    # ── Public API ────────────────────────────────────────────────────────────

    def download(self, url: str, output_dir: Path = None) -> dict:
        """Try all three methods in priority order; return first success."""
        out = output_dir or self.output_dir

        for method_name, method_fn, tier_key in [
            ("yt-dlp (local)",   lambda: self._download_ytdlp(url, out),  "yt_dlp"),
            ("Apify API (cloud)", lambda: self._download_apify(url, out),  "apify"),
            ("Direct HTTP",       lambda: self._download_direct(url, out), "direct"),
        ]:
            if tier_key == "apify" and not self.apify_token:
                continue
            t = time.time()
            result = method_fn()
            elapsed = time.time() - t
            if result["success"]:
                self.counts[tier_key] += 1
                self.monitor.record(tier_key, elapsed, True)
                return {**result, "method": method_name}
            self.monitor.record(tier_key, elapsed, False)

        self.counts["failed"] += 1
        return {"success": False, "error": "All download methods failed"}

    def download_with_retry(self, url: str, max_retries: int = 2,
                            output_dir: Path = None) -> dict:
        for attempt in range(max_retries):
            result = self.download(url, output_dir)
            if result["success"]:
                return result
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 2)
        return {"success": False, "error": f"Failed after {max_retries} attempts"}

    def get_stats(self) -> dict:
        total = self.counts["yt_dlp"] + self.counts["apify"] + self.counts["direct"]
        denom = total + self.counts["failed"]
        return {
            "method1_ytdlp":  self.counts["yt_dlp"],
            "method2_apify":  self.counts["apify"],
            "method3_direct": self.counts["direct"],
            "failed":         self.counts["failed"],
            "total_success":  total,
            "success_rate":   f"{total / denom * 100:.1f}%" if denom else "N/A",
            "apify_enabled":  bool(self.apify_token),
            "performance":    self.monitor.stats(),
        }

    # ── Download methods ──────────────────────────────────────────────────────

    def _download_ytdlp(self, url: str, out: Path) -> dict:
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            cmd = [
                "yt-dlp", "-f", "best",
                "-o", str(out / f"%(title)s_{url_hash}.%(ext)s"),
                "--no-playlist", "--quiet", "--no-warnings", url,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                for f in out.glob(f"*{url_hash}*"):
                    if f.is_file():
                        return {"success": True, "file": f.name}

            # Retry at 720p
            cmd[cmd.index("-f") + 1] = "best[height<=720]"
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                for f in out.glob(f"*{url_hash}*"):
                    if f.is_file():
                        return {"success": True, "file": f.name}

            return {"success": False, "error": r.stderr.strip() or "yt-dlp failed"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "yt-dlp timeout (120s)"}
        except FileNotFoundError:
            return {"success": False, "error": "yt-dlp not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _download_apify(self, url: str, out: Path) -> dict:
        if not self.apify_token:
            return {"success": False, "error": "No Apify token configured"}
        try:
            from apify_client import ApifyClient
            client = ApifyClient(self.apify_token)
            run_input = {
                "videoUrls": [url],
                "downloadVideos": True,
                "proxyConfiguration": {"useApifyProxy": True},
            }
            run = client.actor(self.apify_actor_id).call(run_input=run_input)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            for item in items:
                video_url = item.get("videoUrl") or item.get("downloadUrl")
                if video_url:
                    return self._fetch_url(video_url, url, out)
            return {"success": False, "error": "No video URL in Apify response"}
        except Exception as e:
            return {"success": False, "error": f"Apify: {e}"}

    def _download_direct(self, url: str, out: Path) -> dict:
        parsed = urlparse(url)
        if any(parsed.path.lower().endswith(ext) for ext in self.VIDEO_EXTS):
            return self._fetch_url(url, url, out)
        return {"success": False, "error": "Not a direct video file URL"}

    def _fetch_url(self, video_url: str, original_url: str, out: Path) -> dict:
        try:
            url_hash = hashlib.md5(original_url.encode()).hexdigest()[:8]
            resp = requests.get(video_url, stream=True, timeout=60,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            cd = resp.headers.get("content-disposition", "")
            if "filename=" in cd:
                filename = re.findall(r'filename="?([^";\s]+)', cd)[0]
            else:
                ext = video_url.split(".")[-1].split("?")[0][:4]
                if ext not in ("mp4", "webm", "avi", "mkv"):
                    ext = "mp4"
                filename = f"video_{url_hash}.{ext}"
            filepath = out / filename
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return {"success": True, "file": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Global singleton — shared across the app
downloader = UniversalDownloader()
