import logging
from pathlib import Path

Path("monitoring/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("monitoring/logs/claude_routing.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("claude_router")


def log_routing(user_input: str, routing: dict, model: str, cached: bool = False):
    logger.info(
        f"query={user_input!r} sources={routing.get('sources')} "
        f"confidence={routing.get('confidence')} model={model} cached={cached}"
    )


def log_error(user_input: str, error: Exception):
    logger.error(f"routing_error query={user_input!r} error={error}")


def log_fallback(user_input: str):
    logger.warning(f"fallback_used query={user_input!r}")
