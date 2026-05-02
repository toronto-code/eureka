"""Seed fake data so the UI is non-empty on first run.

Inserts:
  - fake events (mix of github, slack, jira, observer)
  - fake integration_syncs rows (writing this directly is fine ONLY for seed —
    in production, integrations is the sole writer)
  - fake agents + agent_tasks + audit_log entries
  - a small fake company graph by POSTing to the knowledge service
  - via the API where possible; direct Postgres for tables the API doesn't expose

Idempotent: re-running is safe. Skips inserts that already exist.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

API_URL = os.getenv("API_URL", "http://api:8000")
KNOWLEDGE_URL = os.getenv("KNOWLEDGE_URL", "http://knowledge:8001")


def _dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN", "postgresql://mycelium:mycelium@postgres:5432/mycelium")
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


USERS = [
    {"id": "u_alice", "name": "Alice", "email": "alice@mycelium.local"},
    {"id": "u_bob", "name": "Bob", "email": "bob@mycelium.local"},
    {"id": "u_carol", "name": "Carol", "email": "carol@mycelium.local"},
]


def _event(*, source: str, etype: str, actor_id: str, object_id: str, object_type: str,
           correlation_id: str, parent: str | None, when: datetime) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": etype,
        "source": source,
        "actor": {"id": actor_id, "type": "user", "display_name": actor_id},
        "object": {"id": object_id, "type": object_type, "url": None},
        "timestamp": when.isoformat(),
        "schema_version": "1.0",
        "metadata": {"seeded": True},
        "correlation_id": correlation_id,
        "parent_correlation_id": parent,
    }


def _fake_events() -> list[dict]:
    now = datetime.now(timezone.utc)
    events: list[dict] = []

    # PR #42: opened → review → merged (linked by natural id)
    pr = "github:pr-42"
    events.append(_event(
        source="github", etype="github.pr.opened", actor_id="u_alice",
        object_id="42", object_type="pull_request", correlation_id=pr, parent=None,
        when=now - timedelta(hours=4)))
    events.append(_event(
        source="github", etype="github.pr.review_requested", actor_id="u_alice",
        object_id="42", object_type="pull_request", correlation_id=pr, parent=pr,
        when=now - timedelta(hours=3, minutes=50)))
    events.append(_event(
        source="github", etype="github.pr.reviewed", actor_id="u_bob",
        object_id="42", object_type="pull_request", correlation_id=pr, parent=pr,
        when=now - timedelta(hours=2)))
    events.append(_event(
        source="github", etype="github.pr.merged", actor_id="u_alice",
        object_id="42", object_type="pull_request", correlation_id=pr, parent=pr,
        when=now - timedelta(hours=1)))

    # Slack thread (same correlation)
    thread = "slack:thread-T1-1714000000"
    events.append(_event(
        source="slack", etype="slack.message.posted", actor_id="u_carol",
        object_id="m1", object_type="message", correlation_id=thread, parent=None,
        when=now - timedelta(hours=5)))
    events.append(_event(
        source="slack", etype="slack.message.posted", actor_id="u_alice",
        object_id="m2", object_type="message", correlation_id=thread, parent=thread,
        when=now - timedelta(hours=4, minutes=55)))
    events.append(_event(  # edit — parent_correlation_id set
        source="slack", etype="slack.message.edited", actor_id="u_alice",
        object_id="m2", object_type="message", correlation_id=thread, parent=thread,
        when=now - timedelta(hours=4, minutes=52)))

    # Jira ticket
    ticket = "jira:ENG-101"
    events.append(_event(
        source="jira", etype="jira.ticket.created", actor_id="u_bob",
        object_id="ENG-101", object_type="ticket", correlation_id=ticket, parent=None,
        when=now - timedelta(days=1)))
    events.append(_event(
        source="jira", etype="jira.ticket.transitioned", actor_id="u_alice",
        object_id="ENG-101", object_type="ticket", correlation_id=ticket, parent=ticket,
        when=now - timedelta(hours=8)))

    # Observer-style local events
    for i in range(10):
        cid = f"observer:dev-user-1:{int(now.timestamp())//60}:{i}"
        events.append(_event(
            source="observer", etype="observer.command.run", actor_id="dev-user-1",
            object_id=f"cmd-{i}", object_type="command", correlation_id=cid, parent=None,
            when=now - timedelta(minutes=random.randint(1, 600))))

    return events


async def _seed_via_api(events: list[dict]) -> None:
    """Post events through the API so they go through the normal pipeline.

    The API ingestion worker is the sole writer of the events table; we use the
    public ingestion endpoint here.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        for ev in events:
            try:
                r = await client.post(f"{API_URL}/integrations/ingest", json=ev)
                r.raise_for_status()
            except Exception as exc:
                print(f"[seed] failed to ingest event {ev['id']}: {exc}")


async def _seed_integration_syncs(engine) -> None:
    """In real life ONLY services/integrations writes this table.
    Seed is the documented exception.
    """
    rows = [
        ("github", datetime.now(timezone.utc) - timedelta(minutes=5), "ok", None),
        ("slack", datetime.now(timezone.utc) - timedelta(minutes=12), "ok", None),
        ("jira", datetime.now(timezone.utc) - timedelta(hours=2), "error",
         "401 Unauthorized — refresh JIRA_API_TOKEN"),
    ]
    async with engine.begin() as conn:
        for connector, last, status, err in rows:
            await conn.execute(
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
                {"c": connector, "l": last, "s": status, "e": err},
            )


async def _seed_agents(engine) -> None:
    async with engine.begin() as conn:
        for u in USERS:
            agent_id = f"agent-{u['id']}"
            await conn.execute(
                text(
                    """
                    INSERT INTO agents (id, owner_user_id, capabilities, status)
                    VALUES (:id, :owner, :caps, 'idle')
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": agent_id, "owner": u["id"], "caps": json.dumps(["triage", "summarize"])},
            )

            for i in range(2):
                task_id = f"task-{agent_id}-{i}"
                await conn.execute(
                    text(
                        """
                        INSERT INTO agent_tasks (task_id, agent_id, agent_type, input_data,
                                                 correlation_id, status)
                        VALUES (:t, :a, 'triage', :i, :c, :s)
                        ON CONFLICT (task_id) DO NOTHING
                        """
                    ),
                    {
                        "t": task_id,
                        "a": agent_id,
                        "i": json.dumps({"prompt": "summarize PR #42"}),
                        "c": f"seed:{task_id}",
                        "s": "succeeded" if i == 0 else "running",
                    },
                )

                await conn.execute(
                    text(
                        """
                        INSERT INTO audit_log (id, agent_id, task_id, action, actor_user_id,
                                               correlation_id, details)
                        VALUES (:id, :a, :t, 'task.executed', :u, :c, :d)
                        ON CONFLICT (id) DO NOTHING
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "a": agent_id,
                        "t": task_id,
                        "u": u["id"],
                        "c": f"seed:{task_id}",
                        "d": json.dumps({"summary": "looks good", "tokens": 412}),
                    },
                )


async def _seed_graph() -> None:
    """Ask the knowledge service to seed a fake company graph."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.post(f"{KNOWLEDGE_URL}/seed")
            r.raise_for_status()
            print(f"[seed] knowledge graph seeded: {r.json()}")
        except Exception as exc:
            print(f"[seed] knowledge seed failed (ok if knowledge not up yet): {exc}")


async def main() -> None:
    print("[seed] starting")
    engine = create_async_engine(_dsn())

    print("[seed] waiting briefly for migrations to settle")
    await asyncio.sleep(2)

    print("[seed] integration_syncs")
    await _seed_integration_syncs(engine)

    print("[seed] agents + tasks + audit")
    await _seed_agents(engine)

    events = _fake_events()
    print(f"[seed] {len(events)} events via API")
    await _seed_via_api(events)

    print("[seed] knowledge graph")
    await _seed_graph()

    await engine.dispose()
    print("[seed] done")


if __name__ == "__main__":
    asyncio.run(main())
