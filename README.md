# Scholara — Open-Access Academic Research Platform

A bilingual (EN/FR) local-first web app for discovering, downloading, converting, citing, and deeply interacting with free academic resources — built for researchers, NGOs, academic institutions, and independent learners worldwide, with a focus on Africa and the Global South.

Runs at **http://127.0.0.1:7860** · No account required in single-user mode · Fully offline-capable with Ollama

---

## Quick Start

```bash
# 1. Create virtual environment and install dependencies
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) Start Ollama for AI-powered search routing
ollama pull mistral && ollama serve

# 3. Run Scholara — opens browser automatically
python app.py
```

---

## Docker

```bash
# Build and run with Ollama sidecar included
docker-compose up --build
```

App at **http://localhost:7860**. Ollama models persisted in a named volume.

```bash
# Switch AI backend to DeepSeek
AI_BACKEND=deepseek DEEPSEEK_API_KEY=sk-... docker-compose up

# Enable multi-user mode
APP_MODE=multi_user SECRET_KEY=your-secret docker-compose up
```

---

## Features

### Search — Bilingual, Multi-Source, AI-Routed

Describe what you need in plain English or French. The AI router selects the most relevant sources automatically, deduplicates results, and reranks them by relevance.

**Core sources** (always active, 9 total):

| Source | Language | Type |
|--------|----------|------|
| arXiv | EN | Preprints — STEM |
| DOAJ | EN/FR | Peer-reviewed open-access journals |
| OpenAlex | EN | Cross-disciplinary academic |
| Internet Archive | EN | Books, documents, media |
| Project Gutenberg | EN | Public-domain books |
| HAL | FR/EN | French national open archive |
| Persée | FR | French humanities journals |
| OpenEdition | FR/EN | Francophone social sciences |
| Érudit | FR/EN | Québec & Francophone research |

**Extended sources** (enabled when `MARKET_SEGMENT=global-north`, 5 additional):

| Source | Language | Type |
|--------|----------|------|
| Semantic Scholar | EN | STEM, citation graph |
| PubMed | EN | Biomedical & life sciences |
| CrossRef | EN | DOI registry, all disciplines |
| CORE | EN | OA aggregator, global repositories |
| BASE | EN/Multilingual | European institutional coverage |

**Search intelligence:**
- Deduplication: exact DOI match + Jaccard similarity > 0.9 on normalised title tokens
- Reranking: weighted score — language match, DOI, abstract, recency, open-access flag
- `X-Search-Deduped` and `X-Search-Reranked` response headers
- Query stems recorded for analytics

### Interactive AI Demo

Right-click any file in the file list or history, or select any text on the page, to open the **Demo Sidebar** with five AI-powered actions:

| Action | What it does |
|--------|-------------|
| **Text Explanation** | Plain-language explanation for non-specialists |
| **Summary** | Structured summary: topic, findings, methodology, limitations |
| **Interactive Demo** | Multi-turn AI chat grounded in the document |
| **Presentation** | Slide-by-slide outline rendered as cards |
| **Flowchart** | Mermaid.js diagram of the main process or argument |

Text is extracted from `.pdf`, `.docx`, `.html`, `.txt`, `.md` files via the `POST /api/extract` endpoint. Works entirely offline when Ollama is running. Falls back gracefully when no AI backend is available.

### Citation Export

Export any downloaded document from the History panel:

```
GET /api/cite/{id}?format=bibtex
GET /api/cite/{id}?format=ris
GET /api/cite/{id}?format=apa
```

### Download

- Direct HTTP from whitelisted open-access domains only (arxiv.org, hal.science, doaj.org, archive.org, gutenberg.org, persee.fr, and more)
- Jobs survive server restarts — persisted in the `download_queue` SQLite table
- Up to 3 concurrent downloads
- Real-time progress via SSE at `/api/progress/{job_id}`
- `global-north` mode: yt-dlp enabled after accepting copyright disclaimer

### File Conversion

| From | To | Requires |
|------|----|----------|
| PDF | Word (.docx), plain text, HTML | pypdf, pdf2docx (included) |
| Word (.docx) | PDF, HTML, Markdown, plain text | mammoth (included) |
| Markdown / HTML / text | PDF, Word, HTML | included |
| Video (mp4, webm…) | MP3, WAV, AAC, OGG, FLAC | system ffmpeg |

All document conversions are pure Python — no system tools required. Conversion is 5-layer hardened: path validation, size cap, MIME check, timeout kill, subprocess isolation.

### History, Tags, and Collections

- Every download recorded with title, source, size, timestamp, authors, year, journal, language
- Tag any history entry for later filtering
- Group entries into named **Collections** for research project organisation
- Shared collections: share any collection with your institution in multi-user mode

### Institutional Features (multi-user mode)

- **Shared Collections**: share a collection with all users in your institution
- **Usage Analytics**: downloads by day (last 30), top search queries, top sources, active users per week — available at `GET /api/admin/impact`
- **Institution Branding**: logo URL and primary colour applied as CSS variable on load
- Admin canvas bar chart in the sidebar analytics tab

---

## AI Backend

| Backend | How to enable | Notes |
|---------|--------------|-------|
| **Ollama** (default) | Run `ollama serve` | Free, fully offline, any model |
| **DeepSeek** | `DEEPSEEK_API_KEY=sk-...` | Cloud, cheap, OpenAI-compatible |
| **Keyword fallback** | Automatic | Always works, no AI calls |

The same three-tier waterfall is used for both search routing and the interactive demo feature.

---

## Deployment Modes

| Variable | Value | Behaviour |
|----------|-------|-----------|
| `APP_MODE` | `single_user` (default) | No auth — works out of the box; synthetic admin user |
| `APP_MODE` | `multi_user` | JWT Bearer auth; roles (admin / researcher / student); audit log; per-user quotas |
| `MARKET_SEGMENT` | `global-south` (default) | 9 core open-access sources |
| `MARKET_SEGMENT` | `global-north` | All 14 sources + yt-dlp (behind copyright disclaimer) |

In `multi_user` mode: register at `/api/auth/register`, log in at `/api/auth/login`.  
Admin routes at `/api/admin/*` — user management, usage stats, audit log, impact report.

---

## Environment Variables

See `config/.env.example` for the full template.

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_MODE` | `single_user` | `single_user` / `multi_user` |
| `MARKET_SEGMENT` | `global-south` | `global-south` / `global-north` |
| `SECRET_KEY` | _(dev default)_ | JWT signing secret — **change in production** |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `mistral` | Ollama model name |
| `DEEPSEEK_API_KEY` | _(empty)_ | DeepSeek cloud API key |
| `CORE_API_KEY` | _(empty)_ | CORE search API key (free at core.ac.uk) |
| `MAX_EXTRACT_SIZE_MB` | `50` | Max file size for text extraction |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token TTL |

---

## API Reference

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve `index.html` |
| GET | `/api/status` | Tools, files, AI backend, mode, branding |

### Auth (`multi_user` mode)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account `{email, password, role?}` |
| POST | `/api/auth/login` | Returns `access_token`, `refresh_token` |
| POST | `/api/auth/refresh` | Refresh access token `{refresh_token}` |
| GET | `/api/auth/me` | Current user info |

### Admin (requires `admin` role)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/users` | List all users |
| DELETE | `/api/admin/users/{id}` | Delete user |
| PATCH | `/api/admin/users/{id}/role` | Change role |
| GET/POST | `/api/admin/institutions` | List / create institutions |
| GET | `/api/admin/usage` | Usage stats by endpoint |
| GET | `/api/admin/audit` | Audit log |
| GET | `/api/admin/impact` | Downloads/day, top queries, top sources, active users |

### Search
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/search` | `{query, sources[], limit}` | Direct multi-source search |
| POST | `/api/nl_search` | `{text}` | AI-routed natural language search |

### Downloads
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/download` | Enqueue download `{url, ...metadata}` |
| GET | `/api/progress/{job_id}` | SSE progress stream |
| GET | `/api/queue` | All jobs |
| DELETE | `/api/queue/{job_id}` | Cancel job |

### Files & Conversion
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/file/{filename}` | Serve file |
| DELETE | `/api/file/{filename}` | Delete file |
| POST | `/api/convert` | Convert `{filename, to_fmt}` |

### Interactive Demo
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/api/extract` | `{filename?, text?, max_chars?}` | Extract + chunk text from file or raw input |
| POST | `/api/demo` | `{action, text, message?, history?, language?}` | AI action: explain / summary / chat / presentation / flowchart |

### History & Collections
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/history` | Download history |
| POST | `/api/history/{id}/tag` | Set tags |
| DELETE | `/api/history/{id}` | Remove entry |
| GET/POST | `/api/collections` | List / create collections |
| GET | `/api/collections/shared` | Shared collections for user's institution |
| GET | `/api/collections/{id}` | Collection + items |
| POST | `/api/collections/{id}/share` | Share with institution |
| POST | `/api/collections/{id}/items` | Add item |
| DELETE | `/api/collections/{id}` | Delete collection |

### Citations & Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/cite/{id}?format=bibtex\|ris\|apa` | Export citation |
| GET/POST | `/api/settings` | Read / write settings |

---

## External Tools

| Tool | Purpose | Required? |
|------|---------|-----------|
| **ffmpeg** | Video/audio conversion | Optional (system binary) |
| **yt-dlp** | Video downloads (Global North only) | Installed via pip; gated by disclaimer |

Document conversions are pure Python. Status badges in the header show ✓ / ✗ for each tool.

---

## PWA

Scholara installs as a Progressive Web App on desktop and mobile. On Chrome/Edge, look for the ⊕ icon in the address bar. On Android, use "Add to Home Screen" from the browser menu.

The service worker (`static/sw.js`) caches all static assets for offline access. API calls always go to the network.

---

## License & Ethics

Scholara searches only open-access, public-domain, and freely licensed academic sources. Always respect the copyright and terms of service of each content provider.
