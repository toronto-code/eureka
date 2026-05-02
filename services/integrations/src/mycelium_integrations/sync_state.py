"""integration_syncs writes.

This service is the SOLE writer of this table. The API is read-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from mycelium_db import get_session

logger = logging.getLogger(__name__)


async def record_sync(
    connector: str,
    *,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    async with get_session() as session:
        await session.execute(
            text(
                """
                INSERT INTO integration_syncs (connector, last_sync_at, status, error_message)
                VALUES (:c, :l, :s, :e)
                ON CONFLICT (connector) DO UPDATE
                  SET last_sync_at = EXCLUDED.last_sync_at,
                      status = EXCLUDED.status,
                      error_message = EXCLUDED.error_message,
                      updated_at = NOW()
                """
            ),
            {
                "c": connector,
                "l": datetime.now(timezone.utc),
                "s": status,
                "e": error_message,
            },
        )
