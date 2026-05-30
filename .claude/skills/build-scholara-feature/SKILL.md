# Skill: build-scholara-feature

**Triggers:** "build", "implement", "add endpoint", "add feature", "extend"

**Description:** Use this skill when implementing a new feature, endpoint, or extending existing behaviour in Scholara. Reads CLAUDE.md and matches existing patterns before writing any code. Writes tests alongside implementation.

---

## Process — follow this order exactly

**Step 1 — Read the rules**
Read `CLAUDE.md`. Note the repository pattern rule, auth guard rule, rate limit rule, and the "Don't Do" list.

**Step 2 — Understand the request**
Read the description of what is being built. If anything is ambiguous, ask one clarifying question before proceeding.

**Step 3 — Find the next phase number**
List `tests/test_phase*.py` to find the highest existing phase number. The new test file will be `test_phaseN.py` where N = highest + 1.

**Step 4 — Find similar existing features**
Locate 2 similar existing features in the codebase: find the router, its matching repository function, its service (if any), and its test file. Note the patterns: how auth is applied, how errors are returned, how rate limiting is called, how SQL is structured.

**Step 5 — Implement in this order**

a. **Repository** (`repositories/<relevant>.py`) — if new SQL is needed. Signature: `def my_func(db: sqlite3.Connection, ...) -> ...`. No business logic here.

b. **Service** (`services/<relevant>.py`) — if there is orchestration, side-effects, or business logic.

c. **Router** (`routers/<relevant>.py`) — thin layer only. Apply `get_current_user()` and rate limiter as `Depends()`. Call service or repository. Return response.

d. **Wire into `app.py`** — if a new router file was created: `app.include_router(...)`.

e. **Frontend** (`static/js/`) — if UI is needed. Follow the module dependency order. Use `t('key')` for every user-visible string. Add EN and FR translations to `TRANSLATIONS` in `i18n.js` before using them.

**Step 6 — Write tests**
Create `tests/test_phaseN.py` covering:
- Happy path
- One validation-failure or not-found path
- One edge case relevant to this feature

Use the `temp_db` fixture from `conftest.py`. Do not create a separate fixture.

**Step 7 — Run the security checklist**
For every new endpoint, verify:
- [ ] `get_current_user()` / `require_role()` is present for protected routes
- [ ] Rate limiter is applied
- [ ] Input is validated (Pydantic schema or explicit checks)
- [ ] Errors returned to the client contain no raw database messages or stack traces
- [ ] No secrets, tokens, or payment payloads are logged
- [ ] If the endpoint touches user-owned data: ownership is checked before access
- [ ] If admin-only in `multi_user` mode: guarded with `require_role("admin")`

**Step 8 — Return a summary**
Report:
- Files added or changed (with line ranges)
- Patterns reused from existing code
- Any rule that emerged that is worth adding to CLAUDE.md

---

## Hard constraints

- Never call `.execute()` outside `repositories/`
- Never put business logic in `routers/`
- Never skip auth dependency on a protected endpoint, even in `single_user` mode
- Never hardcode English strings in JS — use `t('key')` and update `TRANSLATIONS`
- Never use `str.format()` on prompt templates — use `.replace()`
- Do not add new third-party dependencies without noting them in CLAUDE.md
