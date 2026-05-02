"""HTTP API routers for the learning service."""

from mycelium_learning.api.preferences import router as preferences_router
from mycelium_learning.api.recommendations import router as recommendations_router
from mycelium_learning.api.signals import router as signals_router

__all__ = [
    "preferences_router",
    "recommendations_router",
    "signals_router",
]
