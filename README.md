# Scholara — Open-Access Academic Research Platform

A bilingual (EN/FR) local-first web app for discovering, downloading, converting, and citing
free academic resources — built for researchers, NGOs, academic institutions, and independent learners worldwide.

## Quick Start

```bash
# 1. Create virtual environment and install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) Start Ollama for AI-powered search routing
ollama pull mistral && ollama serve

# 3. Run Scholara (opens browser automatically)
python app.py
```

Then open **http://127.0.0.1:7860** if the browser doesn't open automatically.

---

## Docker

```bash
# Build and run with Docker Compose (includes Ollama sidecar)
docker-compose up --build
```

App available at **http://localhost:7860**. Ollama runs as a sidecar; models are persisted in a named volume.

```bash
# Use an external Ollama instance or switch to DeepSeek
AI_BACKEND=deepseek DEEPSEEK_API_KEY=sk-... docker-compose up

# Enable multi-user mode
APP_MODE=multi_user SECRET_KEY=your-secret docker-compose up
```

---

## Features

### Search — Bilingual, Multi-Source

Describe what you need in plain English or French. The AI router selects the most relevant sources automatically.

**Core sources** (always active):

| Source | Language | Type |
|--------|----------|------|
| arXiv | EN | Preprints (STEM) |
| DOAJ | EN/FR | Peer-reviewed open-access journals |
| OpenAlex | EN | Cross-disciplinary academic |
| Internet Archive | EN | Books, documents, media |
| Project Gutenberg | EN | Public-domain books |
| **HAL** | **FR/EN** | **French national open archive** |
| **Persée** | **FR** | **French humanities journals** |
| **OpenEdition** | **FR/EN** | **Francophone social sciences** |
| **Érudit** | **FR/EN** | **Québec & Francophone research** |

**Extended sources** (enabled when `MARKET_SEGMENT=global-north`):

| Source | Language | Type |
|--------|----------|------|
| Semantic Scholar | EN | STEM, citation graph |
| PubMed | EN | Biomedical & life sciences |
| CrossRef | EN | DOI registry, all disciplines |
| CORE | EN | OA aggregator, global repositories |
| BASE | EN/Multilingual | European institutional coverage |

Filter results by source with one click.

### Citation Export

Export any saved document from the history panel:

```
GET /api/cite/{history_id}?format=bibtex
GET /api/cite/{history_id}?format=ris
GET /api/cite/{history_id}?format=apa
```

### Download

- Direct HTTP downloads from whitelisted open-access domains
- Jobs survive server restarts (SQLite-backed persistent queue)
- Up to 3 concurrent downloads
- In `global-north` mode: yt-dlp available after accepting copyright disclaimer

### Convert (Pure Python — no system tools needed for documents)

| From | To |
|------|----|
| PDF | Word (.docx), plain text, HTML |
| Word (.docx) | PDF, HTML, Markdown, plain text |
| Markdown / HTML / text | PDF, Word, HTML |
| Video (mp4, webm…) | MP3, WAV, AAC, OGG (requires ffmpeg) |

### Built-in Viewer

- **PDF**: inline viewer
- **Video / Audio**: HTML5 player
- **HTML**: sandboxed iframe
- **Text**: plain text view

---

## AI Backend

| Backend | How to enable |
|---------|--------------|
| Ollama (default) | Run `ollama serve`; set `OLLAMA_URL` if non-default |
| DeepSeek | Set `AI_BACKEND=deepseek` and `DEEPSEEK_API_KEY` |
| Keyword fallback | Automatic when neither above is available |

Check `/api/status` for live backend info.

---

## Deployment Modes

| Variable | Value | Behaviour |
|---|---|---|
| `APP_MODE` | `single_user` (default) | No authentication — works out of the box |
| `APP_MODE` | `multi_user` | JWT Bearer auth required; roles (admin / researcher / student); audit logging |
| `MARKET_SEGMENT` | `global-south` (default) | 9 core open-access sources, no yt-dlp |
| `MARKET_SEGMENT` | `global-north` | All 14 sources (core + extended), yt-dlp enabled after disclaimer |

In `multi_user` mode, use `/api/auth/register` and `/api/auth/login` to manage users.
Admin routes live at `/api/admin/*` (usage stats, audit log, user management, impact report).

---

## Environment Variables

See `config/.env.example` for the full template. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `APP_MODE` | `single_user` | `single_user` / `multi_user` |
| `MARKET_SEGMENT` | `global-south` | `global-south` / `global-north` |
| `SECRET_KEY` | _(dev default)_ | JWT signing secret — **change in production** |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `DEEPSEEK_API_KEY` | _(empty)_ | DeepSeek cloud API key |
| `CORE_API_KEY` | _(empty)_ | CORE search API key (free at core.ac.uk) |

---

## External Tools

| Tool | Purpose | Required? |
|------|---------|-----------|
| **ffmpeg** | Video/audio conversion | Optional |
| **yt-dlp** | Video downloads (Global North only) | Optional |

Document conversions (PDF↔DOCX, etc.) are pure Python — no system tools needed.

Status badges in the app header show ✓ / ✗ for detected tools.

---

## Downloads Folder

All files saved to `downloads/`. Configurable in Settings. Managed from the sidebar.

---

## License & Ethics

Scholara searches only open-access, public-domain, and freely licensed academic sources.
Always respect the copyright and terms of service of each content provider.
