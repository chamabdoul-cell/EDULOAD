# EduLoad — Educational Resource Downloader & Viewer

A desktop app (local web UI) for finding, downloading, converting, and viewing
free educational resources: videos, papers, books, documents.

## Quick Start

```bash
# 1. Install dependencies
bash setup.sh

# 2. Run the app  (opens browser automatically)
python app.py
```

Then open **http://127.0.0.1:7860** if the browser doesn't open automatically.

---

## Features

### 🔍 Search
- Describe in plain language: *"lecture on Fourier analysis"* or *"Vaswani attention is all you need"*
- Sources: YouTube, arXiv, DOAJ, Project Gutenberg, DuckDuckGo Web
- Filter results by source with one click

### 🔗 Download by URL
- YouTube, Vimeo, Dailymotion and 1000+ sites via yt-dlp
- Choose quality: Best / 1080p / 720p / 480p / 360p / Audio only
- Download subtitles: EN, FR, AR, ES (auto-generated or manual)
- Direct PDF, DOCX, HTML file downloads

### ⚙️ Convert
| From | To | Requires |
|------|-----|----------|
| Video (mp4, webm…) | MP3 | ffmpeg |
| DOCX / HTML / MD | PDF | pandoc |
| PDF | DOCX | pdf2docx |
| HTML | DOCX | pandoc |

### 👁 Built-in Viewer
- **Video**: HTML5 player (mp4, webm, mkv…)
- **Audio**: HTML5 player (mp3, ogg, wav…)
- **PDF**: inline PDF viewer
- **HTML**: sandboxed iframe
- **Text / SRT subtitles**: plain text view

---

## External Tools Required

| Tool | Purpose | Install |
|------|---------|---------|
| **yt-dlp** | Video downloads | `pip install yt-dlp` |
| **ffmpeg** | Video→MP3, merging | [ffmpeg.org](https://ffmpeg.org) |
| **pandoc** | Doc conversions | [pandoc.org](https://pandoc.org) |

Status badges show ✓ / ✗ for each tool in the header.

---

## Downloads Folder
All files saved to `eduload/downloads/`. Manage them in the sidebar.

---

## License & Ethics
EduLoad only searches open-access, public-domain, and free educational sources.
Always respect copyright and terms of service of content providers.
