"""Direct HTTP downloader for open-access documents."""
import hashlib
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import requests


class PerformanceMonitor:
    """Rolling 60-minute window of download timing."""

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


class DirectDownloader:
    """Single-tier direct HTTP downloader for open-access files."""

    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.counts = {"direct": 0, "failed": 0}
        self.monitor = PerformanceMonitor()

    def download(self, url: str, output_dir: Path = None) -> dict:
        out = output_dir or self.output_dir
        t = time.time()
        result = self._download_direct(url, out)
        elapsed = time.time() - t
        if result["success"]:
            self.counts["direct"] += 1
            self.monitor.record("direct", elapsed, True)
            return {**result, "method": "Direct HTTP"}
        self.monitor.record("direct", elapsed, False)
        self.counts["failed"] += 1
        return {"success": False, "error": result.get("error", "Download failed")}

    def _download_direct(self, url: str, out: Path) -> dict:
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            parsed = urlparse(url)
            ext = parsed.path.split(".")[-1].split("?")[0][:5] or "pdf"
            filename = f"file_{url_hash}.{ext}"

            resp = requests.get(url, stream=True, timeout=60,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

            cd = resp.headers.get("content-disposition", "")
            if "filename=" in cd:
                import re
                m = re.findall(r'filename="?([^";\s]+)', cd)
                if m:
                    filename = m[0]

            filepath = out / filename
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    f.write(chunk)
            return {"success": True, "file": filename}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_stats(self) -> dict:
        total = self.counts["direct"]
        denom = total + self.counts["failed"]
        return {
            "method_direct":  self.counts["direct"],
            "failed":         self.counts["failed"],
            "total_success":  total,
            "success_rate":   f"{total / denom * 100:.1f}%" if denom else "N/A",
            "performance":    self.monitor.stats(),
        }


# Global singleton
downloader = DirectDownloader()
