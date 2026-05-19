"""Admin-only endpoints — user management, usage stats, audit log.

All routes require the 'admin' role.
In single_user mode the synthetic admin user satisfies this automatically.
"""
from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_role
from db import get_db
import repositories.users as users_repo
import repositories.usage as usage_repo
import repositories.audit as audit_repo
import repositories.institutions as inst_repo
import repositories.history as history_repo

router = APIRouter(prefix="/api/admin", tags=["admin"])

_admin = require_role("admin")


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(_user=Depends(_admin)):
    con  = get_db()
    data = users_repo.list_users(con)
    con.close()
    return data


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, _user=Depends(_admin)):
    con     = get_db()
    deleted = users_repo.delete_user(con, user_id)
    con.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


@router.patch("/users/{user_id}/role")
def change_role(user_id: int, body: dict, _user=Depends(_admin)):
    role = body.get("role", "")
    if role not in {"admin", "researcher", "student"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    con = get_db()
    users_repo.update_role(con, user_id, role)
    con.close()
    return {"status": "updated"}


# ── Institutions ───────────────────────────────────────────────────────────────

@router.get("/institutions")
def list_institutions(_user=Depends(_admin)):
    con  = get_db()
    data = inst_repo.list_institutions(con)
    con.close()
    return data


@router.post("/institutions", status_code=201)
def create_institution(body: dict, _user=Depends(_admin)):
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    country = body.get("country", "")
    con     = get_db()
    iid     = inst_repo.create_institution(con, name, country)
    con.close()
    return {"id": iid, "name": name, "country": country}


# ── Usage & audit ──────────────────────────────────────────────────────────────

@router.get("/usage")
def usage_stats(_user=Depends(_admin)):
    con  = get_db()
    data = usage_repo.get_stats(con)
    con.close()
    return data


@router.get("/audit")
def audit_log(limit: int = 100, _user=Depends(_admin)):
    con  = get_db()
    data = audit_repo.list_logs(con, limit=limit)
    con.close()
    return data


# ── Impact summary (grant-ready) ───────────────────────────────────────────────

@router.get("/impact")
def impact_summary(_user=Depends(_admin)):
    con             = get_db()
    all_history     = history_repo.get_history(con, limit=999999)
    all_users       = users_repo.list_users(con)
    con.close()

    total_downloads = len(all_history)
    total_users     = len(all_users)
    source_counts: dict[str, int] = {}
    for entry in all_history:
        src = entry.get("source") or "unknown"
        source_counts[src] = source_counts.get(src, 0) + 1
    sources_used = sorted(
        [{"source": k, "n": v} for k, v in source_counts.items()],
        key=lambda x: x["n"], reverse=True,
    )
    return {
        "total_downloads": total_downloads,
        "total_users":     total_users,
        "sources_used":    sources_used,
    }
