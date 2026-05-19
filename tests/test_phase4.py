"""Phase 4 tests — repository layer completeness.

Covers all new/updated repositories and confirms route handlers
no longer contain raw SQL (import-level structural check).
"""
import sqlite3
import pytest
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════════════
# 1. repositories/users.py
# ══════════════════════════════════════════════════════════════════════════════

class TestUsersRepo:

    def test_create_and_get_user(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        uid = users_repo.create_user(con, "alice@example.com", "hashed_pw", "researcher", None)
        con.close()
        assert isinstance(uid, int) and uid > 0

    def test_get_user_by_email(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        users_repo.create_user(con, "bob@example.com", "hpw", "admin", None)
        row = users_repo.get_user_by_email(con, "bob@example.com")
        con.close()
        assert row is not None
        assert row["email"] == "bob@example.com"
        assert row["role"] == "admin"

    def test_get_user_by_email_missing(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        row = users_repo.get_user_by_email(con, "nobody@example.com")
        con.close()
        assert row is None

    def test_list_users(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        users_repo.create_user(con, "u1@x.com", "pw", "researcher", None)
        users_repo.create_user(con, "u2@x.com", "pw", "researcher", None)
        users = users_repo.list_users(con)
        con.close()
        assert len(users) == 2

    def test_delete_user(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        uid = users_repo.create_user(con, "del@x.com", "pw", "researcher", None)
        deleted = users_repo.delete_user(con, uid)
        remaining = users_repo.list_users(con)
        con.close()
        assert deleted is True
        assert len(remaining) == 0

    def test_delete_nonexistent_user(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        result = users_repo.delete_user(con, 99999)
        con.close()
        assert result is False

    def test_update_role(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        uid = users_repo.create_user(con, "role@x.com", "pw", "researcher", None)
        users_repo.update_role(con, uid, "admin")
        row = users_repo.get_user_by_email(con, "role@x.com")
        con.close()
        assert row["role"] == "admin"

    def test_create_duplicate_email_raises(self, temp_db):
        import db as db_module
        import repositories.users as users_repo
        con = db_module.get_db()
        users_repo.create_user(con, "dup@x.com", "pw", "researcher", None)
        with pytest.raises(Exception):
            users_repo.create_user(con, "dup@x.com", "pw2", "admin", None)
        con.close()


# ══════════════════════════════════════════════════════════════════════════════
# 2. repositories/usage.py
# ══════════════════════════════════════════════════════════════════════════════

class TestUsageRepo:

    def test_record_inserts_row(self, temp_db):
        import db as db_module
        import repositories.usage as usage_repo
        con = db_module.get_db()
        usage_repo.record(con, user_id=1, endpoint="/api/download", tokens=0)
        count = con.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
        con.close()
        assert count == 1

    def test_get_stats_groups_by_endpoint(self, temp_db):
        import db as db_module
        import repositories.usage as usage_repo
        con = db_module.get_db()
        usage_repo.record(con, 1, "/api/search", 5)
        usage_repo.record(con, 1, "/api/search", 3)
        usage_repo.record(con, 2, "/api/download", 0)
        stats = usage_repo.get_stats(con)
        con.close()
        endpoints = {s["endpoint"] for s in stats}
        assert "/api/search" in endpoints and "/api/download" in endpoints
        search_stat = next(s for s in stats if s["endpoint"] == "/api/search")
        assert search_stat["count"] == 2

    def test_count_today_downloads(self, temp_db):
        import db as db_module
        import repositories.usage as usage_repo
        con = db_module.get_db()
        usage_repo.record(con, 1, "/api/download", 0)
        usage_repo.record(con, 1, "/api/download", 0)
        n = usage_repo.count_today(con, user_id=1, endpoint="/api/download")
        con.close()
        assert n == 2


# ══════════════════════════════════════════════════════════════════════════════
# 3. repositories/audit.py
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditRepo:

    def test_log_and_list(self, temp_db):
        import db as db_module
        import repositories.audit as audit_repo
        con = db_module.get_db()
        audit_repo.log(con, user_id=1, action="download", target="paper.pdf")
        rows = audit_repo.list_logs(con, limit=10)
        con.close()
        assert len(rows) == 1
        assert rows[0]["action"] == "download"

    def test_list_respects_limit(self, temp_db):
        import db as db_module
        import repositories.audit as audit_repo
        con = db_module.get_db()
        for i in range(5):
            audit_repo.log(con, 1, f"action{i}", "")
        rows = audit_repo.list_logs(con, limit=3)
        con.close()
        assert len(rows) == 3


# ══════════════════════════════════════════════════════════════════════════════
# 4. repositories/institutions.py
# ══════════════════════════════════════════════════════════════════════════════

class TestInstitutionsRepo:

    def test_create_and_list(self, temp_db):
        import db as db_module
        import repositories.institutions as inst_repo
        con = db_module.get_db()
        iid = inst_repo.create_institution(con, "MIT", "US")
        rows = inst_repo.list_institutions(con)
        con.close()
        assert isinstance(iid, int)
        assert any(r["name"] == "MIT" for r in rows)

    def test_list_empty(self, temp_db):
        import db as db_module
        import repositories.institutions as inst_repo
        con = db_module.get_db()
        rows = inst_repo.list_institutions(con)
        con.close()
        assert rows == []


# ══════════════════════════════════════════════════════════════════════════════
# 5. repositories/queue.py — new functions
# ══════════════════════════════════════════════════════════════════════════════

class TestQueueRepo:

    def test_get_job(self, temp_db):
        import db as db_module
        import repositories.queue as queue_repo
        con = db_module.get_db()
        queue_repo.enqueue_job(con, "job-1", "https://example.com/paper.pdf")
        row = queue_repo.get_job(con, "job-1")
        con.close()
        assert row is not None
        assert row["url"] == "https://example.com/paper.pdf"
        assert row["status"] == "queued"

    def test_get_job_missing(self, temp_db):
        import db as db_module
        import repositories.queue as queue_repo
        con = db_module.get_db()
        row = queue_repo.get_job(con, "no-such-job")
        con.close()
        assert row is None

    def test_list_jobs(self, temp_db):
        import db as db_module
        import repositories.queue as queue_repo
        con = db_module.get_db()
        queue_repo.enqueue_job(con, "j1", "http://a.com")
        queue_repo.enqueue_job(con, "j2", "http://b.com")
        jobs = queue_repo.list_jobs(con)
        con.close()
        assert len(jobs) == 2

    def test_cancel_job(self, temp_db):
        import db as db_module
        import repositories.queue as queue_repo
        con = db_module.get_db()
        queue_repo.enqueue_job(con, "j-cancel", "http://c.com")
        queue_repo.cancel_job(con, "j-cancel")
        row = queue_repo.get_job(con, "j-cancel")
        con.close()
        assert row["status"] == "cancelled"


# ══════════════════════════════════════════════════════════════════════════════
# 6. No raw SQL in route handlers (structural check)
# ══════════════════════════════════════════════════════════════════════════════

class TestNoRawSqlInRouters:
    """Verify route handler source files don't call .execute() directly."""

    ROUTER_FILES = [
        "routers/admin.py",
        "routers/auth.py",
    ]
    SERVICE_FILES = [
        "services/audit.py",
        "services/quota.py",
    ]

    def _read(self, rel_path: str) -> str:
        p = Path(__file__).parent.parent / rel_path
        return p.read_text()

    def test_admin_router_no_raw_execute(self):
        src = self._read("routers/admin.py")
        assert ".execute(" not in src, "routers/admin.py still has raw .execute() calls"

    def test_auth_router_no_raw_execute(self):
        src = self._read("routers/auth.py")
        assert ".execute(" not in src, "routers/auth.py still has raw .execute() calls"

    def test_audit_service_no_raw_execute(self):
        src = self._read("services/audit.py")
        assert ".execute(" not in src, "services/audit.py still has raw .execute() calls"

    def test_quota_service_no_raw_execute(self):
        src = self._read("services/quota.py")
        assert ".execute(" not in src, "services/quota.py still has raw .execute() calls"
