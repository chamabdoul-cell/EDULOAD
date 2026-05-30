# Scholara — Claude Code Instructions

> Drop this file at `adm_app/CLAUDE.md` (project root, next to `app.py`).
> Claude Code loads it automatically at the start of every session.

---

## Project Identity

**Scholara** is a self-hosted, AI-augmented open-access academic research platform.
It supports Francophone sources, bilingual EN/FR UI, single-user local deployments,
and multi-user institutional deployments with JWT auth, roles, and audit logging.

The project was formerly named **EduLoad**. The folder is still called `adm_app/`.
Ignore any references to EduLoad, `adm_app.db`, Apify, or Anthropic in old code —
they are artefacts of the previous codebase.

Served at `http://127.0.0.1:7860` by default.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14+, FastAPI, Uvicorn |
| Frontend | Vanilla HTML/CSS, ES modules (`static/js/*.js`), no framework |
| Database | SQLite (`scholara.db`) via `sqlite3` |
| AI — primary | Ollama (`mistral` by default) — local, offline |
| AI — fallback | DeepSeek API (`deepseek-chat`) — OpenAI-compatible |
| AI — last resort | Keyword heuristic in `core/fallback.py` |
| Auth | `python-jose[cryptography]` (JWT) + `passlib[bcrypt]` |
| Conversion | `pdf2docx`, `pypdf`, `mammoth`, `xhtml2pdf`, `python-docx` |
| HTTP | `httpx` async (AI calls) · `requests` sync (search) |
| Retries | `tenacity` |

---

## Commands

```bash
# Run (uses Python 3.14 venv at /home/chama/my-venv)
source /home/chama/my-venv/bin/activate
python app.py

# Tests
pytest tests/                        # full suite
pytest tests/test_phaseN.py -v       # single phase

# Multi-user mode
APP_MODE=multi_user SECRET_KEY=your-secret python app.py

# Docker
docker-compose up --build
```

Known pre-existing failures (not regressions, do not fix without a dedicated task):
- 3 asyncio `get_event_loop()` incompatibilities (Python 3.14 removed this API)
- 2 EduLoad-era tests expecting `youtube`/`duckduckgo` sources

---

## Architecture — Layer Map

```
routers/        ← thin HTTP layer; calls services or repositories
services/       ← business logic, orchestration, side-effects
repositories/   ← all SQL; takes db: sqlite3.Connection as first arg
core/           ← AI routing, downloading, fallback logic
auth/           ← JWT creation/decoding, password hashing, FastAPI deps
config/         ← settings, env, market segment, app mode
utils/          ← in-memory TTL cache
prompts/        ← plain-text prompt templates for AI actions
static/js/      ← ES module frontend (no build step, no framework)
tests/          ← one file per phase + focused test files
```

---

## Coding Rules

### Backend

**Repository pattern is mandatory.**
All SQL lives in `repositories/`. Routers and services must never call `.execute()` directly.
This is enforced by `TestNoRawSqlInRouters` in `test_phase4.py` — breaking it will fail CI.

**Business logic belongs in `services/`, not in routers.**
Routers validate the request, call a service or repository, and return a response. Nothing more.

**Auth guards are required on every protected endpoint.**
In `multi_user` mode: use `get_current_user()` as a `Depends()` argument.
For admin-only endpoints: add `require_role("admin")` as a `Depends()`.
In `single_user` mode `get_current_user()` returns a synthetic admin — no token needed.
Never skip the dependency; never inline token decoding in a router.

**Rate limiting is applied per router.**
Default: `apply(request, user)` from `services/rate_limit.py`.
Custom limits (e.g. extract: 10/min, demo: 20/min): use `check(key, limit, window_secs)` directly.

**French sources are auto-injected by the search pipeline.**
When `lang == "fr"`, `FR_SOURCES` are prepended automatically inside `aggregate_search()`.
Do not duplicate them in callers or add manual source-list logic in routers.

**Prompt substitution uses `.replace()`, not `str.format()`.**
`prompts/demo/*.txt` placeholders are `{text}`, `{language}`, `{message}`.
`str.format()` breaks on the JSON curly braces in `presentation.txt`.

**Reminder columns follow `last<Action>SentAt`.**
Any new "last time X happened" timestamp column should use this naming pattern.

**Do not add new top-level schedulers or cron jobs.**
Background work goes through the existing `services/download.py` worker pattern or a new
function in `services/`. Document the addition in this file.

**Do not add new third-party dependencies without a noted justification.**
Update `requirements.txt` and add a line here explaining why.

### Frontend

**No framework, no build step.**
The frontend is plain ES modules. Do not introduce React, Vue, a bundler, or TypeScript.

**Module dependency order must stay acyclic.**
```
i18n.js → auth.js → api.js → download.js → search.js / collections.js / demo.js → app.js
```
`auth.js` uses bare `fetch()` for login (not `apiFetch()`) to avoid the auth→api cycle.
Do not create circular imports.

**All user-visible strings go through `t()` from `i18n.js`.**
Add EN and FR translations to the `TRANSLATIONS` object in `i18n.js` before using `t('key')`.
Do not hardcode English strings in JS files.

**`apiFetch()` handles auth headers and 401 refresh automatically.**
Use it for all API calls from frontend modules. Use bare `fetch()` only in `auth.js` login.

### Testing

**Every new feature phase gets a `tests/test_phaseN.py` file.**
Name it with the next available phase number. Cover at minimum:
- the happy path
- one validation-failure path
- one not-found / edge-case path

**Use the `temp_db` fixture from `conftest.py` for all database tests.**
It monkeypatches `db.DB_PATH` and creates all tables. Do not create a separate fixture.

**Do not mock the database unless existing tests in the same file already do.**

---

## Security Checklist (apply to every new endpoint)

Before considering any endpoint complete, verify:

- [ ] Auth dependency (`get_current_user` / `require_role`) is present for protected routes
- [ ] Rate limiter is applied
- [ ] Input is validated (Pydantic schema or explicit checks)
- [ ] Errors returned to the client contain no raw database messages or stack traces
- [ ] No secrets, tokens, or payment payloads are logged
- [ ] If the endpoint touches user-owned data: ownership is checked before access
- [ ] If the endpoint is admin-only in `multi_user` mode: guarded with `require_role("admin")`

---

## How to Add a New Feature (standard pattern)

1. **Explore first.** Read the relevant existing router + repository + test file before writing.
   Identify which repository functions already exist; reuse them before creating new ones.

2. **Add a repository function** in the appropriate `repositories/*.py` file if new SQL is needed.
   Signature: `def my_func(db: sqlite3.Connection, ...) -> ...`

3. **Add a service function** in `services/` if there is orchestration, side-effects, or business logic.

4. **Add or extend a router** in `routers/`. Keep it thin. Apply auth and rate-limit dependencies.

5. **Wire into `app.py`** if a new router file was created: `app.include_router(...)`.

6. **Add frontend module code** if a UI change is needed. Follow the module dependency order.
   Add translations to `i18n.js` before using `t()`.

7. **Write `tests/test_phaseN.py`** covering happy path, failure path, and one edge case.
   Run `pytest tests/test_phaseN.py -v` before finishing.

8. **Run the security checklist** above for every new endpoint.

9. **Update this file** if a new pattern, dependency, or "don't do" rule emerges from the work.

---

## Don't Do

- **Never** call `.execute()` in a router or service — all SQL goes through `repositories/`
- **Never** return raw database errors or exception messages to the client
- **Never** log raw payment payloads, JWT tokens, or passwords
- **Never** skip `get_current_user()` on a protected endpoint, even in `single_user` mode
- **Never** use `str.format()` on prompt templates — use `.replace()` (JSON braces conflict)
- **Never** duplicate French source injection — `aggregate_search()` already handles it
- **Never** edit `prisma/schema.prisma` after merge — there is no Prisma here; schema changes
  are `ALTER TABLE ... ADD COLUMN` migrations in `db.py` that run on startup
- **Never** introduce circular imports between frontend ES modules
- **Never** hardcode English strings in JS — use `t('key')` and update `TRANSLATIONS`
- **Never** add a new scheduler/cron without documenting it here and reusing existing workers

---

## Known Limitations (do not attempt to fix without a dedicated task)

- Synchronous search + conversion run in thread pool workers; async migration is deferred
- No download resume — interrupted downloads restart from zero
- Mermaid.js loads from CDN; not cached by service worker (requires internet for first flowchart)
- CORE search silently returns `[]` if `CORE_API_KEY` is unset
- `internet_archive` and `archive` both map to `_search_archive` for backwards compatibility
- 5 pre-existing test failures (see Commands section above)

---

## Completed Phases (for context; do not re-implement)

| Phase | Description |
|---|---|
| Scholara pivot | EduLoad → Scholara, open-access sources, AI routing, i18n |
| Francophone + DevOps | HAL/Persée/OpenEdition/Érudit, citations, Docker, persistent queue |
| Bilingual UI | Full EN/FR i18n, Francophone routing logic |
| 1 | Router extraction from monolithic `app.py` |
| 2 | Auth guards, rate limiting, quota |
| 3 | Conversion sandboxing — 5-layer hardening |
| 4 | Repository layer — all SQL through `repositories/` |
| 5 | Frontend login/logout UI for `multi_user` mode |
| 6 | Search deduplication + reranking pipeline |
| 7 | Frontend modularisation — 7 ES modules + template |
| 8 | Institutional: shared collections, analytics, branding |
| Demo | Interactive Demo: extract, explain, summary, chat, presentation, flowchart |
| Bug fixes | arXiv extension fix, HTML rejection, French detection 3-tier, lifespan handler, convert alias |

---

## For Deeper Context

Consult these before guessing:

- `CONTEXT_FOR_CLAUDE.md` — full API reference, schema, config vars, GUI reference
- `GUI_REFERENCE.md` — UI layout, panel/tab structure, modal flows
- `tests/conftest.py` — full SQLite schema as DDL (source of truth for table structure)
- `config/settings.py` — `AIConfig`, `MarketSegment`, `APP_MODE` and all env vars
- `core/ai_router.py` — AI waterfall (Ollama → DeepSeek → fallback)
- `prompts/` — all prompt templates and their placeholder conventions
