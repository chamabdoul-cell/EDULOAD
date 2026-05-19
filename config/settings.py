import os
from enum import Enum

from dotenv import load_dotenv

load_dotenv("config/.env")
load_dotenv()


class MarketSegment(str, Enum):
    GLOBAL_NORTH = "global-north"
    GLOBAL_SOUTH = "global-south"


class AIConfig:
    BACKEND          = os.getenv("AI_BACKEND", "ollama")   # 'ollama' | 'deepseek' | 'fallback'
    OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "mistral")
    OLLAMA_URL       = os.getenv("OLLAMA_URL", "http://localhost:11434")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    CACHE_TTL        = int(os.getenv("AI_CACHE_TTL", "300"))
    CORE_API_KEY     = os.getenv("CORE_API_KEY", "")

    # Deployment mode
    APP_MODE         = os.getenv("APP_MODE", "single_user")  # single_user | multi_user

    # JWT auth (only used in multi_user mode)
    SECRET_KEY                  = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    @classmethod
    def is_multi_user(cls) -> bool:
        return cls.APP_MODE == "multi_user"

    MARKET_SEGMENT: MarketSegment = MarketSegment(
        os.getenv("MARKET_SEGMENT", "global-south")
    )

    @classmethod
    def is_north(cls) -> bool:
        return cls.MARKET_SEGMENT == MarketSegment.GLOBAL_NORTH

    @classmethod
    def is_south(cls) -> bool:
        return cls.MARKET_SEGMENT == MarketSegment.GLOBAL_SOUTH


# Alias used by downloader and other modules
ClaudeConfig = AIConfig
