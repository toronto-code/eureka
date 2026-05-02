# Mycelium

Mycelium is an agentic company intelligence system. It watches a Jira board,
pulls context from company sources (repos, docs, working-session transcripts),
and uses GPT-4o-powered agents to help complete Jira tasks safely.

A wide central **OrchestratorAgent** (GPT-4o) decides which specialised
**worker agents** (also GPT-4o today; cheaper models are easy to swap in
later) to spawn for each task. The orchestrator merges their findings,
classifies risk, and recommends the next safe action — gating any real write
behind explicit human approval.

> Status: foundation MVP. Local demo runs end to end without any real Jira /
> GitHub / OpenAI credentials by falling back to seeded fixtures and
> deterministic mock LLM responses.

## Quick start

```bash
cp .env.example .env          # fill in OPENAI_API_KEY for real GPT-4o (optional)
docker compose up --build
```

Then open:

- Frontend (Next.js): http://localhost:3000
- API (FastAPI):      http://localhost:8000 (Swagger at `/docs`)
- Postgres+pgvector:  localhost:5432

The stack auto-creates tables on first boot and seeds a demo Jira-style task
("Create onboarding guide for payments-service") plus fake repo files,
transcripts, docs, and a previous agent run.

Click **Run demo orchestration** on the dashboard or the Orchestration page to
watch the orchestrator spawn the worker agents and produce a structured task
brief, implementation plan, risk classification, and approval flow.

## Autonomous execution (assignment-as-approval)

Once wired up, Mycelium can autonomously finish a Jira task end-to-end:
create a branch, commit file edits, open a pull request, and post a Jira
comment with the PR link. The **human approval step is assigning the task
to the Mycelium bot user in Jira** — after that the agent takes over.

Set up the bot account:

1. Create a dedicated GitHub account for the bot (or use a service account)
   and add it as a collaborator on the target repo with push access. Generate
   a Personal Access Token with the `repo` scope (or `public_repo` if the
   repo is public).
2. Create a dedicated Jira user for the bot (or reuse one).
3. Fill in `.env`:

   ```env
   OPENAI_API_KEY=sk-...
   JIRA_BASE_URL=https://acme.atlassian.net
   JIRA_EMAIL=bot@acme.com
   JIRA_API_TOKEN=...
   JIRA_PROJECT_KEY=PAY

   GITHUB_TOKEN=ghp_...            # bot account's token
   GITHUB_OWNER=acme
   GITHUB_REPO=payments-service

   MYCELIUM_BOT_JIRA_USER=mycelium-bot@acme.com
   MYCELIUM_AUTO_EXECUTE=true
   MYCELIUM_ALLOW_REAL_GITHUB=true   # flip to true when ready for live writes

   JIRA_WATCHER_ENABLED=true
   JIRA_WATCHER_INTERVAL_SECONDS=60
   ```

4. Assign a Jira ticket to the bot user. Within one poll interval the bot
   will:
   1. Pull the ticket + repo context + uploaded docs into `project_data`.
   2. Run the orchestrator + 8 worker agents to build a plan.
   3. Create a `mycelium/<JIRA-KEY>-<slug>` branch.
   4. Commit each file in the plan (refusing anything on the hard-block
      list: `.env`, `secrets/`, `.github/workflows/`, etc).
   5. Open a PR against the default branch with a description linking back
      to Jira.
   6. Post a comment on the Jira ticket with the PR URL.
   7. Transition the ticket to *In Review* (or *In Progress*).

Safety rails enforced in code (not config, not overridable by the model):

- Never merges PRs.
- Never deletes files or branches.
- Never writes to the default branch directly.
- Refuses to write to paths on the hard-block list.
- `MYCELIUM_ALLOW_REAL_GITHUB=false` keeps every write in dry-run mode even
  with real credentials — useful for staging.
- Leaving `MYCELIUM_BOT_JIRA_USER` empty keeps the classic draft-only flow.

You can also trigger a one-shot poll without enabling the watcher via the
**Poll Jira now** button on the Dashboard or `POST /agents/watch`.

### Run locally without Docker

```bash
# Postgres+pgvector (in a separate terminal)
docker run --rm -p 5432:5432 \
  -e POSTGRES_DB=mycelium -e POSTGRES_USER=mycelium -e POSTGRES_PASSWORD=mycelium \
  pgvector/pgvector:pg16

# API
cd apps/api
pip install -r requirements.txt
POSTGRES_DSN=postgresql+psycopg://mycelium:mycelium@localhost:5432/mycelium \
  uvicorn app.main:app --reload --port 8000

# Web
cd apps/web
npm install
BACKEND_URL=http://localhost:8000 npm run dev
```

## Architecture

### Backend (`apps/api/app/`)

```
apps/api/app/
├── main.py                  FastAPI entry, lifespan, CORS, router mounting
├── config.py                pydantic-settings; reads OPENAI_API_KEY etc.
├── db/                      SQLAlchemy 2.0 engine + sessions + pgvector init
├── models/                  ORM models: tasks, source_documents,
│                            document_chunks, entities, relationships,
│                            agent_runs, agent_actions, approvals, audit_logs,
│                            integration_credentials
├── schemas/
│   ├── project_data.py      ProjectData + JiraTaskData + GitHubRepoData +
│   │                        CodeFileData + DocData + TranscriptData +
│   │                        PreviousAgentRunData + ApprovalData +
│   │                        AuditLogData + SystemConfigData
│   └── api.py               DTOs returned by routes
├── prompts/                 System prompts + JSON schema hints per agent
├── agents/
│   ├── base.py              BaseAgent, AgentInput/Output, AgentType,
│   │                        RiskLevel, AgentRunStatus, JSON helpers
│   ├── llm_client.py        OpenAIClient (GPT-4o default, retry-light,
│   │                        fallback to deterministic mock when no key)
│   ├── registry.py          AgentRegistry: register / instantiate / run
│   ├── orchestrator.py      OrchestratorAgent: task understanding,
│   │                        worker selection, focused subset construction,
│   │                        merge, risk, recommendation, audit
│   └── workers/             8 worker agents — each is a class with its own
│                            prompt + schema:
│                              jira_analyst, codebase_analyst,
│                              transcript_analyst, docs_analyst, planner,
│                              risk_safety, executor, reviewer
├── memory/
│   └── base.py              MemoryBackend ABC + PostgresMemoryBackend
│                            (pgvector when available, lexical fallback).
│                            Designed to be swapped for Graphiti / Neo4j /
│                            FalkorDB / Qdrant / Pinecone / Weaviate later.
├── ingestion/               IngestionService: parse upload → chunk → memory →
│                            light entity linking (Jira keys, services, mentions).
│                            GitHub + Slack ingestion are explicit placeholders.
├── integrations/
│   ├── jira.py              JiraClient — real REST when JIRA_* set, seeded
│   │                        fixtures otherwise. Can post comments.
│   └── github.py            GitHubClient — real REST when GITHUB_* set,
│                            seeded fixtures otherwise.
├── routes/
│   ├── system.py            /health, /settings/*
│   ├── agents.py            /agents/orchestrate, /run-worker, /types,
│   │                        /demo, /runs, /runs/{id}, /runs/{id}/graph
│   ├── tasks.py             /tasks, /tasks/{id}, /tasks/{id}/run-agent,
│   │                        /tasks/{id}/approve, /tasks/{id}/reject
│   └── ingestion.py         /ingestion/upload, /documents, /documents/{id}
├── services/
│   └── orchestration.py     OrchestrationService: persists agent_runs +
│                            audit_logs + approvals from orchestrator output
└── seed.py                  build_demo_project_data() + seed_database()
```

Every agent call writes an `agent_runs` row. Every meaningful decision writes
an `audit_logs` row. The `agent_runs` table supports parent-child links so the
UI can render the orchestrator and its spawned workers as a single flow.

### Frontend (`apps/web/`)

```
apps/web/
├── app/
│   ├── layout.tsx              Sidebar + content shell
│   ├── globals.css             Theme tokens + components
│   ├── page.tsx                Dashboard (recent runs, approvals, demo)
│   ├── tasks/page.tsx          Tasks list
│   ├── tasks/[id]/page.tsx     Task detail (brief, plan, risk, approval)
│   ├── ingestion/page.tsx      Upload + project_data preview + doc list
│   ├── orchestration/page.tsx  Orchestrator overview + agent flow + decisions
│   ├── agents/page.tsx         Agent type catalogue + latest output
│   ├── settings/page.tsx       Integration status placeholders
│   └── api/                    Server-side proxy routes (Next.js → FastAPI)
├── components/                 AgentRunCard, RiskBadge, ApprovalPanel,
│                               TaskBrief, AgentOutputViewer, AuditLogTimeline,
│                               ProjectDataViewer, OrchestrationFlow,
│                               OrchestratorOverview, AgentDetailModal,
│                               StatusDot, Sidebar, RunDemoButton,
│                               TaskRunButton, IngestionUploader
└── lib/                        api.ts (typed client) + types.ts (DTOs)
```

The web app reads `BACKEND_URL` (server) / `NEXT_PUBLIC_BACKEND_URL` (browser).
Secrets stay on the server side via the proxy routes under `app/api/*`.

## Risk model

| Level             | Examples                                                 | Approval         |
| ----------------- | -------------------------------------------------------- | ---------------- |
| `READ_ONLY`       | searching, summarising, planning, retrieving context     | not required     |
| `LOW_RISK_WRITE`  | drafting Jira comments / docs / PR descriptions / files  | not required     |
| `HIGH_RISK_WRITE` | posting to Jira, opening PRs, modifying files, deleting, | **required**     |
|                   | changing statuses, sending messages, touching secrets    |                  |

The `RiskSafetyAgent` classifies actions and the orchestrator gates the
recommended next action accordingly. Real writes are simulated unless an
explicit approval row exists AND a tool integration permits it.

## Permission model

`admin` / `reviewer` / `agent` — wired into the UI as placeholders.

## Working-session transcripts

Mycelium is **not** a surveillance product. Transcripts are explicitly
uploaded via the Ingestion page; there is no screen-recording component.

## Extending later

- **Real LLM models per agent** — `BaseAgent.model` is per-instance; switch
  shallow workers to `gpt-4o-mini` or other providers without touching the
  orchestrator.
- **Graph memory** — implement `MemoryBackend` for Graphiti / Neo4j / FalkorDB
  and register it in `app/memory/base.py::get_memory`.
- **Vector providers** — same pattern for Qdrant / Pinecone / Weaviate.
- **Real Jira / GitHub / Slack** — drop credentials in `.env`; `JiraClient`
  and `GitHubClient` will start hitting real APIs without code changes.
- **Workflow engine** — wrap `OrchestrationService.run` in a Temporal
  workflow when you outgrow synchronous orchestration.

## Legacy stack

The earlier multi-service experiment (services/*, Vite frontend, Neo4j,
Redis Streams, observer agent, etc.) lives in `docker-compose.legacy.yml`
and the existing `services/` and `apps/frontend/` trees. It is unrelated to
the Mycelium MVP foundation but is kept around for reference. Run with:

```bash
docker compose -f docker-compose.legacy.yml up --build
```
