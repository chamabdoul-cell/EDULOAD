# Scholara — Development Changelog

> This file tracks the full development history of the project, from its origin as **EduLoad** (a local download manager) through the complete **Scholara** pivot and all subsequent improvement phases.

---

## Origin — EduLoad (adm_app)

The project started as **EduLoad**, a single-user local desktop app for downloading educational resources. It exposed a browser UI at `http://127.0.0.1:7860` and aggregated content from seven sources including YouTube and DuckDuckGo.

**Original capabilities:**
- Multi-source search (arXiv, Gutenberg, DOAJ, YouTube, OpenAlex, Internet Archive, DuckDuckGo)
- yt-dlp for video downloads
- File conversion (video → audio, document formats)
- Built-in viewer
- SQLite history (`adm_app.db`)
- No authentication, no AI, English-only

**Original tech:** Python 3.x · FastAPI · SQLite · Vanilla JS · single monolithic `app.py` + `index.html`

---

## Scholara Pivot — EduLoad → Scholara

**Motivation:** Reposition for researchers, NGOs, and academic institutions in Africa and the Global South. Remove legally questionable sources (YouTube via yt-dlp, DuckDuckGo), add open-access academic databases, introduce AI-powered bilingual routing.

**Changes:**
- Renamed project to **Scholara** (`adm_app.db` → `scholara.db`)
- Removed YouTube and DuckDuckGo as default sources
- Added AI routing: Ollama → DeepSeek → keyword fallback (see `core/ai_router.py`)
- Added Francophone source routing: HAL, Persée, OpenEdition, Érudit
- Added bilingual EN/FR interface with `TRANSLATIONS` object
- Added URL domain whitelist — only open-access academic domains allowed
- yt-dlp now gated behind `MARKET_SEGMENT=global-north` + copyright disclaimer
- Added `MarketSegment` enum (`global-south` / `global-north`)
- Added citation export: BibTeX, RIS, APA (`/api/cite/{id}`)
- Added persistent download queue (SQLite-backed `download_queue` table)
- Added Docker + docker-compose with Ollama sidecar
- Added prompt files: `prompts/router_system.txt`, `prompts/claude_search_system.txt`

---

## Phase 1 — Router Extraction (commit `20e8593`)

Extracted all route groups from the monolithic `app.py` into dedicated `routers/` modules:

| Router | Prefix | File |
|--------|--------|------|
| Auth | `/api/auth` | `routers/auth.py` |
| Admin | `/api/admin` | `routers/admin.py` |
| Search | `/api/search`, `/api/nl_search` | `routers/search.py` |
| Download | `/api/download`, `/api/queue`, `/api/progress` | `routers/download.py` |
| History | `/api/history` | `routers/history.py` |
| Collections | `/api/collections` | `routers/collections.py` |
| Files | `/api/file` | `routers/files.py` |
| Convert | `/api/convert` | `routers/convert.py` |
| Settings | `/api/settings` | `routers/settings.py` |
| Citations | `/api/cite` | `routers/citations.py` |

`app.py` retained only startup, `_init_db()`, `/api/status`, and PWA icon generation.

---

## Phase 2 — Auth Guards, Rate Limiting, Quota (commit `f8a72d0`)

- Added `auth/` package: `dependencies.py`, `jwt_handler.py`, `password.py`
- `get_current_user()` — bypasses auth in `single_user` mode (synthetic admin); validates JWT in `multi_user` mode
- `require_role()` — role-based access control for admin endpoints
- Added `services/rate_limit.py` — sliding-window in-memory rate limiter (`check()`, `apply()`, `reset()`)
- Added `services/quota.py` — per-user daily quota enforcement (raises HTTP 429)
- Added `services/audit.py` — `record_usage()` and `audit()` (no-ops in `single_user` mode)
- Registered auth + admin routers; all admin routes require `admin` role
- DB tables: `users`, `institutions`, `usage`, `audit_logs`

---

## Phase 3 — Conversion Sandboxing (commit `b5b2962`)

Rewrote `services/convert.py` with 5-layer security hardening:

1. **`_check_path`** — resolve path inside `downloads/`, reject `../` traversal
2. **`_check_size`** — reject files > 200 MB
3. **`_check_mime`** — validate MIME type against expected type for extension
4. **`_timeout_call`** — wrap converters in `threading.Timer`, kill on timeout (30 s)
5. **`_run_ffmpeg`** — subprocess with `shell=False`, explicit arg list, no shell injection

All conversions use `tempfile.TemporaryDirectory` for isolation.

---

## Phase 4 — Database Abstraction Layer (commit `10d8518`)

Moved all SQL out of routers and services into `repositories/` modules:

| File | Functions |
|------|-----------|
| `repositories/users.py` | `get_user_by_email`, `get_user_by_id`, `create_user`, `list_users`, `delete_user`, `update_role` |
| `repositories/usage.py` | `record`, `get_stats`, `count_today` |
| `repositories/audit.py` | `log`, `list_logs` |
| `repositories/institutions.py` | `list_institutions`, `create_institution` |
| `repositories/collections.py` | `list_collections`, `create_collection`, `get_collection`, `get_collection_items`, `add_item`, `remove_item`, `delete_collection` |
| `repositories/queue.py` | `get_job`, `list_jobs`, `cancel_job` |
| `repositories/history.py` | `get_history`, `add_history_entry`, `tag_entry`, `delete_entry`, `get_entry` |

Rule: **no `.execute()` calls in routers or services** — enforced by a structural test (`TestNoRawSqlInRouters`).

---

## Phase 5 — Frontend Login / Logout UI (commit `e49dc59`)

Added full login/logout frontend for `multi_user` mode:

- Login modal: email + password fields, `#btnLogin`, `#btnLogout`, `#loginMsg`
- `_multiUser` flag set from `/api/status` → `app_mode === "multi_user"`
- `apiFetch()` wrapper: injects `Authorization: Bearer <token>` header; on 401, attempts token refresh once, then shows login modal
- Token storage in `localStorage`: `access_token`, `refresh_token`
- `loadStatus()` calls `showLoginModal()` if `multi_user` and no token found
- Replaced all bare `fetch('/api/...')` calls with `apiFetch()`

---

## Phase 6 — Search Intelligence (commit `33d5bf6`)

Added to `services/search.py`:

- **Deduplication**: exact DOI match + Jaccard similarity > 0.9 on normalised title tokens; keeps highest-scored duplicate
- **Reranking**: weighted score formula — +3 language match, +2 DOI present, +2 abstract present, +1 year ≥ 2020, +1 open-access flag
- **Pipeline**: `raw → rerank → deduplicate → cap at limit`
- `X-Search-Deduped` and `X-Search-Reranked` response headers on both `/api/search` and `/api/nl_search`
- `record_query()` called in search routers for analytics

---

## Phase 7 — Frontend Modularisation (commit `aa80d53`)

Split the monolithic `<script>` block in `index.html` (1900+ lines) into 7 ES modules:

| Module | Exports |
|--------|---------|
| `static/js/i18n.js` | `TRANSLATIONS`, `currentLang`, `t()`, `applyTranslations()`, `setLang()` |
| `static/js/auth.js` | `initAuth()`, `showLoginModal()`, token getters/setters, `setMultiUser()` |
| `static/js/api.js` | `apiFetch()`, `$()`, `fmtBytes()`, `extIcon()`, `esc()`, `showMsg()` |
| `static/js/download.js` | `loadStatus()`, `renderFileList()`, `trackProgress()`, `renderQueuePanel()`, `openViewer()`, `initDownload()` |
| `static/js/search.js` | `quickDownload()`, `initSearch()` |
| `static/js/collections.js` | `loadHistory()`, `loadCollections()`, `initCollections()` |
| `static/js/app.js` | Entry point — wires all modules, settings, tabs |

- `index.html` now uses `<script type="module" src="/static/js/app.js">` only
- All inline `onclick="fn()"` replaced with `data-action` + event delegation
- Added `<template id="tpl-file-item">` for file list rendering
- Service worker bumped to `scholara-v2`

---

## Phase 8 — Institutional Features (commit `a04fb47`)

### 8a — Shared Collections
- `collections` table: new columns `owner_id`, `institution_id`, `is_shared`
- New repo functions: `share_collection()`, `list_shared_collections()`
- Endpoints: `GET /api/collections/shared`, `POST /api/collections/{id}/share`
- UI: "Share with institution" checkbox in New Collection modal

### 8b — Usage Analytics
- New `search_queries` table
- `repositories/usage.py`: `record_query()`, `top_queries()`, `downloads_by_day()`, `active_users_per_week()`
- `repositories/history.py`: `top_sources()`
- `GET /api/admin/impact` extended: `downloads_by_day`, `top_queries`, `top_sources`, `active_users_week`
- Admin sidebar tab with text stats + `<canvas>` bar chart

### 8c — Institution Branding
- `institutions` table: new columns `logo_url`, `primary_color`
- `repositories/institutions.py`: `get_institution_branding()`
- `GET /api/status` returns `institution_branding` in `multi_user` mode
- Frontend applies `--accent` CSS variable override on load

---

## Interactive Demo Feature (commit `065d57e`)

### Phase D1 — Text Extraction Endpoint
- `routers/extract.py`: `POST /api/extract`
- Supports `.pdf` (pypdf), `.docx` (mammoth), `.html` (html2text), `.txt`/`.md` (stdlib)
- Validation: path traversal rejection, file size cap (`MAX_EXTRACT_SIZE_MB`, default 50 MB), extension allowlist
- Cleans text (strips page numbers, collapses blank lines, removes non-printable chars)
- Chunks to ≤ 2000 chars on sentence boundaries; returns `{source, filename, total_chars, chunks[], truncated}`
- Rate limit: 10 requests/min

### Phase D2 — AI Demo Endpoint
- `routers/demo.py`: `POST /api/demo`
- Five actions: `explain`, `summary`, `chat`, `presentation`, `flowchart`
- Prompt templates in `prompts/demo/*.txt` with manual placeholder substitution
- Same Ollama → DeepSeek → graceful canned fallback waterfall
- `presentation`: parses JSON slide array; falls back to raw text on parse error
- `flowchart`: returns raw Mermaid string
- `chat`: maintains conversation history (last 6 turns); supports DeepSeek multi-turn messages
- Rate limit: 20 requests/min; text cap: 12 000 chars

### Phase D3/D4 — Frontend Demo Sidebar
- `static/js/demo.js`: ES module wired into `app.js`
- Context menu appears on right-click on `[data-filename]` elements or text selection > 20 chars
- Sidebar slides in from the right (420 px; 100 vw on mobile < 600 px)
- Result renderers: markdown text (bold/italic/newlines), slide cards, interactive chat with Enter-to-send, Mermaid flowchart (lazy CDN load)
- `data-filename` / `data-filetype` attributes added to file list and history entries

### Phase D5 — Security
- Path traversal guard on `POST /api/extract`
- File size limit enforced before extraction
- Text length cap (12 000 chars) on `POST /api/demo`
- Rate limits via existing `services/rate_limit.py`
- Auth via `get_current_user` (bypassed in `single_user` mode)

### Phase D6 — Service Worker
- Bumped to `scholara-v4`
- `demo.js` added to static shell cache
- Mermaid CDN (cloudflare.com) explicitly excluded from caching

---

## Test Coverage Summary

| Test file | Tests | What it covers |
|-----------|-------|----------------|
| `tests/conftest.py` | — | `temp_db` fixture; all table DDL |
| `tests/test_phase1.py` | 18 | Router extraction |
| `tests/test_phase2.py` | 22 | Auth, rate limit, quota |
| `tests/test_phase3.py` | 20 | Conversion sandboxing |
| `tests/test_phase4.py` | 23 | Repository layer, no-raw-SQL |
| `tests/test_phase5.py` | 21 | Login/logout UI, token refresh |
| `tests/test_phase6.py` | 18 | Dedup, rerank, search headers |
| `tests/test_phase7.py` | 15 | JS module structure |
| `tests/test_phase8.py` | 14 | Institutional features |
| `tests/test_demo.py` | 21 | Extract + demo endpoints |
| `tests/test_gn_search.py` | varies | GN source shape tests |
| `tests/test_downloader.py` | varies | Download engine |
| `tests/test_fallback.py` | 5 (2 pre-existing) | Fallback routing |
| `tests/test_claude_search.py` | 3 (pre-existing) | AI search router (asyncio) |

**Total: 155 tests passing** (5 pre-existing failures from EduLoad era: 2 asyncio Python 3.14 incompatibilities on asyncio tests, 2 EduLoad-era tests expecting `youtube`/`duckduckgo` sources).

---

## Current File Structure

```
adm_app/
├── app.py                    # FastAPI entry point — startup, /api/status, PWA icons
├── db.py                     # get_db() → sqlite3.Connection
├── requirements.txt
├── scholara.db               # SQLite DB (auto-created)
├── Dockerfile
├── docker-compose.yml
├── downloads/
│
├── auth/
│   ├── dependencies.py       # get_current_user(), require_role()
│   ├── jwt_handler.py        # create_access_token(), decode_token()
│   └── password.py           # hash_password(), verify_password()
│
├── routers/
│   ├── auth.py               # /api/auth/*
│   ├── admin.py              # /api/admin/*
│   ├── search.py             # /api/search, /api/nl_search
│   ├── download.py           # /api/download, /api/queue, /api/progress
│   ├── history.py            # /api/history
│   ├── collections.py        # /api/collections
│   ├── files.py              # /api/file
│   ├── convert.py            # /api/convert
│   ├── settings.py           # /api/settings
│   ├── citations.py          # /api/cite
│   ├── extract.py            # /api/extract  [NEW — Demo Phase D1]
│   └── demo.py               # /api/demo     [NEW — Demo Phase D2]
│
├── repositories/
│   ├── users.py
│   ├── usage.py              # + record_query, top_queries, downloads_by_day, active_users_per_week
│   ├── audit.py
│   ├── institutions.py       # + get_institution_branding
│   ├── collections.py        # + share_collection, list_shared_collections
│   ├── queue.py
│   └── history.py            # + top_sources
│
├── services/
│   ├── audit.py              # record_usage(), audit()
│   ├── quota.py              # check_quota()
│   ├── rate_limit.py         # check(), apply(), reset()
│   ├── convert.py            # do_convert() — 5-layer hardened
│   └── download.py           # enqueue_job(), get_download_dir(), workers
│
├── schemas/
│   └── auth.py               # LoginRequest, RegisterRequest, TokenResponse
│
├── core/
│   ├── ai_router.py          # AISearchRouter — Ollama → DeepSeek → fallback
│   ├── claude_router.py
│   ├── downloader.py
│   └── fallback.py           # FRENCH_KEYWORDS, fallback_routing()
│
├── prompts/
│   ├── router_system.txt
│   ├── claude_search_system.txt
│   ├── claude_search_examples.txt
│   └── demo/                 # [NEW — Demo Phase D2]
│       ├── explain.txt
│       ├── summary.txt
│       ├── chat.txt
│       ├── presentation.txt
│       └── flowchart.txt
│
├── config/
│   ├── settings.py           # AIConfig, MarketSegment, APP_MODE
│   └── .env.example
│
├── utils/
│   └── cache.py              # ResponseCache (TTL in-memory)
│
├── static/
│   ├── index.html            # Main SPA — all HTML structure
│   ├── manifest.json
│   ├── sw.js                 # Service worker (cache: scholara-v4)
│   ├── icon-192.png
│   ├── icon-512.png
│   └── js/
│       ├── app.js            # Entry point
│       ├── i18n.js
│       ├── auth.js
│       ├── api.js
│       ├── download.js
│       ├── search.js
│       ├── collections.js
│       └── demo.js           # [NEW — Demo Phase D3/D4]
│
└── tests/
    ├── conftest.py           # temp_db fixture
    ├── test_phase1.py
    ├── test_phase2.py
    ├── test_phase3.py
    ├── test_phase4.py
    ├── test_phase5.py
    ├── test_phase6.py
    ├── test_phase7.py
    ├── test_phase8.py
    └── test_demo.py          # [NEW]
```

---

## SQLite Schema (current)

```sql
history(id, ts, url, title, source, filename, size_kb, tags,
        authors, year, journal, language)
download_queue(job_id, url, status, progress, error, result_filename,
               created_at, updated_at)
collections(id, name, description, owner_id, institution_id, is_shared,
            created_at)
collection_items(id, collection_id, history_id, position)
settings(key, value)
institutions(id, name, country, logo_url, primary_color, created_at)
users(id, email, password_hash, role, institution_id, created_at)
usage(id, user_id, endpoint, tokens_used, created_at)
audit_logs(id, user_id, action, target, created_at)
search_queries(id, query_stem, created_at)
```
