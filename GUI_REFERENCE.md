# Scholara — GUI Reference

Complete description of the Scholara web interface: its layout, panels, controls, and interactive flows.

Served at `http://127.0.0.1:7860`. The entire UI is a single-page application (SPA) with no page reloads. It is installable as a Progressive Web App (PWA) on mobile.

---

## Layout overview

```
┌──────────────────────────────────────────────────────────────────┐
│  HEADER — logo · tool badges · lang · settings · sign out        │
├──────────────────┬───────────────────────────┬───────────────────┤
│   SIDEBAR        │ SPLITTER │  MAIN (results) │ SPLITTER │ VIEWER│
│   320 px         │          │  (flex 1)        │          │ 520 px│
│   (collapsible)  │          │                  │          │       │
└──────────────────┴──────────┴──────────────────┴──────────┴───────┘
```

Three resizable columns separated by drag handles ("splitters"). The sidebar can be collapsed to zero width via the hamburger button. All panels respect dark mode.

---

## 1. Header

Always visible at the top (height 58 px, dark background with a burnt-orange bottom border).

| Element | Description |
|---|---|
| ☰ Hamburger button | Collapses / expands the left sidebar with an animated slide |
| **Schol·ara** logo | Brand mark with subtitle "Open Knowledge, Everywhere" (or French equivalent) |
| Tool badges | Small mono-font pills showing AI backend status (`✓ Ollama (mistral)` / `✗ DeepSeek` / `Keyword mode`) and tool availability (`✓ ffmpeg`, `✓ pandoc`). Green = available, red = missing |
| **FR / EN** button | Toggles the UI language; persists in `localStorage` |
| **⚙ Settings** button | Opens the Settings modal |
| **⏻ Sign out** button | Visible only in `multi_user` mode; clears JWT tokens and shows the login modal |

---

## 2. Left sidebar

Width 320 px by default, collapsible, vertically scrollable. Divided into three stacked sections:

### 2.1 Tab row + tab panels

Six tabs across the top of the sidebar:

#### 🔍 Search tab (default)

The primary entry point for academic discovery.

- **Natural-language query textarea** — describe what you need in plain language (EN or FR). Auto-detected as French if 2+ French stopwords, academic French vocabulary, or >1.5 % accented characters are present.
- **Source checkboxes** — pill-style toggles grouped into three sections:
  - *Core open-access*: arXiv · OpenAlex · DOAJ · Gutenberg · Archive
  - *Francophone*: HAL · Persée · OpenEdition · Érudit
  - *Video*: YouTube (in its own fieldset)
  - *Global North* (hidden unless `market_segment=global-north`): Semantic Scholar · PubMed · CrossRef · CORE · BASE
- **Custom journal / source** — free-text input with a `<datalist>` of suggestions (AJOL, PLOS ONE, SSRN, …); appended as a hint to the AI router
- **Include Google Scholar** checkbox — opt-in; added to the AI routing prompt
- **Search button** — triggers the AI-routed `POST /api/nl_search`; shows a spinner while pending
- **Status message** — inline feedback (error or info) below the button

#### 🔗 URL tab

Direct download from a known open-access URL.

- **URL input** — paste any `https://` URL; the backend validates against the open-access domain whitelist
- **Disclaimer checkbox** — shown only in `global-north` mode; must be checked before downloading
- **▶ Play video** button — shown when the URL matches a video platform; opens the YouTube viewer inline
- **Download button** — calls `POST /api/download`; shows a spinner while enqueuing
- **Progress bar** — appears after enqueue; shows percentage, speed (MB/s), and ETA via Server-Sent Events from `/api/progress/{job_id}`
- **Status message** — success or error feedback

#### ⚙ Convert tab

Format conversion for files already in the downloads folder.

- **File selector** — dropdown populated from `/api/status`; lists all files in the downloads directory
- **Convert to** selector — three options: `MP3 (from video)` · `PDF (from docx/html/md)` · `DOCX (from pdf/html)`
- **Convert button** — calls `POST /api/convert`; shows a spinner
- **Status message** — conversion result or error

#### 📋 History tab

Browsable log of all past downloads stored in SQLite.

- **↺ Refresh** button — re-fetches `GET /api/history`
- **History list** — each entry shows:
  - Title (truncated with ellipsis)
  - Source badge + size + year
  - Tags (teal, monospace)
  - Action buttons: **Cite** (opens citation export) · **Add to collection** · **Delete**
  - Clicking the card opens the file in the viewer panel

#### 🗂 Collections tab

Named reading lists. Supports institutional sharing in `multi_user` mode.

- **+ New Collection** button — opens the New Collection modal
- **↺ Refresh** button — re-fetches `GET /api/collections`
- **Collections list** — each item shows name, description, and action buttons: **View** · **Share with institution** · **Delete**

#### 📊 Admin tab

Visible only to users with `admin` role. Shows impact analytics:

- Total downloads, total users, active users this week
- Top 5 search queries (with counts)
- Top sources by downloads
- **Downloads-by-day bar chart** rendered on a `<canvas>` element (using native Canvas API, no library)

---

### 2.2 Active downloads queue

A collapsible section below the tabs (hidden when empty).

- **Section title** "Active Downloads" with a **✕ Clear done** button
- **Queue items** — each shows URL (truncated), a status badge (`queued` / `running` / `done` / `error` / `cancelled`), and a cancel button for running jobs

### 2.3 Downloads file list

Always-visible section at the bottom of the sidebar, scrollable.

- **↺ refresh** button — re-fetches `/api/status`
- **File list** — each file shows:
  - Format icon (📄 PDF · 🎬 MP4 · 🎵 MP3 · 📝 DOCX · 🌐 HTML · 📃 TXT · 📖 EPUB · …)
  - Filename + size
  - Action buttons: **👁 View/Play** (opens in viewer) · **💾 Save** (browser download) · **🗑 Delete** (calls `DELETE /api/file/{filename}`)
  - Right-clicking a file entry opens the **AI Demo context menu**

---

## 3. Splitter bars

Two narrow drag handles (5 px wide) sit between sidebar↔main and main↔viewer. Dragging them resizes the adjacent panels. Minimum widths are enforced (120 px for sidebar, 160 px for viewer). The handles turn accent-orange while being dragged.

---

## 4. Main panel (center)

Fills the remaining horizontal space.

### 4.1 Results bar

A thin bar at the top of the main panel:

- **"Results"** label
- **Count badge** (accent-colored pill) — e.g. `14` — hidden until a search runs
- **Filter pills** — one pill per source that returned results (e.g. `arxiv` · `hal` · `openalex`); clicking a pill filters the visible cards; `all` pill shows everything

### 4.2 Results grid

Scrollable, flex-column list of result cards. Each card shows:

| Field | Detail |
|---|---|
| Source badge | Monospace uppercase, e.g. `ARXIV` |
| Title | Linked to the source URL; teal on hover |
| Authors | Italic, muted |
| Year · Journal | Small muted text |
| Abstract snippet | Up to 3 lines, clamped with ellipsis |
| Action buttons | **Download** (accent filled) · **Cite** · **Open** |

- **Download** — opens the Quick Download modal pre-filled with the PDF URL
- **Cite** — calls `GET /api/cite/{id}?format=bibtex|ris|apa`; copies to clipboard or triggers a download
- **Open** — follows the URL; opens in the in-app Link Viewer if the domain is a known publisher portal (DOI, JSTOR, Springer, Wiley, Elsevier, Nature, etc.), otherwise opens in a new tab

**Empty state**: when no search has run yet, a centred placeholder with a book icon and instructional text is shown.

**Loading skeleton**: while a search is in flight, shimmering placeholder bars animate across the grid.

---

## 5. Right viewer panel

Width 520 px. Displays a locally downloaded file inline. Supports PDF, video, audio, text, and HTML.

### 5.1 Viewer toolbar

- **Filename** (truncated) — monospace, muted
- **↗** external link button (opens the file in a new browser tab) — hidden when no file is open
- **✕ Close** button

### 5.2 Viewer body

Renders based on file extension:

| Extension(s) | Renderer |
|---|---|
| `pdf`, `html`, `htm` | `<iframe>` |
| `mp4`, `webm`, `mkv`, `avi`, `mov` | `<video controls>` |
| `mp3`, `ogg`, `wav`, `flac` | `<audio controls>` |
| `txt`, `md`, `srt` | `<div>` with scrollable pre-formatted text |

Placeholder shown when no file is open. Auto-opening (launching the viewer immediately after a download completes) is configurable in Settings.

---

## 6. Modals

All modals render over a semi-transparent backdrop. Clicking the backdrop or pressing **Escape** closes most of them.

### 6.1 Quick Download modal

Triggered by the **Download** button on a result card.

- Pre-filled URL field
- Progress bar (same SSE mechanism as the URL tab)
- **Cancel** / **Download** buttons
- Status message

### 6.2 New Collection modal

- **Name** field (required)
- **Description** field (optional)
- **Share with institution** checkbox (multi-user mode only)
- **Cancel** / **Create** buttons

### 6.3 Add to Collection modal

- **Choose collection** dropdown — populated from the user's existing collections
- **Cancel** / **Add** buttons

### 6.4 Settings modal

- **Download directory** — text field; saved debounced to `POST /api/settings`
- **Max concurrent downloads** — number input (1–10)
- **Language** — EN / FR toggle buttons
- **Auto-open viewer** — toggle switch
- **Dark mode** — toggle switch; sets `data-theme="dark"` on `<html>`
- **Market segment** — dropdown (`global-south` / `global-north`); requires server restart

### 6.5 Login modal (multi-user mode only)

Shown automatically on startup when no token is stored and `app_mode=multi_user`.

- Blurred backdrop (highest z-index: 200)
- **Email** and **Password** fields
- **Sign in** button — calls `POST /api/auth/login`; stores `access_token` and `refresh_token` in `localStorage`
- Inline error message for invalid credentials or network errors

---

## 7. In-app Link Viewer overlay

A full-screen overlay (z-index 150) that opens when a search result link points to a known publisher domain (DOI, JSTOR, Springer, Wiley, Elsevier, Nature, Cambridge, Oxford, ResearchGate, etc.) or to an HTML page.

### Toolbar

- **← Back** / **→ Forward** / **⟳ Reload** navigation buttons
- **Title** label (truncated)
- **URL bar** — editable; press Enter to navigate; updates automatically when the iframe navigates (same-origin only)
- **✕ Close** button (also triggered by Escape)

### Frame

A sandboxed `<iframe>` fills the rest of the screen. The sandbox grants `allow-scripts allow-same-origin allow-forms allow-popups`.

---

## 8. Interactive Demo (AI sidebar)

The demo system adds AI-powered analysis to any file or text in the interface, accessible via a right-click context menu.

### 8.1 Triggers

- **Right-click a file entry** in the downloads list → context menu appears
- **Select text** anywhere in the page (≥ 20 characters) and release the mouse → context menu appears at the selection's bottom-right corner

### 8.2 Context menu

A dark-themed floating menu with five actions:

| Action | Icon | Description |
|---|---|---|
| Explain | 💡 | Plain-language explanation of the content |
| Summary | 📄 | Condensed summary |
| Chat | 🤖 | Multi-turn Q&A session about the content |
| Presentation | 📊 | Slide deck (JSON array rendered as cards) |
| Flowchart | 🔀 | Mermaid diagram rendered interactively |

Clicking an action closes the menu and opens the Demo Sidebar.

### 8.3 Demo sidebar

A 420 px panel that slides in from the right edge of the screen (over all other content, z-index 1000).

- **Sticky header** — action title + **✕ Close** button
- **Loading spinner** — shown while the AI call is in progress
- **Result area** — rendered differently per action:
  - *Explain / Summary* — formatted text with `**bold**` and `*italic*` markdown
  - *Presentation* — stacked slide cards (title + bullet list per slide)
  - *Flowchart* — Mermaid.js diagram (loaded lazily from CDN); falls back to raw text if Mermaid is unavailable
  - *Chat* — scrollable message thread with user messages in accent colour and AI responses in a light background; a textarea + **Send** button at the bottom; Enter sends (Shift+Enter = newline)

The sidebar remains open until the user closes it with **✕** or presses **Escape**.

### 8.4 File extraction

When the context is a file (not a text selection), the demo system first calls `POST /api/extract` to extract up to 8 000 characters of text from the file. Supported file types for extraction: `.pdf`, `.docx`, `.txt`, `.md`, `.html`. An error message is shown in the sidebar if extraction fails.

---

## 9. Theme and typography

| CSS variable | Default value | Purpose |
|---|---|---|
| `--accent` | `#c8430b` | Primary interactive colour (buttons, links, active tabs, progress fills) |
| `--teal` | `#1a6b6b` | Secondary colour (checked source pills, active filter pills) |
| `--gold` | `#b89435` | Decorative accents |
| `--paper` | `#f5f2eb` | Page background (light mode) |
| `--panel` | `#1a1814` | Header and dark surfaces |
| `--ink` | `#0f0e0a` | Body text |
| `--muted` | `#7a7060` | Secondary text, labels |

Fonts:
- **Syne** (sans-serif, 400–800) — headings, tabs, card titles, labels
- **IBM Plex Mono** (monospace, 400–500) — badges, meta, file names, code
- **Lora** (serif, regular + italic) — body text, inputs

Dark mode is toggled via `data-theme="dark"` on `<html>`. All colour variables are redefined for dark mode.

Institutional branding can override `--accent` and the logo image via the `institution_branding` field returned by `GET /api/status`.

---

## 10. Bilingual support

The UI ships with full EN / FR translations for all user-facing strings. The active language is stored in `localStorage('lang')` and applied on every page render via `applyTranslations()`. Switching language is instant (no reload). The language toggle button in the header always shows the *other* language as the call to action (i.e. when French is active it shows **EN**, and vice-versa).

---

## 11. Progressive Web App

The app registers a service worker (`sw.js`, cache name `scholara-v4`) that caches static assets for offline use. It ships a `manifest.json` with a 192 px and 512 px icon, enabling "Add to home screen" on Android and iOS. The theme color is `#c8430b`.

---

## 12. Auto-refresh

Two background polling loops run while the app is open:

- **`loadStatus()` every 15 s** — refreshes tool badges, file list, and market-segment UI
- **`renderQueuePanel()` every 2 s** — refreshes the active downloads queue section
