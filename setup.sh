#!/usr/bin/env bash
# Scholara — one-time setup
set -e

echo ""
echo "══════════════════════════════════════════════"
echo "  Scholara Setup"
echo "══════════════════════════════════════════════"

# Python deps
echo "[1/4] Installing Python packages..."
pip install -r requirements.txt --quiet

# ffmpeg check
echo "[2/4] Checking ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
  echo "  ffmpeg not found. Install it:"
  echo "    macOS:   brew install ffmpeg"
  echo "    Ubuntu:  sudo apt install ffmpeg"
  echo "    Windows: https://ffmpeg.org/download.html"
else
  echo "  ✓ ffmpeg found"
fi

# pandoc check
echo "[3/4] Checking pandoc..."
if ! command -v pandoc &> /dev/null; then
  echo "  pandoc not found. Install it:"
  echo "    macOS:   brew install pandoc"
  echo "    Ubuntu:  sudo apt install pandoc"
else
  echo "  ✓ pandoc found"
fi

# Ollama check
echo "[4/4] Checking Ollama (optional but recommended)..."
if ! command -v ollama &> /dev/null; then
  echo "  Ollama not found. For free local AI routing, install it:"
  echo "    curl -fsSL https://ollama.ai/install.sh | sh"
  echo "    ollama pull mistral"
else
  echo "  ✓ Ollama found"
fi

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete!  Run:  python app.py"
echo "══════════════════════════════════════════════"
echo ""
