"""Runtime configuration."""

from __future__ import annotations

import logging
import os
from functools import lru_cache


@lru_cache
def is_dev_mode() -> bool:
    return os.getenv("DEV_MODE", "true").lower() == "true"


def announce_dev_mode(service_name: str) -> None:
    """Every service must call this on startup. See implementation rule 14."""
    logger = logging.getLogger(service_name)
    if is_dev_mode():
        logger.warning("Running in DEV_MODE — auth disabled")


# URLs of downstream services
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_URL", "http://knowledge:8001")
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8002")
INTEGRATIONS_URL = os.getenv("INTEGRATIONS_URL", "http://integrations:8003")
PROCESS_INTEL_URL = os.getenv("PROCESS_INTEL_URL", "http://process-intel:8004")
LEARNING_URL = os.getenv("LEARNING_URL", "http://learning:8005")
SECURITY_URL = os.getenv("SECURITY_URL", "http://security:8006")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEV_USER_ID = os.getenv("DEV_USER_ID", "dev-user-1")
DEV_USER_EMAIL = os.getenv("DEV_USER_EMAIL", "dev@mycelium.local")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
