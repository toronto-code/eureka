"""correlation_id helpers.

Generation rules (priority order):
  1. Natural ID if one exists (PR number, Slack thread ID).
  2. hash(source + object_id + time_window) + uuid suffix to prevent burst collisions.
  3. API assigns a fallback if the producer omits it.

Use ``derive_correlation_id`` for rules (1) and (2). Rule (3) is implemented in apps/api.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional


def _time_window_bucket(when: datetime, window_seconds: int = 60) -> int:
    """Bucket a timestamp into a fixed-size window. Defaults to 60-second buckets."""
    return int(when.timestamp()) // window_seconds


def derive_correlation_id(
    *,
    source: str,
    object_id: str,
    natural_id: Optional[str] = None,
    when: Optional[datetime] = None,
    window_seconds: int = 60,
) -> str:
    """Derive a correlation_id following the priority rules above.

    If a ``natural_id`` is provided we use it directly (rule 1). Otherwise we hash
    ``source + object_id + time_window_bucket`` and append a uuid4 suffix to prevent
    collisions between concurrent producers in the same window (rule 2).
    """
    if natural_id:
        return f"{source}:{natural_id}"

    when = when or datetime.now(timezone.utc)
    bucket = _time_window_bucket(when, window_seconds)
    digest = hashlib.sha256(
        f"{source}|{object_id}|{bucket}".encode("utf-8")
    ).hexdigest()[:16]
    suffix = uuid.uuid4().hex[:8]
    return f"{source}:{digest}:{suffix}"
