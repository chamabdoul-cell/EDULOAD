"""Phase 2 tests — auth guards, rate limiting, download quota.

Tests are written BEFORE implementation (TDD for security-critical changes).
"""
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as app_module
from auth.dependencies import get_current_user
from config.settings import AIConfig

_RESEARCHER = {"id": 1, "email": "r@test.com", "role": "researcher", "institution_id": None}
_ADMIN      = {"id": 2, "email": "a@test.com", "role": "admin",      "institution_id": None}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _override(user: dict):
    app_module.app.dependency_overrides[get_current_user] = lambda: user


def _clear():
    app_module.app.dependency_overrides.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Auth guard
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthGuard:

    def test_single_user_no_token_allowed(self):
        """In single_user mode, protected routes pass without any token."""
        with patch.object(AIConfig, "APP_MODE", "single_user"):
            with TestClient(app_module.app) as c:
                r = c.get("/api/history")
        assert r.status_code == 200

    def test_multi_user_no_token_returns_401(self):
        """In multi_user mode, missing token → 401 on protected route."""
        _clear()
        with patch.object(AIConfig, "APP_MODE", "multi_user"):
            with TestClient(app_module.app, raise_server_exceptions=False) as c:
                r = c.get("/api/history")
        assert r.status_code == 401

    def test_multi_user_with_valid_token_allowed(self):
        """In multi_user mode, injected user → 200 on protected route."""
        _override(_RESEARCHER)
        try:
            with TestClient(app_module.app) as c:
                r = c.get("/api/history")
            assert r.status_code == 200
        finally:
            _clear()

    def test_search_requires_auth_in_multi_user(self):
        """POST /api/search → 401 without token in multi_user mode."""
        _clear()
        with patch.object(AIConfig, "APP_MODE", "multi_user"):
            with TestClient(app_module.app, raise_server_exceptions=False) as c:
                r = c.post("/api/search", json={"query": "test"})
        assert r.status_code == 401

    def test_collections_require_auth_in_multi_user(self):
        """GET /api/collections → 401 without token in multi_user mode."""
        _clear()
        with patch.object(AIConfig, "APP_MODE", "multi_user"):
            with TestClient(app_module.app, raise_server_exceptions=False) as c:
                r = c.get("/api/collections")
        assert r.status_code == 401

    def test_settings_get_requires_auth_in_multi_user(self):
        """GET /api/settings → 401 without token in multi_user mode."""
        _clear()
        with patch.object(AIConfig, "APP_MODE", "multi_user"):
            with TestClient(app_module.app, raise_server_exceptions=False) as c:
                r = c.get("/api/settings")
        assert r.status_code == 401

    def test_settings_post_admin_only_rejects_researcher(self):
        """POST /api/settings → 403 for non-admin user."""
        _override(_RESEARCHER)
        try:
            with TestClient(app_module.app) as c:
                r = c.post("/api/settings", json={"key": "val"})
            assert r.status_code == 403
        finally:
            _clear()

    def test_settings_post_admin_allowed(self, temp_db):
        """POST /api/settings → 200 for admin user."""
        _override(_ADMIN)
        try:
            with TestClient(app_module.app) as c:
                r = c.post("/api/settings", json={"key": "val"})
            assert r.status_code == 200
        finally:
            _clear()


# ══════════════════════════════════════════════════════════════════════════════
# Rate limiter
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimiter:

    def test_allows_requests_under_limit(self):
        from services.rate_limit import check, reset
        reset("rl-test-under")
        for _ in range(5):
            assert check("rl-test-under", limit=10) is True

    def test_blocks_request_over_limit(self):
        from services.rate_limit import check, reset
        reset("rl-test-over")
        for _ in range(3):
            check("rl-test-over", limit=3)
        assert check("rl-test-over", limit=3) is False

    def test_window_expiry_resets_count(self):
        import time
        from services.rate_limit import check, reset
        reset("rl-test-expire")
        for _ in range(2):
            check("rl-test-expire", limit=2, window_secs=1)
        assert check("rl-test-expire", limit=2, window_secs=1) is False
        time.sleep(1.1)
        assert check("rl-test-expire", limit=2, window_secs=1) is True

    def test_different_keys_are_independent(self):
        from services.rate_limit import check, reset
        reset("rl-a")
        reset("rl-b")
        for _ in range(3):
            check("rl-a", limit=3)
        assert check("rl-a", limit=3) is False
        assert check("rl-b", limit=3) is True


# ══════════════════════════════════════════════════════════════════════════════
# Download quota
# ══════════════════════════════════════════════════════════════════════════════

class TestDownloadQuota:

    def test_quota_bypassed_in_single_user(self):
        """check_quota is a no-op in single_user mode."""
        from services.quota import check_quota
        with patch.object(AIConfig, "APP_MODE", "single_user"):
            check_quota(999)  # must not raise

    def test_quota_passes_when_under_limit(self, temp_db):
        """User with 0 downloads today is under quota."""
        from services.quota import check_quota
        with patch.object(AIConfig, "APP_MODE", "multi_user"), \
             patch("services.quota.MAX_DOWNLOADS_PER_DAY", 5):
            check_quota(1)  # must not raise

    def test_quota_raises_429_when_at_limit(self, temp_db):
        """User who reached MAX_DOWNLOADS_PER_DAY gets HTTP 429."""
        import db as db_module
        from services.quota import check_quota
        con = db_module.get_db()
        for _ in range(3):
            con.execute(
                "INSERT INTO usage (user_id, endpoint, tokens_used) VALUES (?, '/api/download', 0)",
                (1,),
            )
        con.commit()
        con.close()
        with patch.object(AIConfig, "APP_MODE", "multi_user"), \
             patch("services.quota.MAX_DOWNLOADS_PER_DAY", 3):
            with pytest.raises(HTTPException) as exc:
                check_quota(1)
            assert exc.value.status_code == 429

    def test_quota_is_per_user(self, temp_db):
        """Quota exhausted for user 1 does not affect user 2."""
        import db as db_module
        from services.quota import check_quota
        con = db_module.get_db()
        for _ in range(3):
            con.execute(
                "INSERT INTO usage (user_id, endpoint, tokens_used) VALUES (1, '/api/download', 0)"
            )
        con.commit()
        con.close()
        with patch.object(AIConfig, "APP_MODE", "multi_user"), \
             patch("services.quota.MAX_DOWNLOADS_PER_DAY", 3):
            with pytest.raises(HTTPException):
                check_quota(1)
            check_quota(2)  # must not raise

    def test_quota_only_counts_todays_downloads(self, temp_db):
        """Downloads from previous days do not count toward today's quota."""
        import db as db_module
        from services.quota import check_quota
        con = db_module.get_db()
        con.execute(
            "INSERT INTO usage (user_id, endpoint, tokens_used, created_at) "
            "VALUES (1, '/api/download', 0, date('now', '-1 day'))"
        )
        con.commit()
        con.close()
        with patch.object(AIConfig, "APP_MODE", "multi_user"), \
             patch("services.quota.MAX_DOWNLOADS_PER_DAY", 1):
            check_quota(1)  # must not raise — yesterday's download doesn't count
