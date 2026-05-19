# Scholara — App Context for Claude

Use this document to get up to speed on Scholara before a technical conversation.

> The project was originally named **EduLoad**. All references to EduLoad, yt-dlp (as a top-level feature), Apify, Anthropic, or `adm_app.db` are from the old codebase — ignore them.

---

## What is Scholara?

**Scholara** is a self-hosted, AI-augmented open-access academic research platform for researchers, NGOs, academic institutions, and independent learners worldwide. It has built-in support for Francophone sources and a configurable `MARKET_SEGMENT` that unlocks extended coverage. It supports both single-user local deployments and multi-user institutional deployments.

Core capabilities:
- Search across up to 14 academic sources with a natural-language query (bilingual EN/FR)
- Download PDFs and documents from a whitelisted set of open-access domains
- Export citations in BibTeX, RIS, or APA format
- Convert files between formats (PDF↔DOCX, video→audio, etc.)
- Organise downloads with history, tags, and named collections — shareable with an institution
- Interactive AI Demo: right-click any file or selected text for explain / summary / chat / presentation / flowchart
- Run as a PWA installable on mobile
- Deploy in `single_user` mode (no auth) or `multi_user` mode (JWT auth, roles, audit logging)

Served at `http://127.0.0.1:7860` by default.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14+, FastAPI, Uvicorn |
| Frontend | Vanilla HTML/CSS, ES modules (`static/js/*.js`), no framework |
| Database | SQLite (`scholara.db`) via Python `sqlite3` |
| AI routing (primary) | **Ollama** local LLM (`mistral` by default) — free, runs offline |
| AI routing (cloud fallback) | **DeepSeek API** (`deepseek-chat`) — cheap, OpenAI-compatible |
| AI routing (last resort) | Keyword heuristic in `core/fallback.py` |
| HTTP client (AI + search) | `httpx` (async, AI calls); `requests` (sync, search functions) |
| Auth | `python-jose[cryptography]` (JWT), `passlib[bcrypt]` (password hashing) |
| Document conversion | `pdf2docx`, `pypdf`, `mammoth`, `xhtml2pdf`, `python-docx`, `html2text`, `markdown` |
| Video/audio | System `ffmpeg` (optional); `yt-dlp` (Global North only, via subprocess) |
| Retries | `tenacity` |
| Fonts | Google Fonts — Syne, IBM Plex Mono, Lora |

---

## Project Layout

```
adm_app/
├── app.py                   # FastAPI entry point — startup, /api/status, PWA icons
├── db.py                    # get_db() → sqlite3.Connection with row_factory
├── requirements.txt
├── scholara.db              # SQLite — created on first run
├── Dockerfile               # python:3.11-slim, installs ffmpeg, exposes 7860
├── docker-compose.yml       # scholara + ollama sidecar
├── downloads/               # Default download folder (configurable)
│
├── auth/
│   ├── dependencies.py      # get_current_user(), require_role()
│   ├── jwt_handler.py       # create_access_token(), create_refresh_token(), decode_token()
│   └── password.py          # hash_password(), verify_password()
│
├── routers/                 # All FastAPI APIRouters
│   ├── auth.py              # /api/auth/login|register|refresh|me
│   ├── admin.py             # /api/admin/users|institutions|usage|audit|impact
│   ├── search.py            # /api/search, /api/nl_search
│   ├── download.py          # /api/download, /api/queue, /api/progress
│   ├── history.py           # /api/history
│   ├── collections.py       # /api/collections (+ /shared, /{id}/share)
│   ├── files.py             # /api/file
│   ├── convert.py           # /api/convert
│   ├── settings.py          # /api/settings
│   ├── citations.py         # /api/cite
│   ├── extract.py           # /api/extract — text extraction (Demo Phase 1)
│   └── demo.py              # /api/demo — AI actions (Demo Phase 2)
│
├── repositories/            # All SQL — routers and services never call .execute() directly
│   ├── users.py             # get_user_by_email/id, create_user, list_users, delete_user, update_role
│   ├── usage.py             # record, get_stats, count_today, record_query, top_queries,
│   │                        # downloads_by_day, active_users_per_week
│   ├── audit.py             # log, list_logs
│   ├── institutions.py      # list_institutions, create_institution, get_institution_branding
│   ├── collections.py       # list_collections, create_collection (owner_id), get_collection,
│   │                        # get_collection_items, add_item, remove_item, delete_collection,
│   │                        # share_collection, list_shared_collections
│   ├── queue.py             # get_job, list_jobs, cancel_job
│   └── history.py           # get_history, add_history_entry, tag_entry, delete_entry,
│                            # get_entry, top_sources
│
├── schemas/
│   └── auth.py              # LoginRequest, RegisterRequest, TokenResponse, UserOut
│
├── services/
│   ├── audit.py             # record_usage(), audit() — no-ops in single_user mode
│   ├── quota.py             # check_quota() — raises HTTP 429
│   ├── rate_limit.py        # check(key, limit, window_secs), apply(request, user), reset()
│   ├── convert.py           # do_convert() — 5-layer hardened: path, size, MIME, timeout, subprocess
│   └── download.py          # enqueue_job(), get_download_dir(), load_jobs_from_db(), workers
│
├── models/                  # Reserved for future SQLAlchemy ORM
│
├── core/
│   ├── ai_router.py         # AISearchRouter — Ollama → DeepSeek → fallback waterfall
│   ├── claude_router.py
│   ├── downloader.py        # DirectDownloader, _ytdlp_allowed()
│   └── fallback.py          # FRENCH_KEYWORDS, _is_french(), fallback_routing()
│
├── prompts/
│   ├── router_system.txt    # Primary AI router system prompt
│   ├── claude_search_system.txt
│   ├── claude_search_examples.txt
│   └── demo/                # Demo action prompt templates
│       ├── explain.txt      # Placeholders: {text}, {language}
│       ├── summary.txt      # Placeholders: {text}, {language}
│       ├── chat.txt         # Placeholders: {text}, {language}, {message}
│       ├── presentation.txt # Returns JSON array of slides
│       └── flowchart.txt    # Returns Mermaid flowchart TD string
│
├── config/
│   ├── settings.py          # AIConfig, MarketSegment, APP_MODE
│   └── .env.example
│
├── utils/
│   └── cache.py             # ResponseCache — in-memory TTL cache (default 300 s)
│
├── static/
│   ├── index.html           # SPA shell — all HTML structure, CSS, i18n translations
│   ├── manifest.json
│   ├── sw.js                # Service worker (cache: scholara-v4)
│   ├── icon-192.png
│   ├── icon-512.png
│   └── js/
│       ├── app.js           # Entry point — wires all modules, settings, tabs, branding
│       ├── i18n.js          # TRANSLATIONS, currentLang, t(), applyTranslations(), setLang()
│       ├── auth.js          # initAuth(), showLoginModal(), token management, setMultiUser()
│       ├── api.js           # apiFetch(), $(), fmtBytes(), extIcon(), esc(), showMsg()
│       ├── download.js      # loadStatus() → returns data; renderFileList(), trackProgress(),
│       │                    # renderQueuePanel(), openViewer(), initDownload()
│       ├── search.js        # quickDownload(), initSearch()
│       ├── collections.js   # loadHistory(), loadCollections(), initCollections()
│       └── demo.js          # initDemo(), launchDemoAction(), showDemoContextMenu()
│                            # — context menu + sidebar panel for all 5 AI actions
│
└── tests/
    ├── conftest.py          # temp_db fixture (monkeypatches db.DB_PATH); all table DDL
    ├── test_phase1.py       # 18 tests — router extraction
    ├── test_phase2.py       # 22 tests — auth, rate limit, quota
    ├── test_phase3.py       # 20 tests — conversion sandboxing
    ├── test_phase4.py       # 23 tests — repository layer, no-raw-SQL structural check
    ├── test_phase5.py       # 21 tests — frontend auth (login modal, token refresh)
    ├── test_phase6.py       # 18 tests — dedup, rerank, search headers
    ├── test_phase7.py       # 15 tests — JS module structure
    ├── test_phase8.py       # 14 tests — shared collections, analytics, branding
    ├── test_demo.py         # 21 tests — /api/extract, /api/demo
    ├── test_downloader.py
    ├── test_claude_search.py
    ├── test_fallback.py
    └── test_gn_search.py
```

---

## Configuration

All env vars loaded from `config/.env` or root `.env`. See `config/.env.example` for the full template.

| Variable | Default | Purpose |
|---|---|---|
| `AI_BACKEND` | `ollama` | `ollama` / `deepseek` / `fallback` / `auto` |
| `OLLAMA_MODEL` | `mistral` | Ollama model name |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server base URL |
| `DEEPSEEK_API_KEY` | _(empty)_ | DeepSeek cloud API key |
| `AI_CACHE_TTL` | `300` | Seconds to cache AI routing responses |
| `MARKET_SEGMENT` | `global-south` | `global-south` / `global-north` |
| `CORE_API_KEY` | _(empty)_ | CORE search API key (optional) |
| `APP_MODE` | `single_user` | `single_user` / `multi_user` |
| `SECRET_KEY` | _(dev default)_ | JWT signing secret |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token TTL |
| `MAX_EXTRACT_SIZE_MB` | `50` | Max file size for `/api/extract` |

`AIConfig` in `config/settings.py` exposes all of the above as class attributes. Helpers: `AIConfig.is_north()`, `AIConfig.is_south()`, `AIConfig.is_multi_user()`.

---

## Key Technical Patterns

### Repository Pattern
Every function in `repositories/` takes `db: sqlite3.Connection` as its first argument. The caller (router or service) opens and closes the connection. No business logic in repos.

**Rule:** Routers and services must never call `.execute()` directly. All SQL goes through `repositories/`. Enforced by `TestNoRawSqlInRouters` in `test_phase4.py`.

### Auth Flow
- `get_current_user()` in `auth/dependencies.py`: in `single_user` mode returns synthetic `{"id": 0, "email": "local@scholara", "role": "admin", "institution_id": None}` — no token required. In `multi_user` mode, decodes Bearer JWT.
- `require_role("admin")` → returns a `Depends()` callable that checks the `role` field.
- Frontend `apiFetch()` in `api.js`: injects `Authorization` header in multi-user mode; on 401, attempts refresh once, then shows login modal.

### Rate Limiter
`services/rate_limit.py` — sliding window, in-memory, thread-safe:
- `check(key, limit, window_secs)` → `bool`
- `apply(request, user)` → raises HTTP 429 if exceeded (default: 30/min single_user, 20/min multi_user)
- `reset(key?)` → clears state (used in tests)
- Routers that need custom limits use `check()` directly with their own key prefix

### AI Waterfall (search + demo)
1. Try Ollama (`POST {OLLAMA_URL}/api/generate`, `stream=False`)
2. If fails/unavailable and DeepSeek key set: try `POST https://api.deepseek.com/chat/completions`
3. If both fail: keyword fallback (for search) or canned message (for demo)

### Search Pipeline
`services/search.py` `aggregate_search()`:
1. Fan out to selected sources in thread pool
2. `rerank(results, query_lang)` — weighted score sort
3. `deduplicate(results)` — DOI exact match + Jaccard > 0.9 on normalised title tokens
4. Cap at `limit`
5. Returns `(results, deduped_count, reranked_count)`

### Demo Prompt Substitution
`prompts/demo/*.txt` use `{text}`, `{language}`, `{message}` as placeholders. Substitution is done via `.replace()`, **not** `str.format()`, to avoid conflicts with JSON curly braces in `presentation.txt`.

### Frontend Module Dependencies
```
i18n.js       (no imports)
auth.js    ← i18n.js
api.js     ← auth.js, i18n.js
download.js← api.js, i18n.js
search.js  ← api.js, i18n.js, download.js
collections← api.js, i18n.js, download.js
demo.js    ← api.js, i18n.js
app.js     ← all modules
```
No circular dependencies. `auth.js` uses bare `fetch()` for login (not `apiFetch()`) to avoid the cycle.

---

## SQLite Schema (current, as of Phase 8 + Demo)

```sql
history(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT (datetime('now')),
  url TEXT, title TEXT, source TEXT, filename TEXT,
  size_kb INTEGER, tags TEXT,
  authors TEXT, year INTEGER, journal TEXT, language TEXT
)
download_queue(
  job_id TEXT PRIMARY KEY, url TEXT NOT NULL,
  status TEXT DEFAULT 'queued', progress REAL DEFAULT 0,
  error TEXT, result_filename TEXT,
  created_at TEXT, updated_at TEXT
)
collections(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, description TEXT,
  owner_id INTEGER,          -- Phase 8a
  institution_id INTEGER,    -- Phase 8a
  is_shared INTEGER DEFAULT 0,  -- Phase 8a
  created_at TEXT
)
collection_items(id, collection_id, history_id, position)
settings(key TEXT PRIMARY KEY, value TEXT)
institutions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, country TEXT,
  logo_url TEXT,        -- Phase 8c
  primary_color TEXT,   -- Phase 8c
  created_at TEXT
)
users(id, email UNIQUE NOT NULL, password_hash TEXT NOT NULL,
      role TEXT DEFAULT 'researcher', institution_id INTEGER, created_at TEXT)
usage(id, user_id INTEGER, endpoint TEXT, tokens_used INTEGER DEFAULT 0, created_at TEXT)
audit_logs(id, user_id INTEGER, action TEXT, target TEXT, created_at TEXT)
search_queries(id, query_stem TEXT NOT NULL, created_at TEXT)  -- Phase 8b
```

All tables are created with `IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN` migrations run on startup — safe against an existing DB.

---

## API Reference

Port 7860. Auth required on `/api/admin/*` in `multi_user` mode only.

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve `index.html` |
| GET | `/api/status` | tools, files, ollama_available, app_mode, market_segment, active_sources, institution_branding |

### Auth
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | `{email, password, role?, institution_id?}` | Create user (201) |
| POST | `/api/auth/login` | `{email, password}` | Returns `access_token`, `refresh_token`, `role` |
| POST | `/api/auth/refresh` | `{refresh_token}` | Returns new `access_token` |
| GET | `/api/auth/me` | — | Current user info |

### Admin (requires `admin` role)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/users` | List all users |
| DELETE | `/api/admin/users/{id}` | Delete user |
| PATCH | `/api/admin/users/{id}/role` | Change role `{role}` |
| GET | `/api/admin/institutions` | List institutions |
| POST | `/api/admin/institutions` | Create `{name, country?}` |
| GET | `/api/admin/usage` | Usage stats grouped by endpoint |
| GET | `/api/admin/audit` | Audit log (last 100 actions, `?limit=N`) |
| GET | `/api/admin/impact` | `{total_downloads, total_users, sources_used, downloads_by_day, top_queries, top_sources, active_users_week}` |

### Search
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/search` | `{query, sources[], limit}` | Multi-source search (deduped + reranked) |
| POST | `/api/nl_search` | `{text}` or `{query}` | AI-routed NL search |

Both return `X-Search-Deduped` and `X-Search-Reranked` headers.

### Downloads
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/download` | `{url, disclaimer_accepted?, title?, authors?, year?, journal?, language?}` | Enqueue; enforces whitelist |
| GET | `/api/progress/{job_id}` | — | SSE stream |
| GET | `/api/queue` | — | All jobs |
| DELETE | `/api/queue/{job_id}` | — | Cancel job |

### Interactive Demo
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/extract` | `{filename?, text?, max_chars?}` | Extract text from file or raw input; returns `{source, filename, total_chars, chunks[], truncated}` |
| POST | `/api/demo` | `{action, text, message?, history?, language?}` | AI action — `action` ∈ `{explain, summary, chat, presentation, flowchart}`; returns `{action, result, slides?, parse_error?, backend_used}` |

Rate limits: extract 10/min, demo 20/min. Text cap: demo 12 000 chars, raw text input 50 000 chars.

### Files & Conversion
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/file/{filename}` | Serve download |
| DELETE | `/api/file/{filename}` | Delete file |
| POST | `/api/convert` | `{filename, to_fmt}` |

### History
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/history?limit=50` | Last N downloads |
| POST | `/api/history/{id}/tag` | Set tags `{tags}` |
| DELETE | `/api/history/{id}` | Remove entry |

### Collections
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/collections` | List all |
| POST | `/api/collections` | Create `{name, description}` |
| GET | `/api/collections/shared` | Shared collections for user's institution |
| GET | `/api/collections/{id}` | Collection + items |
| POST | `/api/collections/{id}/share` | Share with user's institution |
| POST | `/api/collections/{id}/items` | Add item `{history_id, position}` |
| DELETE | `/api/collections/{id}/items/{item_id}` | Remove item |
| DELETE | `/api/collections/{id}` | Delete |

Note: `/api/collections/shared` must be registered **before** `/api/collections/{id}` in FastAPI to avoid routing conflict.

### Citations & Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cite/{id}?format=bibtex\|ris\|apa` | Export citation |
| GET | `/api/settings` | All key-value settings |
| POST | `/api/settings` | Upsert `{key: value}` |

---

## Running the App

```bash
# Python (system Python 3.14)
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
# Opens http://127.0.0.1:7860 automatically

# With multi-user mode
APP_MODE=multi_user SECRET_KEY=your-secret python app.py

# Docker
docker-compose up --build
```

**venv note:** The `my-venv` at `/home/chama/my-venv` uses Python 3.14 packages and is the active venv for this project. Do not use the system Python directly.

---

## Completed Phases

| Phase | Commit | Description |
|-------|--------|-------------|
| Scholara pivot | `bfff742` | EduLoad → Scholara, open-access sources, AI routing, i18n |
| Francophone + DevOps | `4cca5fd` | HAL/Persée/OpenEdition/Érudit, citations, Docker, persistent queue |
| Bilingual UI | `764c76f` | Full EN/FR i18n, Francophone routing logic |
| Phase 1 | `20e8593` | Router extraction from monolithic app.py |
| Phase 2 | `f8a72d0` | Auth guards, rate limiting, quota |
| Phase 3 | `b5b2962` | Conversion sandboxing — 5-layer hardening |
| Phase 4 | `10d8518` | Repository layer — all SQL through repositories/ |
| Phase 5 | `e49dc59` | Frontend login/logout UI for multi_user mode |
| Phase 6 | `33d5bf6` | Search deduplication + reranking pipeline |
| Phase 7 | `aa80d53` | Frontend modularisation — 7 ES modules + template |
| Phase 8 | `a04fb47` | Institutional: shared collections, analytics, branding |
| Demo | `065d57e` | Interactive Demo: extract, explain, summary, chat, presentation, flowchart |

---

## Known Limitations

- **`app.py` startup uses deprecated `@app.on_event("startup")`** — FastAPI deprecation warning only; does not affect functionality. Migrate to `lifespan=` when convenient.
- **Synchronous search + conversion**: all 14 search functions and `/api/convert` run synchronously in thread pool workers. Async migration is deferred.
- **No download resume**: interrupted downloads must restart from the beginning.
- **Mermaid.js from CDN**: the flowchart renderer loads Mermaid lazily from `cdnjs.cloudflare.com`. It is not cached by the service worker — requires internet for first flowchart request.
- **5 pre-existing test failures**: 3 asyncio `get_event_loop()` incompatibilities (Python 3.14 removed this API); 2 EduLoad-era tests expecting `youtube`/`duckduckgo` sources. These are not regressions.
- **CORE search**: silently returns `[]` if `CORE_API_KEY` is not set.
- **`internet_archive` and `archive`**: both keys map to `_search_archive` for compatibility.
