"""FastAPI application entrypoint for Mycelium.

Run with:
    uvicorn app.main:app --reload --port 8000

Boot sequence:
  1. Build SQLAlchemy engine from POSTGRES_DSN.
  2. Create all tables (idempotent — fine for the MVP).
  3. Seed demo tasks if `ENABLE_DEMO_SEED=true`.
  4. Mount routers under `/agents`, `/tasks`, `/ingestion`, plus `/health`.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.routes import agents, ingestion, ol, projects, system, tasks, webhooks

# Ensure all model modules are imported so metadata is populated.
from app import models  # noqa: F401

logger = logging.getLogger(__name__)


def _init_db_safely() -> None:
    settings = get_settings()
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        logger.warning("Database not reachable on startup: %s", exc)
        return
    if settings.enable_demo_seed:
        try:
            with SessionLocal() as session:
                from app.seed import seed_database

                seed_database(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Demo seed failed (non-fatal): %s", exc)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    _init_db_safely()
    # Start background Jira watcher if enabled (no-op otherwise).
    try:
        from app.services.watcher import start_watcher_task, stop_watcher_task

        start_watcher_task()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Watcher failed to start (non-fatal): %s", exc)
        stop_watcher_task = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if stop_watcher_task is not None:
            try:
                stop_watcher_task()
            except Exception:  # noqa: BLE001
                pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(system.router)
    app.include_router(agents.router)
    app.include_router(tasks.router)
    app.include_router(ingestion.router)
    # New OL / multi-repo surface.
    app.include_router(projects.router)
    app.include_router(ol.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
