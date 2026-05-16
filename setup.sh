#!/usr/bin/env bash
# EduLoad — one-time setup
set -e

echo ""
echo "══════════════════════════════════════════════"
echo "  EduLoad Setup"
echo "══════════════════════════════════════════════"

# Python deps
echo "[1/4] Installing Python packages..."
pip install -r requirements.txt --quiet

# yt-dlp
echo "[2/4] Installing yt-dlp..."
pip install yt-dlp --quiet

# ffmpeg check
echo "[3/4] Checking ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
  echo "  ffmpeg not found. Install it:"
  echo "    macOS:   brew install ffmpeg"
  echo "    Ubuntu:  sudo apt install ffmpeg"
  echo "    Windows: https://ffmpeg.org/download.html"
else
  echo "  ✓ ffmpeg found"
fi

# pandoc check
echo "[4/4] Checking pandoc..."
if ! command -v pandoc &> /dev/null; then
  echo "  pandoc not found. Install it:"
  echo "    macOS:   brew install pandoc"
  echo "    Ubuntu:  sudo apt install pandoc"
  echo "    Windows: https://pandoc.org/installing.html"
else
  echo "  ✓ pandoc found"
fi

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete!  Run:  python app.py"
echo "══════════════════════════════════════════════"
echo ""
