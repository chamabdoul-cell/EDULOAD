import os
from dotenv import load_dotenv

load_dotenv("config/.env")
load_dotenv()  # fallback to root .env


class ClaudeConfig:
    API_KEY = os.getenv("ANTHROPIC_API_KEY")
    MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-haiku-20241022")
    HAIKU_MODEL = "claude-3-5-haiku-20241022"
    CACHE_TTL = int(os.getenv("CLAUDE_CACHE_TTL", 300))
    FALLBACK_ENABLED = os.getenv("CLAUDE_FALLBACK_ENABLED", "true").lower() == "true"
    MAX_TOKENS = 1024
    TEMPERATURE = 0.1
