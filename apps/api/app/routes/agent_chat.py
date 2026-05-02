"""POST /chat/agent — Agentic chat with tool calls.

Streams the OpenAI function-calling loop with tools that read AND write to
Jira, GitHub, and Slack. Every tool call is recorded to the agent_actions
Postgres table and broadcast over SSE so the frontend can show a live
action log.

Safety:
- Write tools require confirm=true.
- We never merge PRs, never force-push, never DM-blast.
- Real github/slack/jira writes only happen when MYCELIUM_AGENT_WRITES_ENABLED=true.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from typing import Any
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import text

from app.supabase_client import SupabaseUser, get_supabase_user, service_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat-agent"])

_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
WRITES_ENABLED = os.getenv("MYCELIUM_AGENT_WRITES_ENABLED", "true").lower() == "true"

_action_subscribers: list[asyncio.Queue] = []

# ---------------- Security guardrails ----------------

def _csv_env(name: str) -> set[str]:
    raw = os.getenv(name, "").strip()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


REPO_ALLOWLIST = _csv_env("MYCELIUM_REPO_ALLOWLIST")
REPO_DENYLIST = _csv_env("MYCELIUM_REPO_DENYLIST")
CHANNEL_ALLOWLIST = _csv_env("MYCELIUM_SLACK_CHANNEL_ALLOWLIST")
JIRA_PROJECT_ALLOWLIST = _csv_env("MYCELIUM_JIRA_PROJECT_ALLOWLIST")

WRITE_TOOLS = {"comment_jira", "transition_jira", "assign_jira", "create_jira_issue",
               "create_branch", "commit_file", "open_pr",
               "post_slack", "create_slack_channel", "invite_to_slack_channel", "set_slack_topic"}
DANGEROUS_TOOLS: set[str] = set()  # empty by design — we never registered destructive tools

MAX_WRITES_PER_USER_PER_MIN = int(os.getenv("MYCELIUM_MAX_WRITES_PER_MIN", "20"))
MAX_TEXT_LENGTH = 4000  # cap any user-bound text we write

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"system\s*[:>]\s*you\s+are", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"<\s*script[^>]*>", re.I),
]

_write_log: dict[str, list[float]] = {}


def _rate_limit_check(user_id: str) -> tuple[bool, str | None]:
    now = time.time()
    history = _write_log.setdefault(user_id, [])
    history[:] = [t for t in history if now - t < 60]
    if len(history) >= MAX_WRITES_PER_USER_PER_MIN:
        return False, f"rate limit: {MAX_WRITES_PER_USER_PER_MIN} writes/min exceeded"
    history.append(now)
    return True, None


def _check_repo(owner: str, repo: str) -> tuple[bool, str | None]:
    full = f"{owner}/{repo}".lower()
    if full in REPO_DENYLIST:
        return False, f"repo {full} is on the denylist"
    if REPO_ALLOWLIST and full not in REPO_ALLOWLIST and repo.lower() not in REPO_ALLOWLIST:
        return False, f"repo {full} not in MYCELIUM_REPO_ALLOWLIST"
    return True, None


def _check_channel(channel: str) -> tuple[bool, str | None]:
    c = channel.lstrip("#").lower()
    if CHANNEL_ALLOWLIST and c not in CHANNEL_ALLOWLIST:
        return False, f"channel #{c} not in MYCELIUM_SLACK_CHANNEL_ALLOWLIST"
    return True, None


def _check_jira_project(key: str) -> tuple[bool, str | None]:
    project = key.split("-")[0].lower() if "-" in key else key.lower()
    if JIRA_PROJECT_ALLOWLIST and project not in JIRA_PROJECT_ALLOWLIST:
        return False, f"jira project {project.upper()} not in MYCELIUM_JIRA_PROJECT_ALLOWLIST"
    return True, None


def _sanitize_text(text_content: str) -> str | None:
    """Reject text containing prompt-injection markers or oversized content."""
    if not isinstance(text_content, str):
        return None
    if len(text_content) > MAX_TEXT_LENGTH:
        return None
    for pat in INJECTION_PATTERNS:
        if pat.search(text_content):
            return None
    return text_content


CONSENT_PATTERNS = [
    re.compile(r"\b(yes|yep|yeah|yup|sure|ok(?:ay)?|confirm(?:ed)?|do it|go ahead|proceed|approved?|sounds good|please do|fine)\b", re.I),
]


def _user_consent_in_message(text_content: str) -> bool:
    if not text_content:
        return False
    return any(p.search(text_content) for p in CONSENT_PATTERNS)


def _preflight(name: str, args: dict, user_id: str) -> tuple[bool, str | None]:
    """Returns (allowed, error_message). Runs before every tool call."""
    if name in WRITE_TOOLS:
        ok, why = _rate_limit_check(user_id)
        if not ok:
            return False, why
    if "owner" in args and "repo" in args:
        ok, why = _check_repo(args["owner"], args["repo"])
        if not ok:
            return False, why
    if name == "post_slack" and "channel" in args:
        ok, why = _check_channel(args["channel"])
        if not ok:
            return False, why
    if name in {"comment_jira", "transition_jira", "assign_jira", "read_jira_ticket"} and "key" in args:
        ok, why = _check_jira_project(args["key"])
        if not ok:
            return False, why
    for field in ("text", "body", "content", "message"):
        if field in args and isinstance(args[field], str):
            if _sanitize_text(args[field]) is None:
                return False, f"text in '{field}' rejected (too long or contains suspicious pattern)"
    return True, None


# ---------------- Storage ----------------

async def _ensure_tables():
    """No-op — schema is provisioned in Supabase via supabase/schema.sql."""
    return


async def _record_action(user_id: str, tool: str, args: dict, summary: str, status: str):
    try:
        sb = service_client()
        sb.table("agent_actions").insert({
            "user_id": user_id,
            "tool": tool,
            "args": args,
            "result_summary": summary[:500],
            "status": status,
        }).execute()
    except Exception as e:
        logger.warning("record_action failed: %s", e)
    evt = {"tool": tool, "args": args, "summary": summary, "status": status, "ts": time.time()}
    for q in list(_action_subscribers):
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            pass


async def _save_message(user_id: str, role: str, content: str, conversation_id: str | None = None):
    try:
        sb = service_client()
        row: dict[str, Any] = {"user_id": user_id, "role": role, "content": content}
        if conversation_id:
            row["conversation_id"] = conversation_id
        sb.table("chat_history").insert(row).execute()
    except Exception as e:
        logger.warning("save_message failed: %s", e)


@router.get("/history")
async def get_history(conversation_id: str | None = None, user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        q = sb.table("chat_history").select("role,content,created_at,conversation_id").eq("user_id", user.id).order("id").limit(200)
        if conversation_id:
            q = q.eq("conversation_id", conversation_id)
        res = q.execute()
        return [{"role": r["role"], "content": r["content"], "at": r.get("created_at"), "conversation_id": r.get("conversation_id")} for r in (res.data or [])]
    except Exception as e:
        logger.warning("get_history failed: %s", e)
        return []


@router.delete("/history")
async def clear_history(conversation_id: str | None = None, user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        q = sb.table("chat_history").delete().eq("user_id", user.id)
        if conversation_id:
            q = q.eq("conversation_id", conversation_id)
        q.execute()
    except Exception as e:
        logger.warning("clear_history failed: %s", e)
    return {"cleared": True}


# ---------------- Multi-conversation CRUD ----------------

@router.get("/conversations")
async def list_conversations(user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        res = sb.table("chat_conversations_with_preview").select("*").eq("user_id", user.id).order("updated_at", desc=True).limit(100).execute()
        return res.data or []
    except Exception as e:
        logger.warning("list_conversations failed: %s", e)
        return []


class ConvCreate(BaseModel):
    title: str | None = "New chat"
    mode: str | None = "agent"


@router.post("/conversations")
async def create_conversation(req: ConvCreate, user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        res = sb.table("chat_conversations").insert({
            "user_id": user.id,
            "title": req.title or "New chat",
            "mode": (req.mode or "agent") if (req.mode or "agent") in ("agent", "intel") else "agent",
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.warning("create_conversation failed: %s", e)
        return {"error": str(e)}


class ConvRename(BaseModel):
    title: str


@router.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: str, req: ConvRename, user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        sb.table("chat_conversations").update({"title": req.title[:120]}).eq("id", conv_id).eq("user_id", user.id).execute()
    except Exception as e:
        logger.warning("rename_conversation failed: %s", e)
    return {"ok": True}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        sb.table("chat_conversations").delete().eq("id", conv_id).eq("user_id", user.id).execute()
    except Exception as e:
        logger.warning("delete_conversation failed: %s", e)
    return {"deleted": True}


@router.get("/actions")
async def get_actions(user: SupabaseUser = Depends(get_supabase_user)):
    try:
        sb = service_client()
        res = sb.table("agent_actions").select("tool,args,result_summary,status,created_at").eq("user_id", user.id).order("id", desc=True).limit(50).execute()
        return [{"tool": r["tool"], "args": r.get("args"), "summary": r.get("result_summary"), "status": r.get("status"), "at": r.get("created_at")} for r in (res.data or [])]
    except Exception as e:
        logger.warning("get_actions failed: %s", e)
        return []


@router.get("/actions/stream")
async def stream_actions(user: SupabaseUser = Depends(get_supabase_user)):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _action_subscribers.append(queue)

    async def gen():
        try:
            yield "data: {\"hello\": true}\n\n"
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            if queue in _action_subscribers:
                _action_subscribers.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------- Tool implementations ----------------

async def _jira_request(client: httpx.AsyncClient, method: str, path: str, json_body=None):
    domain = os.getenv("JIRA_DOMAIN", "")
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_TOKEN", "")
    if not (domain and email and token):
        return {"error": "jira not configured"}
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json", "Content-Type": "application/json"}
    try:
        r = await client.request(method, f"https://{domain}{path}", headers=headers, json=json_body, timeout=20)
        if r.status_code >= 400:
            return {"error": f"{r.status_code}", "detail": r.text[:500]}
        if r.status_code == 204 or not r.content:
            return {"ok": True}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


async def _gh_request(client: httpx.AsyncClient, method: str, path: str, json_body=None):
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = await client.request(method, f"https://api.github.com{path}", headers=headers, json=json_body, timeout=30)
        if r.status_code >= 400:
            return {"error": f"{r.status_code}", "detail": r.text[:500]}
        if r.status_code == 204 or not r.content:
            return {"ok": True}
        return r.json()
    except Exception as e:
        return {"error": str(e)}


async def _slack_request(client: httpx.AsyncClient, method: str, json_body: dict):
    token = os.getenv("SLACK_TOKEN", "")
    if not token:
        return {"ok": False, "error": "slack not configured"}
    try:
        r = await client.post(
            f"https://slack.com/api/{method}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            json=json_body,
            timeout=15,
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Tool: list_jira_tickets
async def tool_list_jira_tickets(client: httpx.AsyncClient, status: str | None = None, assignee: str | None = None) -> dict:
    jql_parts = ["created >= -365d"]
    if status:
        jql_parts.append(f'status = "{status}"')
    if assignee:
        # accept "me" / display names / accountId — Jira uses currentUser() for me
        if assignee.lower() in ("me", "currentuser", "current user", "self"):
            jql_parts.append("assignee = currentUser()")
        else:
            jql_parts.append(f'assignee = "{assignee}"')
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    body = {"jql": jql, "maxResults": 30, "fields": ["summary", "status", "assignee", "priority", "issuetype"]}
    res = await _jira_request(client, "POST", "/rest/api/3/search/jql", body)
    if "error" in res:
        return res
    return {"issues": [
        {"key": i["key"], "summary": i["fields"]["summary"], "status": i["fields"]["status"]["name"],
         "assignee": (i["fields"].get("assignee") or {}).get("displayName") or "Unassigned",
         "priority": (i["fields"].get("priority") or {}).get("name"),
         "type": (i["fields"].get("issuetype") or {}).get("name")}
        for i in res.get("issues", [])
    ]}


async def tool_assign_jira(client: httpx.AsyncClient, key: str, assignee_name: str, confirm: bool = True) -> dict:
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_assigned": {key: assignee_name}}
    # Find the accountId for the assignee by name
    user_search = await _jira_request(client, "GET", f"/rest/api/3/user/search?query={assignee_name}")
    if isinstance(user_search, dict) and "error" in user_search:
        return user_search
    if not user_search:
        return {"error": f"no user found matching '{assignee_name}'"}
    account_id = user_search[0].get("accountId")
    res = await _jira_request(client, "PUT", f"/rest/api/3/issue/{key}/assignee", {"accountId": account_id})
    return {"ok": "error" not in res, "assigned_to": user_search[0].get("displayName"), "accountId": account_id, "result": res}


async def tool_list_my_repos(client: httpx.AsyncClient) -> dict:
    res = await _gh_request(client, "GET", "/user/repos?per_page=30&sort=pushed")
    if isinstance(res, dict) and "error" in res:
        return res
    if not isinstance(res, list):
        return {"error": "unexpected response", "raw": str(res)[:200]}
    return {"repos": [
        {"owner": r["owner"]["login"], "name": r["name"], "language": r.get("language"),
         "private": r.get("private"), "pushed_at": r.get("pushed_at"),
         "description": (r.get("description") or "")[:120]}
        for r in res[:25]
    ]}


async def tool_get_default_branch(client: httpx.AsyncClient, owner: str, repo: str) -> dict:
    res = await _gh_request(client, "GET", f"/repos/{owner}/{repo}")
    if isinstance(res, dict) and "error" in res:
        return res
    return {"default_branch": res.get("default_branch", "main")}


async def tool_create_branch(client: httpx.AsyncClient, owner: str, repo: str, new_branch: str, from_branch: str = "", confirm: bool = True) -> dict:
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_created": new_branch}
    if not from_branch:
        repo_info = await _gh_request(client, "GET", f"/repos/{owner}/{repo}")
        from_branch = (repo_info or {}).get("default_branch") or "main"
    ref = await _gh_request(client, "GET", f"/repos/{owner}/{repo}/git/ref/heads/{from_branch}")
    if isinstance(ref, dict) and "error" in ref:
        return {"error": "couldn't read base branch", "detail": ref}
    sha = (ref or {}).get("object", {}).get("sha")
    if not sha:
        return {"error": "no sha for base"}
    res = await _gh_request(client, "POST", f"/repos/{owner}/{repo}/git/refs",
                            {"ref": f"refs/heads/{new_branch}", "sha": sha})
    return res


async def tool_commit_file(client: httpx.AsyncClient, owner: str, repo: str, branch: str, path: str, content: str, message: str, confirm: bool = True) -> dict:
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_committed": {"path": path, "branch": branch, "message": message}}
    # Get existing file sha if it exists (for update vs create)
    existing = await _gh_request(client, "GET", f"/repos/{owner}/{repo}/contents/{path}?ref={branch}")
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if isinstance(existing, dict) and existing.get("sha"):
        body["sha"] = existing["sha"]
    res = await _gh_request(client, "PUT", f"/repos/{owner}/{repo}/contents/{path}", body)
    return res


async def tool_read_jira_ticket(client: httpx.AsyncClient, key: str) -> dict:
    issue = await _jira_request(client, "GET", f"/rest/api/3/issue/{key}")
    if "error" in issue:
        return issue
    comments_res = await _jira_request(client, "GET", f"/rest/api/3/issue/{key}/comment?maxResults=10")
    comments = []
    for c in comments_res.get("comments", []):
        comments.append({"author": (c.get("author") or {}).get("displayName"), "text": _adf_text(c.get("body"))[:500]})
    f = issue.get("fields", {})
    return {
        "key": issue["key"],
        "summary": f.get("summary"),
        "description": _adf_text(f.get("description"))[:1000],
        "status": (f.get("status") or {}).get("name"),
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "priority": (f.get("priority") or {}).get("name"),
        "comments": comments,
    }


async def tool_create_jira_issue(client: httpx.AsyncClient, project_key: str, summary: str, description: str = "", issue_type: str = "Task", priority: str | None = None) -> dict:
    """Create a brand-new Jira ticket."""
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_create": {"project": project_key, "summary": summary, "type": issue_type}}
    fields: dict[str, Any] = {
        "project": {"key": project_key.upper()},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
        }
    if priority:
        fields["priority"] = {"name": priority}
    res = await _jira_request(client, "POST", "/rest/api/3/issue", {"fields": fields})
    if isinstance(res, dict) and "error" in res:
        return res
    return {"ok": True, "key": res.get("key"), "id": res.get("id"), "url": f"https://{os.getenv('JIRA_DOMAIN','')}/browse/{res.get('key')}"}


async def tool_create_slack_channel(client: httpx.AsyncClient, name: str, is_private: bool = False) -> dict:
    """Create a new Slack channel. Channel names must be lowercase, no spaces."""
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_create": name}
    safe_name = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name.lower())[:80]
    return await _slack_request(client, "conversations.create", {"name": safe_name, "is_private": is_private})


async def tool_invite_to_slack_channel(client: httpx.AsyncClient, channel: str, user_names: str) -> dict:
    """Invite users to a channel. user_names is a comma-separated list of display names or Slack user IDs."""
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_invite": user_names, "to": channel}
    # Resolve channel name to ID
    chans = await _slack_request(client, "conversations.list", {})
    ch_id = None
    if chans.get("ok"):
        for c in chans.get("channels", []):
            if c["name"] == channel.lstrip("#"):
                ch_id = c["id"]
                break
    if not ch_id:
        return {"error": f"channel #{channel} not found"}
    # Resolve usernames to IDs
    users_res = await _slack_request(client, "users.list", {})
    user_ids = []
    targets = [n.strip() for n in user_names.split(",") if n.strip()]
    for n in targets:
        if n.startswith("U") and n.isupper():
            user_ids.append(n)
            continue
        for u in users_res.get("members", []):
            if u.get("real_name", "").lower() == n.lower() or u.get("name", "").lower() == n.lower():
                user_ids.append(u["id"])
                break
    if not user_ids:
        return {"error": f"no matching users for '{user_names}'"}
    return await _slack_request(client, "conversations.invite", {"channel": ch_id, "users": ",".join(user_ids)})


async def tool_set_slack_topic(client: httpx.AsyncClient, channel: str, topic: str) -> dict:
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_set_topic_on": channel, "topic": topic}
    chans = await _slack_request(client, "conversations.list", {})
    ch_id = None
    if chans.get("ok"):
        for c in chans.get("channels", []):
            if c["name"] == channel.lstrip("#"):
                ch_id = c["id"]
                break
    if not ch_id:
        return {"error": f"channel #{channel} not found"}
    return await _slack_request(client, "conversations.setTopic", {"channel": ch_id, "topic": topic})


async def tool_comment_jira(client: httpx.AsyncClient, key: str, text_content: str) -> dict:
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_commented": text_content[:200]}
    body = {"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text_content}]}]}}
    res = await _jira_request(client, "POST", f"/rest/api/3/issue/{key}/comment", body)
    return {"ok": "error" not in res, "result": res}


async def tool_transition_jira(client: httpx.AsyncClient, key: str, status: str) -> dict:
    transitions = await _jira_request(client, "GET", f"/rest/api/3/issue/{key}/transitions")
    if "error" in transitions:
        return transitions
    target = next((t for t in transitions.get("transitions", []) if t["name"].lower() == status.lower()), None)
    if not target:
        return {"error": f"no transition named '{status}'", "available": [t["name"] for t in transitions.get("transitions", [])]}
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_moved_to": status}
    res = await _jira_request(client, "POST", f"/rest/api/3/issue/{key}/transitions", {"transition": {"id": target["id"]}})
    return {"ok": "error" not in res, "result": res}


async def tool_list_repo_files(client: httpx.AsyncClient, owner: str, repo: str, path: str = "") -> dict:
    res = await _gh_request(client, "GET", f"/repos/{owner}/{repo}/contents/{path}")
    if isinstance(res, dict) and "error" in res:
        return res
    return {"items": [{"name": item["name"], "path": item["path"], "type": item["type"], "size": item.get("size")} for item in (res if isinstance(res, list) else [res])]}


async def tool_read_file(client: httpx.AsyncClient, owner: str, repo: str, path: str) -> dict:
    res = await _gh_request(client, "GET", f"/repos/{owner}/{repo}/contents/{path}")
    if isinstance(res, dict) and "error" in res:
        return res
    if not isinstance(res, dict) or "content" not in res:
        return {"error": "not a file"}
    try:
        content = base64.b64decode(res["content"]).decode("utf-8", errors="replace")
        return {"path": path, "content": content[:8000], "sha": res["sha"]}
    except Exception as e:
        return {"error": str(e)}


async def tool_open_pr(client: httpx.AsyncClient, owner: str, repo: str, branch: str, title: str, body: str, base: str = "") -> dict:
    if not base:
        repo_info = await _gh_request(client, "GET", f"/repos/{owner}/{repo}")
        base = (repo_info or {}).get("default_branch") or "main"
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_opened": {"title": title, "branch": branch, "base": base}}
    res = await _gh_request(client, "POST", f"/repos/{owner}/{repo}/pulls", {"title": title, "body": body, "head": branch, "base": base})
    return res


async def tool_post_slack(client: httpx.AsyncClient, channel: str, text_content: str) -> dict:
    if not WRITES_ENABLED:
        return {"ok": True, "dry_run": True, "would_have_sent": {"channel": channel, "text": text_content[:200]}}
    return await _slack_request(client, "chat.postMessage", {"channel": channel, "text": text_content})


def _adf_text(adf: Any) -> str:
    if not adf:
        return ""
    if isinstance(adf, str):
        return adf
    if isinstance(adf, dict):
        if adf.get("text"):
            return adf["text"]
        if isinstance(adf.get("content"), list):
            return " ".join(_adf_text(c) for c in adf["content"])
    return ""


# ---------------- Tool registry / OpenAI function definitions ----------------

TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "create_jira_issue",
        "description": "Create a NEW Jira ticket. Use this when the user asks to 'add a task', 'create a todo', 'open a ticket', 'log a story'. Do NOT use comment_jira for that.",
        "parameters": {"type": "object", "required": ["project_key", "summary"], "properties": {
            "project_key": {"type": "string", "description": "Project key like 'KAN'."},
            "summary": {"type": "string", "description": "The ticket title/summary."},
            "description": {"type": "string", "description": "Optional longer description."},
            "issue_type": {"type": "string", "description": "Task, Story, Bug, Epic. Default Task."},
            "priority": {"type": "string", "description": "Highest, High, Medium, Low, Lowest. Optional."},
        }},
    }},
    {"type": "function", "function": {
        "name": "create_slack_channel",
        "description": "Create a NEW Slack channel. Channel names are auto-lowercased and dashes replace spaces.",
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string"},
            "is_private": {"type": "boolean", "description": "Default false (public channel)."},
        }},
    }},
    {"type": "function", "function": {
        "name": "invite_to_slack_channel",
        "description": "Invite people to a Slack channel by display name (e.g. 'Yuvaansh Kapila, Michael Mazilu').",
        "parameters": {"type": "object", "required": ["channel", "user_names"], "properties": {
            "channel": {"type": "string"},
            "user_names": {"type": "string", "description": "Comma-separated display names or Slack user IDs."},
        }},
    }},
    {"type": "function", "function": {
        "name": "set_slack_topic",
        "description": "Set the topic of a Slack channel.",
        "parameters": {"type": "object", "required": ["channel", "topic"], "properties": {
            "channel": {"type": "string"}, "topic": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_jira_tickets",
        "description": "List Jira tickets. Call with NO filters to see ALL tickets in the workspace. Only filter when the user specifically asks (e.g. 'unassigned tickets', 'in progress'). Pass assignee='me' for current user.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "description": "Optional. e.g. 'To Do', 'In Progress', 'Done'"},
            "assignee": {"type": "string", "description": "Optional. Display name or 'me' for current user."},
        }},
    }},
    {"type": "function", "function": {
        "name": "assign_jira",
        "description": "Assign a Jira ticket to a user by display name (e.g. 'Yuvaansh Kapila').",
        "parameters": {"type": "object", "required": ["key", "assignee_name"], "properties": {
            "key": {"type": "string"}, "assignee_name": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_my_repos",
        "description": "List GitHub repos owned by or accessible to the authenticated user. Use this BEFORE asking the user which repo to use — you already have access.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_default_branch",
        "description": "Get the default branch name (usually main or master) for a repo.",
        "parameters": {"type": "object", "required": ["owner", "repo"], "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "create_branch",
        "description": "Create a new branch from the default branch (or specified base).",
        "parameters": {"type": "object", "required": ["owner", "repo", "new_branch"], "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"},
            "new_branch": {"type": "string"}, "from_branch": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "commit_file",
        "description": "Create or update a single file on a branch. Use this to make code changes before opening a PR.",
        "parameters": {"type": "object", "required": ["owner", "repo", "branch", "path", "content", "message"], "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"}, "branch": {"type": "string"},
            "path": {"type": "string"}, "content": {"type": "string"}, "message": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "read_jira_ticket",
        "description": "Read full details of one Jira ticket including comments.",
        "parameters": {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}},
    }},
    {"type": "function", "function": {
        "name": "comment_jira",
        "description": "Add a comment to a Jira ticket. Just call it — don't ask the user for permission first.",
        "parameters": {"type": "object", "required": ["key", "text"], "properties": {
            "key": {"type": "string"}, "text": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "transition_jira",
        "description": "Move a Jira ticket to a new status (e.g. 'In Progress', 'Done'). Just call it.",
        "parameters": {"type": "object", "required": ["key", "status"], "properties": {
            "key": {"type": "string"}, "status": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_repo_files",
        "description": "List files/dirs at a path in a GitHub repo.",
        "parameters": {"type": "object", "required": ["owner", "repo"], "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a file's contents from a GitHub repo.",
        "parameters": {"type": "object", "required": ["owner", "repo", "path"], "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "open_pr",
        "description": "Open a pull request from a branch to the base branch. Just call it.",
        "parameters": {"type": "object", "required": ["owner", "repo", "branch", "title", "body"], "properties": {
            "owner": {"type": "string"}, "repo": {"type": "string"}, "branch": {"type": "string"},
            "title": {"type": "string"}, "body": {"type": "string"}, "base": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "post_slack",
        "description": "Post a message to a Slack channel by name (e.g. 'all-my-onboarding-pal'). Just call it.",
        "parameters": {"type": "object", "required": ["channel", "text"], "properties": {
            "channel": {"type": "string"}, "text": {"type": "string"},
        }},
    }},
]


async def _execute_tool(client: httpx.AsyncClient, name: str, args: dict, user_id: str, latest_user_message: str = "") -> str:
    """Run a tool, record the action, return JSON-serialized result."""
    summary_args = {k: (v if not isinstance(v, str) or len(v) < 80 else v[:80] + "…") for k, v in args.items()}

    # SECURITY: preflight checks (allowlists, rate limits, prompt-injection)
    allowed, why = _preflight(name, args, user_id)
    if not allowed:
        await _record_action(user_id, name, summary_args, f"BLOCKED: {why}", "blocked")
        return json.dumps({"error": "blocked by security policy", "reason": why})

    # SECURITY: require explicit user confirmation in the latest message for write tools.
    if name in WRITE_TOOLS and not _user_consent_in_message(latest_user_message):
        await _record_action(user_id, name, summary_args, "AWAITING USER CONFIRMATION", "awaiting_confirm")
        return json.dumps({
            "error": "awaiting_confirmation",
            "message": "This write action requires explicit user consent in the same turn. "
                       "Describe to the user exactly what you're about to do (target, content, side effects), then ask "
                       "'Type \"yes\" or \"go ahead\" to proceed.' Wait for the user reply before calling this tool again.",
            "what_was_attempted": {"tool": name, "args": summary_args},
        })

    await _record_action(user_id, name, summary_args, f"running {name}", "running")
    try:
        if name == "list_jira_tickets":
            result = await tool_list_jira_tickets(client, args.get("status"), args.get("assignee"))
        elif name == "read_jira_ticket":
            result = await tool_read_jira_ticket(client, args["key"])
        elif name == "assign_jira":
            result = await tool_assign_jira(client, args["key"], args["assignee_name"])
        elif name == "create_jira_issue":
            result = await tool_create_jira_issue(client, args["project_key"], args["summary"],
                                                  args.get("description", ""), args.get("issue_type", "Task"),
                                                  args.get("priority"))
        elif name == "create_slack_channel":
            result = await tool_create_slack_channel(client, args["name"], args.get("is_private", False))
        elif name == "invite_to_slack_channel":
            result = await tool_invite_to_slack_channel(client, args["channel"], args["user_names"])
        elif name == "set_slack_topic":
            result = await tool_set_slack_topic(client, args["channel"], args["topic"])
        elif name == "comment_jira":
            result = await tool_comment_jira(client, args["key"], args["text"])
        elif name == "transition_jira":
            result = await tool_transition_jira(client, args["key"], args["status"])
        elif name == "list_my_repos":
            result = await tool_list_my_repos(client)
        elif name == "get_default_branch":
            result = await tool_get_default_branch(client, args["owner"], args["repo"])
        elif name == "create_branch":
            result = await tool_create_branch(client, args["owner"], args["repo"], args["new_branch"], args.get("from_branch", ""))
        elif name == "commit_file":
            result = await tool_commit_file(client, args["owner"], args["repo"], args["branch"], args["path"], args["content"], args["message"])
        elif name == "list_repo_files":
            result = await tool_list_repo_files(client, args["owner"], args["repo"], args.get("path", ""))
        elif name == "read_file":
            result = await tool_read_file(client, args["owner"], args["repo"], args["path"])
        elif name == "open_pr":
            result = await tool_open_pr(client, args["owner"], args["repo"], args["branch"], args["title"], args["body"], args.get("base", ""))
        elif name == "post_slack":
            result = await tool_post_slack(client, args["channel"], args["text"])
        else:
            result = {"error": f"unknown tool {name}"}
        status = "error" if isinstance(result, dict) and "error" in result else "ok"
        await _record_action(user_id, name, summary_args, json.dumps(result)[:300], status)
        return json.dumps(result)[:6000]
    except Exception as e:
        await _record_action(user_id, name, summary_args, f"exception: {e}", "error")
        return json.dumps({"error": str(e)})


# ---------------- The agent loop ----------------

class AgentChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    save_history: bool = True
    conversation_id: str | None = None


SYSTEM_PROMPT_BASE = """You are Mycelium — an agentic engineering assistant for a small team.

TOOL SELECTION — pick the RIGHT one. Common mistakes to avoid:
- "create a task / todo / ticket / story" → create_jira_issue (NOT comment_jira)
- "make a new channel" → create_slack_channel (NOT post_slack)
- "add Yuvaansh to #engineering" → invite_to_slack_channel
- "set the topic of #foo to bar" → set_slack_topic
- "comment on KAN-3" / "leave a note on KAN-3" → comment_jira
- "move KAN-3 to Done" → transition_jira
- "assign KAN-3 to me" → assign_jira
- "post in #channel" / "send a message" → post_slack
- "open a PR" → open_pr
- "make a branch" → create_branch
- "edit a file" / "commit X" → commit_file

WRITE TOOLS NEED USER CONSENT (security):
- Read tools (list_*, read_*, get_*) — call freely.
- Write tools (anything that creates, edits, posts, transitions, assigns, invites) — describe what you'll do, end with "Type 'yes' to proceed.", wait. Only call after the user replies with yes/ok/proceed/go ahead.
- The system enforces this — write calls without consent in the latest user message are rejected.
- One consent covers a whole batch — if you need to do 3 writes, list all 3, ask once, do all 3 on yes.

LIVE CONTEXT below lists every repo, ticket, channel, team member. Don't ask "which repo?" or "what's your GitHub username?". Don't say "I don't have access" if the data is right there.
"""


def _build_web_sessions_context(limit: int = 5) -> str:
    """Return a markdown block summarising the user's most recent web-recorded
    sessions. Pulled from ``source_documents`` where ``source_type='web_session'``.

    Silently returns an empty string on any failure — context enrichment is
    best-effort and must never break the chat endpoint.
    """
    try:
        from app.db import SessionLocal
        from app.models import SourceDocument
        from sqlalchemy import select

        with SessionLocal() as session:
            rows = session.execute(
                select(SourceDocument)
                .where(SourceDocument.source_type == "web_session")
                .order_by(SourceDocument.created_at.desc())
                .limit(limit)
            ).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.debug("web session context unavailable: %s", exc)
        return ""

    if not rows:
        return ""

    parts: list[str] = [
        "",
        "RECENT USER WEB SESSIONS (what the user has been doing in the product UI;"
        " use these to understand intent and ongoing workflows):",
    ]
    for doc in rows:
        meta = doc.doc_metadata or {}
        workflows = meta.get("workflows") or []
        workflow_names = ", ".join(wf.get("name", "") for wf in workflows if wf.get("name"))
        duration = meta.get("duration_seconds", 0)
        events = meta.get("event_count", 0)
        pages = meta.get("pages_visited") or []
        parts.append("")
        parts.append(f"  • {doc.title}")
        parts.append(
            f"    — duration {duration}s, {events} events, pages: {', '.join(pages[:6]) or '(none)'}"
        )
        if workflow_names:
            parts.append(f"    — detected workflows: {workflow_names}")
        summary = (doc.content or "").strip()
        if summary:
            parts.append("    — summary:")
            snippet = summary[:800].replace("\n", "\n      ")
            parts.append(f"      {snippet}")
    parts.append("")
    return "\n".join(parts)


async def _build_live_context() -> str:
    """Pre-fetch real data so the agent doesn't have to discover it.
    Mirrors chat_intel's context — same commits, PRs, issues, slack, jira data."""
    try:
        from app.routes.chat_intel import fetch_github, fetch_slack, fetch_jira
        async with httpx.AsyncClient() as client:
            slack = await fetch_slack(client)
            slack_users = {m["user"] for m in slack["messages"] if m.get("user")}
            # Don't filter repos — keeping all of them. The user wants completeness.
            gh, jira = await asyncio.gather(
                fetch_github(client, None),
                fetch_jira(client),
            )

        repos_lines = "\n".join(
            f"  - {r['owner']}/{r['name']} ({r.get('language') or '?'}) - {(r.get('description') or '')[:60]}"
            for r in gh["repos"][:10]
        ) or "  (none)"

        commits_lines = "\n".join(
            f"  - {c['repo']}: {(c.get('message') or '')[:80]} — {c.get('author')}"
            for c in gh["commits"][:15]
        ) or "  (none)"

        prs_lines = "\n".join(
            f"  - {p['repo']}#{p['number']} [{('merged' if p.get('merged') else p.get('state'))}] {p.get('title')} — {p.get('author')}"
            for p in gh["prs"][:12]
        ) or "  (none)"

        issues_lines = "\n".join(
            f"  - {i['repo']}#{i['number']} [{i['state']}] {i.get('title')} — by {i.get('author')}"
            + (f" (assigned: {i['assignee']})" if i.get("assignee") else "")
            for i in gh["issues"][:10]
        ) or "  (none)"

        # Tally commits by author for the "who has the most commits" question
        author_counts: dict[str, int] = {}
        for c in gh["commits"]:
            a = c.get("author") or "?"
            author_counts[a] = author_counts.get(a, 0) + 1
        contributors_lines = "\n".join(
            f"  - {a}: {n} recent commits" for a, n in sorted(author_counts.items(), key=lambda x: -x[1])[:10]
        ) or "  (none)"

        jira_lines = "\n".join(
            f"  - {j['key']} [{j['status']}] {j.get('priority') or ''} {j['summary']} → {j['assignee']}"
            for j in jira[:15]
        ) or "  (none)"

        # Skip only join/leave filler — keep all real messages.
        import re as _re
        _join_re = _re.compile(r"(joined #|has joined|<@.+> joined)", _re.I)
        _real = [m for m in slack["messages"]
                 if (m.get("text") or "").strip() and not _join_re.search(m.get("text") or "")]
        slack_msgs_lines = "\n".join(
            f"  - #{m['channel']} <{m['user']}>: {(m.get('text') or '')[:120]}"
            for m in _real[:20]
        ) or "  (no messages)"

        slack_channels = sorted({m["channel"] for m in slack["messages"]})
        users = sorted(slack_users)

        return f"""
LIVE CONTEXT (already fetched, don't re-fetch — answer directly from this):

REPOS (use these as owner/repo for any GitHub tool):
{repos_lines}

RECENT COMMITS:
{commits_lines}

CONTRIBUTOR TALLY (commit count per author across the data we have):
{contributors_lines}

PULL REQUESTS:
{prs_lines}

ISSUES:
{issues_lines}

JIRA TICKETS:
{jira_lines}

SLACK MESSAGES (newest first — line 1 is the most recent):
{slack_msgs_lines}

SLACK CHANNELS YOU CAN POST TO:
  {", ".join(slack_channels) or "(none)"}

TEAM MEMBERS (Slack display names):
  {", ".join(users[:20]) or "(none)"}
{_build_web_sessions_context()}
When the user asks who has the most commits, who is working on what, what PRs are open, etc — answer directly from the data above. Do NOT say you don't have access; the data is right here.
"""
    except Exception as e:
        logger.warning("live context build failed: %s", e)
        return f"\nLIVE CONTEXT: (unavailable — {e})\n"


@router.post("/agent")
async def agent_chat(req: AgentChatRequest, user: SupabaseUser = Depends(get_supabase_user)):
    await _ensure_tables()
    if req.save_history and req.messages:
        await _save_message(user.id, "user", req.messages[-1].get("content", ""), req.conversation_id)

    live_ctx = await _build_live_context()
    convo = [{"role": "system", "content": SYSTEM_PROMPT_BASE + live_ctx}, *req.messages]
    latest_user = ""
    for m in reversed(req.messages):
        if m.get("role") == "user":
            latest_user = m.get("content", "")
            break

    async def gen():
        nonlocal convo
        async with httpx.AsyncClient() as client:
            for _step in range(8):
                try:
                    resp = await _openai.chat.completions.create(
                        model="gpt-4o",
                        messages=convo,
                        tools=TOOL_DEFS,
                        tool_choice="auto",
                        max_tokens=900,
                    )
                except Exception as e:
                    yield f"\n[error: {e}]"
                    return

                msg = resp.choices[0].message
                if msg.tool_calls:
                    convo.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                        {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ]})
                    if msg.content:
                        yield msg.content + "\n"
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except Exception:
                            args = {}
                        yield f"\n→ {tc.function.name}({json.dumps(args)[:120]})\n"
                        result_json = await _execute_tool(client, tc.function.name, args, user.id, latest_user)
                        convo.append({"role": "tool", "tool_call_id": tc.id, "content": result_json})
                    continue
                final = msg.content or ""
                if req.save_history:
                    await _save_message(user.id, "assistant", final, req.conversation_id)
                yield final
                return

            yield "\n[stopped: hit 8-step tool-call limit]"

    return StreamingResponse(gen(), media_type="text/plain")
