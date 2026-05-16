# EduLoad

**A local desktop app for finding, downloading, converting, and viewing free educational resources.**

EduLoad runs entirely on your machine (no account, no cloud) and exposes a browser-based UI at `http://127.0.0.1:7860`. It aggregates open-access content from seven sources, manages downloads through a queue, and includes a built-in file viewer — all from one window.

---

## What It Does

| Capability | Details |
|---|---|
| **Multi-source search** | Query arXiv, Project Gutenberg, DOAJ, YouTube, OpenAlex, Internet Archive, and DuckDuckGo simultaneously |
| **Natural language search** | Describe what you need in plain text; the app selects the right sources automatically |
| **URL download** | Paste any URL — yt-dlp handles 1000+ video sites (YouTube, Vimeo, Dailymotion…); direct HTTP files are downloaded chunk-by-chunk |
| **Batch download** | Queue multiple URLs at once; up to 3 run in parallel |
| **File conversion** | Video → MP3, DOCX/HTML/Markdown → PDF, PDF → DOCX, HTML → DOCX |
| **Built-in viewer** | Play video/audio, view PDF, render HTML, read plain text and SRT subtitles — all in-browser |
| **Download history** | Every download is recorded with title, source, size, and timestamp |
| **Collections** | Group history items into named collections for organization |
| **Configurable settings** | Download directory, quality presets, subtitle languages, dark mode, concurrent download limit |

---

## Tech Stack

**Backend**
- Python 3.x · FastAPI · Uvicorn · SQLite

**Frontend**
- Vanilla JavaScript · Plain HTML5/CSS · no build step

**External tools** (optional; the app degrades gracefully if missing)
- `yt-dlp` — video downloading (auto-updated on startup)
- `ffmpeg` — audio extraction
- `pandoc` — document conversion
- `pdf2docx` — PDF-to-DOCX conversion

---

## Getting Started

```bash
# One-time setup
bash setup.sh

# Run
python app.py
```

The app opens `http://127.0.0.1:7860` in your default browser automatically.

---

## Project Structure

```
adm_app/
├── app.py          # FastAPI backend — all API routes, download queue, search logic (~815 lines)
├── static/
│   └── index.html  # Single-page frontend — UI, viewer, real-time progress (~1743 lines)
├── requirements.txt
├── setup.sh
├── adm_app.db      # SQLite database (auto-created on first run)
└── downloads/      # Downloaded files land here by default
```

---

## Database Schema

```
history            — one row per completed download
collections        — named groups
collection_items   — links history rows to collections (many-to-many)
settings           — key/value store for user preferences
```

Key settings keys: `download_dir`, `dark_mode`, `default_quality`, `default_subs`, `max_concurrent`, `auto_open_viewer`.

---

## API Reference

### System
| Method | Path | Description |
|---|---|---|
| GET | `/` | Serve the SPA |
| GET | `/api/status` | Tool availability + current file list |
| GET | `/api/ytdlp_version` | Installed yt-dlp version |

### Downloads
| Method | Path | Description |
|---|---|---|
| POST | `/api/download` | Queue a single download |
| POST | `/api/batch` | Queue multiple downloads |
| GET | `/api/progress/{job_id}` | SSE stream for real-time progress |
| GET | `/api/queue` | List all jobs |
| DELETE | `/api/queue/{job_id}` | Cancel a queued job |

### Search
| Method | Path | Description |
|---|---|---|
| POST | `/api/search` | Search selected sources |
| POST | `/api/nl_search` | Natural language search (auto-selects sources) |

### Files & Conversion
| Method | Path | Description |
|---|---|---|
| GET | `/api/file/{filename}` | Serve a downloaded file |
| DELETE | `/api/file/{filename}` | Delete a file |
| POST | `/api/convert` | Convert a file to another format |

### History
| Method | Path | Description |
|---|---|---|
| GET | `/api/history` | List download history (`?limit=50`) |
| POST | `/api/history/{id}/tag` | Add tags to a history entry |
| DELETE | `/api/history/{id}` | Remove a history entry |

### Collections
| Method | Path | Description |
|---|---|---|
| GET | `/api/collections` | List all collections |
| POST | `/api/collections` | Create a collection |
| GET | `/api/collections/{id}` | Get a collection with its items |
| POST | `/api/collections/{id}/items` | Add a history item to a collection |
| DELETE | `/api/collections/{id}/items/{item_id}` | Remove an item |
| DELETE | `/api/collections/{id}` | Delete a collection |

### Settings
| Method | Path | Description |
|---|---|---|
| GET | `/api/settings` | Get all settings |
| POST | `/api/settings` | Save a setting (key + value body) |

---

## Known Limitations

- **No authentication** — designed for single-user local use only.
- **No download resume** — interrupted downloads must restart from the beginning.
- **yt-dlp auto-update blocks startup** — runs synchronously before the server is ready.
- **Search results not cached** — every search hits external APIs fresh.
- **Frontend polls every 2 s** for queue status instead of using WebSockets.
- **`download_jobs` dict grows indefinitely** — no cleanup of completed job records in memory.
- **Monolithic frontend** — all HTML, CSS, and JS live in a single 1743-line file.
- **No i18n** — all UI strings are hardcoded in English.

---

## Future Improvements

### High Priority
- **Download resume** — use HTTP `Range` headers to resume interrupted downloads.
- **Retry logic** — automatic retry with backoff for failed downloads and searches.
- **Startup yt-dlp update in background** — don't block the server while updating.
- **Search result caching** — cache API responses for a few minutes to reduce latency and external calls.

### User-Facing Features
- **Tagging UI** — the API supports tags on history entries but there is no UI for it yet.
- **Bulk file operations** — delete, move, or add multiple files to a collection at once.
- **Export / import** — export history and collections to JSON or CSV; import from backup.
- **Scheduled downloads** — set a URL to download at a specific time or on a recurring schedule.
- **Full-text search** — index downloaded text/PDF content for local search.
- **Video transcoding** — convert downloaded video to different resolutions, not just quality selection at download time.
- **Metadata editing** — rename, re-tag, or edit file metadata from the UI.

### Technical Improvements
- **Split the frontend** — break `index.html` into separate JS modules and a CSS file with a simple build step.
- **WebSocket queue updates** — replace the 2-second polling loop with a WebSocket or SSE stream.
- **Database connection pooling** — reuse connections instead of opening a new one per request.
- **Factory pattern for search sources** — replace seven near-identical search functions with a single configurable implementation.
- **Configurable search timeout** — expose the hardcoded 10-second API timeout as a setting.
- **File system watcher** — replace the 15-second file list refresh with `watchdog` or similar.
- **Path traversal hardening** — explicit sanitization on file-serving endpoints.
- **Stricter iframe sandbox** — tighten the `sandbox` attribute on the built-in viewer.

### Possible Integrations
- Additional search sources (e.g., PubMed, CORE, Semantic Scholar).
- Optional LLM-assisted search refinement or result summarization.
- Browser extension to push URLs directly to the download queue.
