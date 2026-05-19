"""Audit logging and usage recording helpers.

Called from route handlers that want to record activity.
No-ops in single_user mode to keep overhead zero.
"""
from config.settings import AIConfig
from db import get_db
import repositories.usage as usage_repo
import repositories.audit as audit_repo


def record_usage(user_id: int, endpoint: str, tokens_used: int = 0) -> None:
    if not AIConfig.is_multi_user():
        return
    con = get_db()
    usage_repo.record(con, user_id, endpoint, tokens_used)
    con.close()


def audit(user_id: int, action: str, target: str = "") -> None:
    if not AIConfig.is_multi_user():
        return
    con = get_db()
    audit_repo.log(con, user_id, action, target)
    con.close()
