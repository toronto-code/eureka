"""Seed fixtures used when real Jira/GitHub credentials are missing.

These power the local demo so the orchestrator has something to chew on.
"""
from __future__ import annotations

from typing import Any

DEMO_TASK_TITLE = "Create onboarding guide for payments-service"
DEMO_PROJECT_KEY = "PAY"
DEMO_BOT_USER = "mycelium-bot"
DEMO_BOT_EMAIL = "mycelium-bot@mycelium.local"


def fake_jira_tasks() -> list[dict[str, Any]]:
    return [
        {
            "id": "PAY-101",
            "key": "PAY-101",
            "title": DEMO_TASK_TITLE,
            "description": (
                "We need a single onboarding doc for new engineers joining the payments-service "
                "team. Cover architecture, code map, ownership, runbooks, and FAQs. Mirror the "
                "structure of existing onboarding docs."
            ),
            "status": "To Do",
            "assignee": "alex.kim",
            "reporter": "priya.s",
            "labels": ["onboarding", "documentation", "payments"],
            "comments": [
                {
                    "author": "priya.s",
                    "body": "Let's keep it under 2 pages. Link to the runbooks instead of copying.",
                },
                {
                    "author": "alex.kim",
                    "body": "Also include who to ping on-call.",
                },
            ],
            "acceptance_criteria": [
                "Doc lives in docs/onboarding/payments-service.md",
                "Architecture diagram included",
                "Code map references real files",
                "Runbook links present",
                "Owners + on-call rota listed",
            ],
            "dependencies": [],
            "priority": "Medium",
            "project_key": DEMO_PROJECT_KEY,
        },
        {
            "id": "PAY-102",
            "key": "PAY-102",
            "title": "Add idempotency keys to refunds endpoint",
            "description": "Customers occasionally submit duplicate refund requests during retries.",
            "status": "In Progress",
            "assignee": "sara.j",
            "reporter": "alex.kim",
            "labels": ["payments", "api", "reliability"],
            "comments": [],
            "acceptance_criteria": [
                "POST /refunds accepts an Idempotency-Key header",
                "Duplicate keys return the previous response",
            ],
            "dependencies": ["PAY-101"],
            "priority": "High",
            "project_key": DEMO_PROJECT_KEY,
        },
        # Bot-assigned task — demonstrates the autonomous end-to-end flow.
        {
            "id": "PAY-103",
            "key": "PAY-103",
            "title": "Draft payments-service onboarding doc (auto-run)",
            "description": (
                "Same deliverable as PAY-101 but assigned to the Mycelium bot so "
                "it autonomously creates the branch, commits the new markdown file, "
                "opens a PR, and posts a status comment back here. Humans review the PR."
            ),
            "status": "To Do",
            "assignee": DEMO_BOT_USER,
            "assignee_email": DEMO_BOT_EMAIL,
            "reporter": "priya.s",
            "labels": ["onboarding", "documentation", "payments", "auto"],
            "comments": [
                {
                    "author": "priya.s",
                    "body": "Assigning to the Mycelium bot — it should open a PR within a few minutes.",
                },
            ],
            "acceptance_criteria": [
                "PR opened with docs/onboarding/payments-service.md",
                "Jira comment posted with PR link",
            ],
            "dependencies": [],
            "priority": "Medium",
            "project_key": DEMO_PROJECT_KEY,
        },
    ]


def fake_repo() -> dict[str, Any]:
    return {
        "owner": "mycelium-demo",
        "name": "payments-service",
        "description": "Demo payments service used by the Mycelium scaffold.",
        "primary_language": "Python",
        "files": [
            {
                "path": "services/payments-service/app/main.py",
                "language": "python",
                "summary": "FastAPI entrypoint mounting payments router.",
                "content": (
                    "from fastapi import FastAPI\n"
                    "from .api import payments_router\n\n"
                    "app = FastAPI(title='payments-service')\n"
                    "app.include_router(payments_router, prefix='/payments')\n"
                ),
                "metadata": {"service": "payments-service"},
            },
            {
                "path": "services/payments-service/app/api.py",
                "language": "python",
                "summary": "Payment intents + refunds endpoints.",
                "content": (
                    "from fastapi import APIRouter\n\n"
                    "payments_router = APIRouter()\n\n"
                    "@payments_router.post('/intents')\n"
                    "def create_intent(payload: dict):\n"
                    "    return {'id': 'pi_demo', **payload}\n\n"
                    "@payments_router.post('/refunds')\n"
                    "def create_refund(payload: dict):\n"
                    "    return {'id': 're_demo', **payload}\n"
                ),
                "metadata": {"service": "payments-service"},
            },
            {
                "path": "services/payments-service/README.md",
                "language": "markdown",
                "summary": "Service README.",
                "content": (
                    "# payments-service\n\n"
                    "Handles payment intents, refunds, and provider webhooks.\n\n"
                    "## Layout\n- app/main.py — FastAPI entrypoint\n- app/api.py — routes\n"
                ),
                "metadata": {"service": "payments-service"},
            },
        ],
    }


def fake_docs() -> list[dict[str, Any]]:
    return [
        {
            "id": "doc-onboard-template",
            "title": "Onboarding Template",
            "source": "internal-wiki",
            "content": (
                "# {service-name} Onboarding\n\n"
                "## What it does\n## Architecture\n## Code map\n## Ownership\n## Runbooks\n## FAQ\n"
            ),
            "project_key": DEMO_PROJECT_KEY,
        },
        {
            "id": "doc-payments-readme",
            "title": "payments-service README",
            "source": "github",
            "content": (
                "payments-service handles payment intents, refunds, and webhook delivery. "
                "Owned by the Payments team."
            ),
            "project_key": DEMO_PROJECT_KEY,
        },
    ]


def fake_transcripts() -> list[dict[str, Any]]:
    return [
        {
            "id": "tr-demo-1",
            "title": "Payments-service architecture sync",
            "participants": ["alex.kim", "priya.s", "sara.j"],
            "occurred_at": "2026-04-29T14:00:00Z",
            "content": (
                "alex.kim: We decided to keep payment intents idempotent at the adapter layer.\n"
                "priya.s: Agreed. Onboarding doc should mention services/payments-service/app/api.py.\n"
                "sara.j: Mention the on-call rota and link to runbooks.\n"
                "alex.kim: Decided to ship the onboarding guide before next sprint.\n"
            ),
        }
    ]


def fake_previous_runs() -> list[dict[str, Any]]:
    return [
        {
            "id": "run-prior-1",
            "agent_type": "docs_analyst",
            "summary": "Located prior onboarding template that we should mirror.",
            "output": {"useful_context_for_task": "Use the existing onboarding template structure."},
            "risk_level": "READ_ONLY",
            "occurred_at": "2026-04-30T10:00:00Z",
        }
    ]
