"""Demo seeding utilities.

`build_demo_project_data()` returns a `ProjectData` populated with one fake
Jira task, fake repo files, fake transcripts, fake docs, and a fake previous
agent run. `seed_database()` inserts a baseline Task row so the Tasks page is
non-empty on first run.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations._fakes import (
    DEMO_BOT_EMAIL,
    DEMO_BOT_USER,
    DEMO_PROJECT_KEY,
    DEMO_TASK_TITLE,
    fake_docs,
    fake_jira_tasks,
    fake_previous_runs,
    fake_repo,
    fake_transcripts,
)
from app.models import Project, Task
from app.schemas.project_data import (
    CodeFileData,
    DocData,
    GitHubRepoData,
    JiraTaskData,
    PreviousAgentRunData,
    ProjectData,
    SystemConfigData,
    TranscriptData,
)

logger = logging.getLogger(__name__)


def build_demo_project_data() -> ProjectData:
    """Return a fully-populated ProjectData fixture for the local demo.

    If `MYCELIUM_BOT_JIRA_USER` is set, the bot-assigned task (PAY-103) is
    used as `current_task` so `/agents/demo` exercises the autonomous flow.
    Otherwise the first non-bot task (PAY-101) is used so the approval flow
    is exercised instead.
    """
    jira = fake_jira_tasks()
    repo = fake_repo()
    docs = fake_docs()
    transcripts = fake_transcripts()
    previous = fake_previous_runs()

    code_files = [CodeFileData(**f, repo=repo["name"]) for f in repo["files"]]
    repo_obj = GitHubRepoData(
        owner=repo["owner"],
        name=repo["name"],
        description=repo.get("description"),
        primary_language=repo.get("primary_language"),
        files=code_files,
    )

    # Pick the task for `current_task`.
    bot_user = get_settings().mycelium_bot_jira_user
    candidate = None
    if bot_user:
        for task in jira:
            if (
                bot_user.lower()
                in {
                    str(task.get("assignee") or "").lower(),
                    str(task.get("assignee_email") or "").lower(),
                }
            ):
                candidate = task
                break
    if candidate is None:
        candidate = jira[0]

    return ProjectData(
        user_goal=f"Help engineers complete the Jira task: {candidate.get('title') or DEMO_TASK_TITLE}",
        current_task=JiraTaskData(**candidate),
        jira_tasks=[JiraTaskData(**t) for t in jira],
        github_repositories=[repo_obj],
        code_files=code_files,
        docs=[DocData(**d) for d in docs],
        transcripts=[TranscriptData(**t) for t in transcripts],
        previous_agent_runs=[PreviousAgentRunData(**p) for p in previous],
        available_tools=[
            "jira.read",
            "jira.post_comment",
            "jira.transition",
            "github.read",
            "github.create_branch",
            "github.create_or_update_file",
            "github.open_pull_request",
        ],
        system_config=SystemConfigData(),
        constraints=[
            "Never merge PRs automatically.",
            "Never delete files or branches.",
            "Never modify secrets, .env files, or CI configuration.",
            "Cite sources when summarising docs/transcripts.",
        ],
    )


def seed_database(session: Session) -> None:
    """Insert demo Task rows + a demo Project/Repository for the OL flow."""
    _seed_demo_project(session)

    has_any = session.execute(select(Task).limit(1)).scalar_one_or_none()
    if has_any is not None:
        return
    for issue in fake_jira_tasks():
        session.add(
            Task(
                external_id=issue["key"],
                source="jira",
                project_key=issue.get("project_key", DEMO_PROJECT_KEY),
                title=issue["title"],
                description=issue.get("description"),
                status=issue.get("status") or "To Do",
                assignee=issue.get("assignee"),
                reporter=issue.get("reporter"),
                labels=issue.get("labels") or [],
                priority=issue.get("priority"),
                raw_payload=issue,
            )
        )
    session.commit()
    logger.info("Seeded %s demo tasks.", len(fake_jira_tasks()))


def _seed_demo_project(session: Session) -> None:
    """Create a canonical Project + Repository + a few indexed chunks."""
    from app.memory.project_data import ProjectDataService

    project = session.execute(
        select(Project).where(Project.slug == "demo-payments")
    ).scalar_one_or_none()
    if project is not None:
        return

    pd = ProjectDataService()
    project = pd.ensure_project(
        session,
        slug="demo-payments",
        name="Demo Payments Platform",
        description=(
            "Seeded demo project. Represents a payments service with Jira + "
            "GitHub sources. Used to exercise the OL orchestrator end-to-end."
        ),
        primary_language="python",
        jira_project_key=DEMO_PROJECT_KEY,
    )
    repo_meta = fake_repo()
    owner, _, repo_name = (repo_meta.get("full_name") or "mycelium-demo/payments-service").partition("/")
    repository = pd.ensure_repository(
        session,
        project_id=project.id,
        owner=owner or "mycelium-demo",
        name=repo_name or "payments-service",
        default_branch=repo_meta.get("default_branch") or "main",
        html_url=repo_meta.get("html_url"),
    )
    # Ingest a handful of seeded code files + docs so retrieval has something
    # to return without having to call sync endpoints first.
    for f in repo_meta.get("files", []):
        if not f.get("content"):
            continue
        pd.upsert_repo_file(
            session,
            project_id=project.id,
            repo_id=repository.id,
            path=f.get("path") or "",
            content=f.get("content") or "",
            branch=repository.default_branch,
        )
    for doc in fake_docs():
        pd.chunker  # no-op: keep ChunkingService warm
        drafts = pd.chunker.chunk_doc(
            project_id=project.id,
            source_id=doc.get("id") or doc.get("title", "doc"),
            title=doc.get("title"),
            content=doc.get("content") or "",
        )
        if not drafts:
            continue
        pd._replace_chunks(  # type: ignore[attr-defined]
            session,
            project_id=project.id,
            source_type="doc",
            source_id=drafts[0].source_id,
            drafts=drafts,
        )
    for issue in fake_jira_tasks():
        pd.upsert_jira_ticket(
            session,
            project_id=project.id,
            key=issue["key"],
            title=issue["title"],
            description=issue.get("description"),
            status=issue.get("status"),
            assignee=issue.get("assignee"),
            assignee_email=issue.get("assignee_email"),
            labels=issue.get("labels") or [],
            comments=issue.get("comments") or [],
            raw_payload=issue,
        )
    session.commit()
    logger.info("Seeded demo project %s", project.slug)
