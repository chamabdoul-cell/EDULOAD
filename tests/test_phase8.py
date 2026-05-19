"""Phase 8 tests — institutional features: shared collections, analytics, branding.

TDD: tests written before implementation.
"""
import pytest


# ══════════════════════════════════════════════════════════════════════════════
# 8a — Shared Collections
# ══════════════════════════════════════════════════════════════════════════════

class TestSharedCollections:

    def test_create_collection_with_owner(self, temp_db):
        import db as db_module
        import repositories.collections as col_repo
        con = db_module.get_db()
        cid = col_repo.create_collection(con, "My Coll", "", owner_id=1)
        col = col_repo.get_collection(con, cid)
        con.close()
        assert col["owner_id"] == 1

    def test_share_collection_sets_institution(self, temp_db):
        import db as db_module
        import repositories.collections as col_repo
        con = db_module.get_db()
        cid = col_repo.create_collection(con, "Shared", "", owner_id=1)
        col_repo.share_collection(con, cid, institution_id=42)
        col = col_repo.get_collection(con, cid)
        con.close()
        assert col["institution_id"] == 42
        assert col["is_shared"] == 1

    def test_list_shared_by_institution(self, temp_db):
        import db as db_module
        import repositories.collections as col_repo
        con = db_module.get_db()
        cid1 = col_repo.create_collection(con, "Inst Coll", "", owner_id=1)
        col_repo.share_collection(con, cid1, institution_id=5)
        col_repo.create_collection(con, "Private Coll", "", owner_id=2)  # not shared
        shared = col_repo.list_shared_collections(con, institution_id=5)
        con.close()
        assert len(shared) == 1
        assert shared[0]["name"] == "Inst Coll"

    def test_list_shared_empty_for_different_institution(self, temp_db):
        import db as db_module
        import repositories.collections as col_repo
        con = db_module.get_db()
        cid = col_repo.create_collection(con, "Coll A", "", owner_id=1)
        col_repo.share_collection(con, cid, institution_id=1)
        shared = col_repo.list_shared_collections(con, institution_id=99)
        con.close()
        assert len(shared) == 0

    def test_shared_collections_endpoint(self, temp_db):
        from fastapi.testclient import TestClient
        import app as application
        from auth.dependencies import get_current_user
        application.app.dependency_overrides[get_current_user] = lambda: {
            "id": 1, "email": "u@x.com", "role": "admin", "institution_id": 7
        }
        import db as db_module
        import repositories.collections as col_repo
        con = db_module.get_db()
        cid = col_repo.create_collection(con, "SharedColl", "", owner_id=1)
        col_repo.share_collection(con, cid, institution_id=7)
        con.close()
        client = TestClient(application.app)
        r = client.get("/api/collections/shared")
        assert r.status_code == 200
        data = r.json()
        assert any(c["name"] == "SharedColl" for c in data)

    def test_share_endpoint(self, temp_db):
        from fastapi.testclient import TestClient
        import app as application
        from auth.dependencies import get_current_user
        application.app.dependency_overrides[get_current_user] = lambda: {
            "id": 1, "email": "u@x.com", "role": "admin", "institution_id": 3
        }
        import db as db_module
        import repositories.collections as col_repo
        con = db_module.get_db()
        cid = col_repo.create_collection(con, "ToShare", "", owner_id=1)
        con.close()
        client = TestClient(application.app)
        r = client.post(f"/api/collections/{cid}/share")
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 8b — Usage Analytics
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalytics:

    def test_record_and_top_queries(self, temp_db):
        import db as db_module
        import repositories.usage as usage_repo
        con = db_module.get_db()
        usage_repo.record_query(con, "deep learning")
        usage_repo.record_query(con, "deep learning")
        usage_repo.record_query(con, "quantum computing")
        top = usage_repo.top_queries(con, limit=10)
        con.close()
        assert len(top) >= 1
        assert top[0]["query_stem"] == "deep learning"
        assert top[0]["count"] == 2

    def test_downloads_by_day(self, temp_db):
        import db as db_module
        import repositories.history as hist_repo
        import repositories.usage as usage_repo
        con = db_module.get_db()
        hist_repo.add_history_entry(con, "http://a.com", "Paper A", "arxiv", "a.pdf", 100)
        hist_repo.add_history_entry(con, "http://b.com", "Paper B", "arxiv", "b.pdf", 200)
        by_day = usage_repo.downloads_by_day(con, days=30)
        con.close()
        assert isinstance(by_day, list)
        total = sum(d["count"] for d in by_day)
        assert total == 2

    def test_active_users_per_week(self, temp_db):
        import db as db_module
        import repositories.usage as usage_repo
        con = db_module.get_db()
        usage_repo.record(con, user_id=1, endpoint="/api/search")
        usage_repo.record(con, user_id=2, endpoint="/api/search")
        usage_repo.record(con, user_id=1, endpoint="/api/download")
        active = usage_repo.active_users_per_week(con)
        con.close()
        assert isinstance(active, int)
        assert active == 2

    def test_top_sources_from_history(self, temp_db):
        import db as db_module
        import repositories.history as hist_repo
        con = db_module.get_db()
        hist_repo.add_history_entry(con, "http://a.com", "A", "arxiv", "a.pdf", 1)
        hist_repo.add_history_entry(con, "http://b.com", "B", "arxiv", "b.pdf", 1)
        hist_repo.add_history_entry(con, "http://c.com", "C", "hal",   "c.pdf", 1)
        sources = hist_repo.top_sources(con, limit=5)
        con.close()
        assert sources[0]["source"] == "arxiv"
        assert sources[0]["n"] == 2

    def test_impact_endpoint_includes_analytics(self, temp_db):
        from fastapi.testclient import TestClient
        import app as application
        from auth.dependencies import require_role
        application.app.dependency_overrides[require_role("admin")] = lambda: {
            "id": 0, "email": "admin@x.com", "role": "admin", "institution_id": None
        }
        client = TestClient(application.app)
        r = client.get("/api/admin/impact")
        assert r.status_code == 200
        data = r.json()
        assert "downloads_by_day" in data
        assert "top_queries"      in data
        assert "top_sources"      in data
        assert "active_users_week" in data


# ══════════════════════════════════════════════════════════════════════════════
# 8c — Institution Branding
# ══════════════════════════════════════════════════════════════════════════════

class TestInstitutionBranding:

    def test_create_institution_with_branding(self, temp_db):
        import db as db_module
        import repositories.institutions as inst_repo
        con = db_module.get_db()
        iid = inst_repo.create_institution(con, "MIT", "US",
                                           logo_url="https://mit.edu/logo.png",
                                           primary_color="#c8430b")
        branding = inst_repo.get_institution_branding(con, iid)
        con.close()
        assert branding["logo_url"]      == "https://mit.edu/logo.png"
        assert branding["primary_color"] == "#c8430b"

    def test_branding_none_for_missing_institution(self, temp_db):
        import db as db_module
        import repositories.institutions as inst_repo
        con = db_module.get_db()
        b = inst_repo.get_institution_branding(con, 9999)
        con.close()
        assert b is None

    def test_branding_none_when_not_set(self, temp_db):
        import db as db_module
        import repositories.institutions as inst_repo
        con = db_module.get_db()
        iid = inst_repo.create_institution(con, "Plain Uni", "TN")
        b = inst_repo.get_institution_branding(con, iid)
        con.close()
        # No branding set → None
        assert b is None
