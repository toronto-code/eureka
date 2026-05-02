"""Configuration for the learning service."""

from __future__ import annotations

import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://mycelium:mycelium@postgres:5432/mycelium")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

# Trigger thresholds - update models when either is hit
SIGNAL_BATCH_SIZE = int(os.getenv("LEARNING_BATCH_SIZE", "10"))
SIGNAL_BATCH_INTERVAL_SECONDS = int(os.getenv("LEARNING_BATCH_INTERVAL_SECONDS", "900"))  # 15 min

# Minimum signals before a model is considered "trained"
MIN_SIGNALS_FOR_RECOMMENDATION = int(os.getenv("LEARNING_MIN_SIGNALS", "5"))

# Weight for recent signals (exponential decay)
RECENT_SIGNAL_WEIGHT = float(os.getenv("LEARNING_RECENT_WEIGHT", "2.0"))
RECENT_SIGNAL_WINDOW_HOURS = int(os.getenv("LEARNING_RECENT_WINDOW_HOURS", "24"))

# Backend selection
LEARNING_BACKEND = os.getenv("LEARNING_BACKEND", "local")
OPENCLAW_RL_API_KEY = os.getenv("OPENCLAW_RL_API_KEY", "")
OPENCLAW_RL_API_URL = os.getenv("OPENCLAW_RL_API_URL", "https://api.openclaw.ai/rl")
GENVERSE_API_KEY = os.getenv("GENVERSE_API_KEY", "")
GENVERSE_API_URL = os.getenv("GENVERSE_API_URL", "https://api.genverse.ai")

# Model cache TTL
MODEL_CACHE_TTL_SECONDS = int(os.getenv("LEARNING_MODEL_CACHE_TTL", "3600"))

# Auto-approve threshold: if user approves X% of an action, suggest auto-approve
AUTO_APPROVE_THRESHOLD = float(os.getenv("LEARNING_AUTO_APPROVE_THRESHOLD", "0.9"))
AUTO_BLOCK_THRESHOLD = float(os.getenv("LEARNING_AUTO_BLOCK_THRESHOLD", "0.1"))
MIN_DECISIONS_FOR_SUGGESTION = int(os.getenv("LEARNING_MIN_DECISIONS", "5"))
