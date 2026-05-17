import os
from dotenv import load_dotenv

load_dotenv("config/.env")
load_dotenv()


class AIConfig:
    BACKEND          = os.getenv("AI_BACKEND", "ollama")   # 'ollama' | 'deepseek' | 'fallback'
    OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "mistral")
    OLLAMA_URL       = os.getenv("OLLAMA_URL", "http://localhost:11434")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    CACHE_TTL        = int(os.getenv("AI_CACHE_TTL", "300"))
