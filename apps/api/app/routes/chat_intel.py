"""POST /chat/intel — Mycelium intelligence chat.

Direct OpenAI streaming with live data from GitHub, Slack, Jira, plus observer
events. Mirrors the mycelium/ Next.js prototype but lives in the real eureka API.

Storage: transcripts cached in Postgres (table: mycelium_transcripts).
Auth: requires DEV_MODE or Bearer token like other routes.
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

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import text

from app.supabase_client import SupabaseUser, get_supabase_user, service_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat-intel"])

_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

VISION_KEYWORDS = re.compile(
    r"\b(image|picture|photo|screenshot|logo|diagram|chart|graph|drawing|design|mockup|figma|whiteboard|attached|attachment|visual|see|show|look|appears?)\b",
    re.IGNORECASE,
)
JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")

CACHE: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str, ttl: float):
    v = CACHE.get(key)
    if v and time.time() - v[0] < ttl:
        return v[1]
    return None


def _cache_set(key: str, value: Any):
    CACHE[key] = (time.time(), value)


# ---------------- GitHub ----------------

async def _gh_request(client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = await client.get(f"https://api.github.com{path}", headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


async def fetch_github(client: httpx.AsyncClient, team_logins: set[str] | None = None) -> dict[str, Any]:
    cache_key = "github:" + ",".join(sorted(team_logins or []))
    cached = _cache_get(cache_key, 600)
    if cached:
        return cached

    repos = await _gh_request(client, "/user/repos", {"per_page": 30, "sort": "pushed"})
    if not isinstance(repos, list):
        repos = []
    # Fine-grained PATs can fail on /user/repos; fall back to configured repo.
    if not repos:
        owner = os.getenv("GITHUB_OWNER", "") or os.getenv("GITHUB_ORG", "")
        repo = os.getenv("GITHUB_REPO", "")
        if owner and repo:
            repos = [{"name": repo, "owner": {"login": owner}, "language": None, "description": ""}]

    if team_logins:
        team_norms = {t.lower().replace(" ", "") for t in team_logins}
        relevant = []
        for r in repos[:20]:
            commits = await _gh_request(client, f"/repos/{r['owner']['login']}/{r['name']}/commits", {"per_page": 5})
            if isinstance(commits, list):
                logins = {((c.get("author") or {}).get("login") or "").lower() for c in commits if c.get("author")}
                names = {(c.get("commit", {}).get("author") or {}).get("name") or "" for c in commits}
                norms = {n.lower().replace(" ", "") for n in names}
                if logins & team_norms or norms & team_norms or any(any(t in n for t in team_norms if len(t) > 3) for n in (logins | norms)):
                    relevant.append(r)
            if len(relevant) >= 10:
                break
        if relevant:
            repos = relevant

    async def commits_for(repo):
        return await _gh_request(client, f"/repos/{repo['owner']['login']}/{repo['name']}/commits", {"per_page": 5})

    async def prs_for(repo):
        return await _gh_request(client, f"/repos/{repo['owner']['login']}/{repo['name']}/pulls", {"state": "all", "per_page": 5, "sort": "updated", "direction": "desc"})

    async def issues_for(repo):
        return await _gh_request(client, f"/repos/{repo['owner']['login']}/{repo['name']}/issues", {"state": "all", "per_page": 5})

    commits_lists, prs_lists, issues_lists = await asyncio.gather(
        asyncio.gather(*[commits_for(r) for r in repos[:8]]),
        asyncio.gather(*[prs_for(r) for r in repos[:8]]),
        asyncio.gather(*[issues_for(r) for r in repos[:8]]),
    )

    commits: list[dict] = []
    for repo, lst in zip(repos[:8], commits_lists):
        if isinstance(lst, list):
            for c in lst:
                commits.append({
                    "repo": repo["name"],
                    "message": (c.get("commit", {}).get("message") or "").split("\n")[0],
                    "author": c.get("commit", {}).get("author", {}).get("name"),
                    "date": c.get("commit", {}).get("author", {}).get("date"),
                })

    prs: list[dict] = []
    for repo, lst in zip(repos[:8], prs_lists):
        if isinstance(lst, list):
            for p in lst:
                prs.append({
                    "repo": repo["name"],
                    "number": p.get("number"),
                    "title": p.get("title"),
                    "state": p.get("state"),
                    "merged": bool(p.get("merged_at")),
                    "author": (p.get("user") or {}).get("login"),
                })

    issues: list[dict] = []
    for repo, lst in zip(repos[:8], issues_lists):
        if isinstance(lst, list):
            for i in lst:
                if i.get("pull_request"):
                    continue
                issues.append({
                    "repo": repo["name"],
                    "number": i.get("number"),
                    "title": i.get("title"),
                    "state": i.get("state"),
                    "author": (i.get("user") or {}).get("login"),
                    "assignee": ((i.get("assignee") or {}).get("login")),
                })

    out = {
        "repos": [{"name": r["name"], "language": r.get("language"), "owner": r["owner"]["login"], "description": (r.get("description") or "")[:80]} for r in repos[:10]],
        "commits": commits[:15],
        "prs": prs[:12],
        "issues": issues[:10],
    }
    _cache_set(cache_key, out)
    return out


# ---------------- Slack ----------------

async def _slack_fetch(client: httpx.AsyncClient, method: str, params: dict | None = None) -> dict:
    token = os.getenv("SLACK_TOKEN", "")
    if not token:
        return {"ok": False}
    try:
        r = await client.get(f"https://slack.com/api/{method}", params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.json()
    except Exception:
        return {"ok": False}


async def fetch_slack(client: httpx.AsyncClient) -> dict[str, Any]:
    cached = _cache_get("slack", 10)
    if cached:
        return cached

    users_res = await _slack_fetch(client, "users.list", {"limit": "200"})
    user_map = {}
    for u in (users_res.get("members") or []):
        user_map[u["id"]] = {
            "name": u.get("real_name") or u.get("name") or u["id"],
            "email": (u.get("profile") or {}).get("email"),
        }

    channels_res = await _slack_fetch(client, "conversations.list", {"limit": "20", "types": "public_channel"})
    channels = [c for c in (channels_res.get("channels") or []) if c.get("is_member")]

    async def hist(ch):
        return await _slack_fetch(client, "conversations.history", {"channel": ch["id"], "limit": "20"})

    histories = await asyncio.gather(*[hist(c) for c in channels[:5]])

    messages = []
    for ch, h in zip(channels[:5], histories):
        for m in (h.get("messages") or []):
            uinfo = user_map.get(m.get("user"), {"name": m.get("user")})
            messages.append({
                "channel": ch["name"],
                "user": uinfo["name"],
                "userId": m.get("user"),
                "userEmail": uinfo.get("email"),
                "text": m.get("text", ""),
                "ts": m.get("ts"),
                "thread_ts": m.get("thread_ts"),
                "files": [
                    {"id": f.get("id"), "name": f.get("name"), "mimetype": f.get("mimetype"), "url_private": f.get("url_private")}
                    for f in (m.get("files") or [])
                ],
                "reactions": m.get("reactions") or [],
            })

    out = {"messages": messages, "user_map": user_map}
    _cache_set("slack", out)
    return out


# ---------------- Jira ----------------

async def fetch_jira(client: httpx.AsyncClient) -> list[dict]:
    cached = _cache_get("jira", 120)
    if cached:
        return cached

    domain = os.getenv("JIRA_DOMAIN", "")
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_TOKEN", "")
    if not (domain and email and token):
        return []

    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json", "Content-Type": "application/json"}

    try:
        r = await client.post(
            f"https://{domain}/rest/api/3/search/jql",
            headers=headers,
            json={
                "jql": "created >= -365d ORDER BY updated DESC",
                "maxResults": 30,
                "fields": ["summary", "status", "assignee", "priority", "updated", "reporter", "issuetype"],
            },
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []

    issues = []
    for i in (data.get("issues") or []):
        f = i.get("fields", {})
        issues.append({
            "key": i["key"],
            "summary": f.get("summary"),
            "status": (f.get("status") or {}).get("name"),
            "assignee": (f.get("assignee") or {}).get("displayName") or "Unassigned",
            "reporter": (f.get("reporter") or {}).get("displayName"),
            "priority": (f.get("priority") or {}).get("name"),
            "type": (f.get("issuetype") or {}).get("name"),
            "updated": f.get("updated"),
        })

    _cache_set("jira", issues)
    return issues


# ---------------- Observer events ----------------

async def _fetch_docker_summary() -> dict[str, Any]:
    """Pull docker container state, stats, and recent events for chat context."""
    cached = _cache_get("docker", 15)
    if cached:
        return cached
    try:
        from app.routes import docker_obs as dobs
        loop = asyncio.get_event_loop()

        def _gather():
            client = dobs._docker()
            services = []
            for c in client.containers.list(all=True):
                state = c.attrs.get("State", {}) or {}
                cfg = c.attrs.get("Config", {}) or {}
                services.append({
                    "name": c.name,
                    "image": cfg.get("Image"),
                    "status": c.status,
                    "health": (state.get("Health") or {}).get("Status"),
                    "exit_code": state.get("ExitCode"),
                    "restart_count": c.attrs.get("RestartCount", 0),
                })
            stats_summary = []
            for c in client.containers.list():
                try:
                    s = c.stats(stream=False)
                    stats_summary.append({
                        "name": c.name,
                        "cpu": _safe_cpu_percent(s),
                        "mem": _safe_mem_percent(s),
                    })
                except Exception:
                    pass
            return services, stats_summary

        services, stats_list = await loop.run_in_executor(None, _gather)
        out = {
            "services": services,
            "stats": stats_list,
            "events": list(dobs._recent_events)[-15:],
        }
        _cache_set("docker", out)
        return out
    except Exception as e:
        return {"services": [], "stats": [], "events": [], "error": str(e)}


def _safe_cpu_percent(stats: dict) -> float:
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu = stats.get("precpu_stats", {})
        cd = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu.get("cpu_usage", {}).get("total_usage", 0)
        sd = cpu_stats.get("system_cpu_usage", 0) - precpu.get("system_cpu_usage", 0)
        n = cpu_stats.get("online_cpus") or 1
        return round((cd / sd) * n * 100, 1) if sd > 0 and cd > 0 else 0.0
    except Exception:
        return 0.0


def _safe_mem_percent(stats: dict) -> float:
    try:
        m = stats.get("memory_stats", {})
        cache = (m.get("stats") or {}).get("cache", 0) or (m.get("stats") or {}).get("inactive_file", 0)
        used = max(m.get("usage", 0) - cache, 0)
        return round((used / (m.get("limit", 1) or 1)) * 100, 1)
    except Exception:
        return 0.0


async def fetch_observer_events() -> list[dict]:
    try:
        sb = service_client()
        res = sb.table("observer_events").select("type,source,actor,object,occurred_at").order("id", desc=True).limit(30).execute()
        return [
            {"type": r["type"], "source": r.get("source"), "actor": r.get("actor"),
             "object": r.get("object"), "timestamp": r.get("occurred_at")}
            for r in (res.data or [])
        ]
    except Exception as e:
        logger.warning("observer query failed: %s", e)
        return []


# ---------------- Transcripts (Postgres) ----------------

async def _ensure_transcripts_table():
    """No-op — provisioned in supabase/schema.sql."""
    return


async def get_transcript(file_id: str) -> str | None:
    try:
        sb = service_client()
        res = sb.table("mycelium_transcripts").select("text").eq("file_id", file_id).maybe_single().execute()
        return res.data["text"] if res.data else None
    except Exception:
        return None


async def save_transcript(file_id: str, name: str, mimetype: str, text_content: str):
    try:
        sb = service_client()
        sb.table("mycelium_transcripts").upsert({
            "file_id": file_id,
            "name": name,
            "mimetype": mimetype,
            "text": text_content,
        }).execute()
    except Exception as e:
        logger.warning("transcript save failed: %s", e)


async def transcribe_slack_file(client: httpx.AsyncClient, file_id: str, url: str, name: str, mimetype: str) -> str | None:
    cached = await get_transcript(file_id)
    if cached:
        return cached
    try:
        token = os.getenv("SLACK_TOKEN", "")
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code != 200:
            return None
        if len(r.content) > 25 * 1024 * 1024:
            return f"[file too large: {name}]"
        result = await _openai.audio.transcriptions.create(
            file=(name, r.content, mimetype),
            model="whisper-1",
        )
        await save_transcript(file_id, name, mimetype, result.text)
        return result.text
    except Exception as e:
        return f"[transcription failed: {e}]"


async def download_slack_image(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        token = os.getenv("SLACK_TOKEN", "")
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.status_code != 200:
            return None
        mime = r.headers.get("content-type", "image/png")
        b64 = base64.b64encode(r.content).decode()
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None


# ---------------- Cross-system links ----------------

def build_links(commits, slack_msgs, jira_issues, prs):
    keys = {j["key"] for j in jira_issues}
    out = []
    for c in commits:
        for k in JIRA_KEY_RE.findall(c.get("message") or ""):
            if k in keys:
                out.append({"type": "commit→jira", "from": f"{c['repo']}: {(c['message'] or '')[:50]}", "to": k})
    for m in slack_msgs:
        for k in JIRA_KEY_RE.findall(m.get("text") or ""):
            if k in keys:
                out.append({"type": "slack→jira", "from": f"#{m['channel']} <{m['user']}>", "to": k})
    for p in prs:
        for k in JIRA_KEY_RE.findall(p.get("title") or ""):
            if k in keys:
                out.append({"type": "pr→jira", "from": f"{p['repo']}#{p['number']}", "to": k})
    return out[:15]


def build_identity(slack_msgs, gh_commits, jira_issues):
    """Quick identity matching by name/email."""
    by_name: dict[str, dict] = {}
    for m in slack_msgs:
        name = m.get("user")
        if not name or name == m.get("userId"):
            continue
        ent = by_name.setdefault(name.lower(), {"slackName": name, "email": m.get("userEmail")})
    gh_names = {c.get("author") for c in gh_commits if c.get("author")}
    for gh in gh_names:
        if not gh:
            continue
        match = next((v for k, v in by_name.items() if gh.lower() in k or k in gh.lower()), None)
        if match:
            match["githubAuthor"] = gh
        else:
            by_name[gh.lower()] = {"githubAuthor": gh}
    jira_names = set()
    for j in jira_issues:
        if j.get("assignee") and j["assignee"] != "Unassigned":
            jira_names.add(j["assignee"])
        if j.get("reporter"):
            jira_names.add(j["reporter"])
    for jn in jira_names:
        match = next((v for k, v in by_name.items() if jn.lower().split()[0] in k or k.split()[0] in jn.lower()), None)
        if match:
            match["jiraName"] = jn
        else:
            by_name[jn.lower()] = {"jiraName": jn}
    return [v for v in by_name.values() if sum(1 for k in ("slackName", "githubAuthor", "jiraName") if v.get(k)) >= 2][:10]


# ---------------- Static system prefix ----------------

STATIC_PREFIX = """You are Mycelium, an AI company intelligence assistant.

You have access to real-time data about the engineering organization: repos, commits, contributors, pull requests, issues, Slack messages, and Jira tickets.

Be specific - use real repo names, real contributor names, real commit messages, real channel names, real ticket keys. When asked about the most recent message, summarize the SUBSTANTIVE conversation - skip filler like single characters or test messages. When asked who's working on what, combine commit authors with Jira assignees. Format multi-item answers as short bullets. Don't add sections the user didn't ask about.

---LIVE DATA---"""


class IntelChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    save_history: bool = True
    conversation_id: str | None = None


@router.post("/intel")
async def chat_intel(req: IntelChatRequest, user: SupabaseUser = Depends(get_supabase_user)):
    await _ensure_transcripts_table()
    user_query = req.messages[-1].get("content", "") if req.messages else ""
    wants_images = bool(VISION_KEYWORDS.search(user_query))

    # Save user message to chat_history before streaming the answer
    if req.save_history and req.messages:
        try:
            sb = service_client()
            row: dict[str, Any] = {"user_id": user.id, "role": "user", "content": user_query}
            if req.conversation_id:
                row["conversation_id"] = req.conversation_id
            sb.table("chat_history").insert(row).execute()
        except Exception:
            pass

    async with httpx.AsyncClient() as client:
        slack, gh, jira = await asyncio.gather(
            fetch_slack(client),
            fetch_github(client, None),
            fetch_jira(client),
        )

        slack_msgs = slack["messages"]

        # Transcripts (audio/video)
        av_files = []
        for m in slack_msgs:
            for f in m.get("files") or []:
                mt = f.get("mimetype") or ""
                if (mt.startswith("audio/") or mt.startswith("video/")) and f.get("url_private") and f.get("id"):
                    av_files.append({"file_id": f["id"], "channel": m["channel"], "user": m["user"], "name": f["name"], "mimetype": mt, "url": f["url_private"]})
                    if len(av_files) >= 4:
                        break
            if len(av_files) >= 4:
                break
        transcripts = await asyncio.gather(*[
            transcribe_slack_file(client, f["file_id"], f["url"], f["name"], f["mimetype"]) for f in av_files
        ]) if av_files else []
        valid_transcripts = [(av_files[i], t) for i, t in enumerate(transcripts) if t]

        # Images (only if query mentions visuals)
        valid_images = []
        if wants_images:
            img_files = []
            for m in slack_msgs:
                for f in m.get("files") or []:
                    if (f.get("mimetype") or "").startswith("image/") and f.get("url_private"):
                        img_files.append({"channel": m["channel"], "user": m["user"], "name": f["name"], "url": f["url_private"]})
                        if len(img_files) >= 4:
                            break
                if len(img_files) >= 4:
                    break
            urls = await asyncio.gather(*[download_slack_image(client, f["url"]) for f in img_files])
            valid_images = [(img_files[i], u) for i, u in enumerate(urls) if u]

    # Build prompt sections
    repos_block = "\n".join(f"{r['owner']}/{r['name']} ({r.get('language') or '?'}) - {r.get('description') or ''}" for r in gh["repos"]) or "(none)"
    commits_block = "\n".join(f"{c['repo']}: {(c['message'] or '')[:80]} - {c.get('author')}" for c in gh["commits"]) or "(none)"
    prs_block = "\n".join(f"{p['repo']}#{p['number']} [{('merged' if p['merged'] else p['state'])}] {p['title']} - {p['author']}" for p in gh["prs"]) or "(none)"
    issues_block = "\n".join(f"{i['repo']}#{i['number']} [{i['state']}] {i['title']}{(' (assigned: '+i['assignee']+')') if i.get('assignee') else ''}" for i in gh["issues"]) or "(none)"

    def _slack_line(m):
        reply = " (reply)" if m.get("thread_ts") and m["thread_ts"] != m.get("ts") else ""
        text = (m.get("text") or "")[:120]
        files = f" [{len(m['files'])} file(s)]" if m.get("files") else ""
        return f"#{m['channel']} <{m['user']}>{reply}: {text}{files}"

    # Skip ONLY join/leave filler (not real human messages).
    # Slack returns messages newest-first, so slack_msgs[0] = most recent.
    JOIN_RE = re.compile(r"(joined #|has joined|<@.+> joined)", re.I)
    real_msgs = [
        m for m in slack_msgs
        if (m.get("text") or "").strip()
        and not JOIN_RE.search(m.get("text") or "")
    ]
    slack_block = "\n".join(_slack_line(m) for m in real_msgs[:20]) or "(no messages)"

    jira_block = "\n".join(f"{j['key']} [{j['status']}] {j.get('priority') or ''} {j.get('type') or ''}: {j['summary']} ({j['assignee']})" for j in jira[:12]) or "(none)"

    transcripts_block = "\n\n".join(f"#{f['channel']} <{f['user']}> \"{f['name']}\":\n\"{t}\"" for f, t in valid_transcripts) or "(none)"

    live_data = f"""
REPOS:
{repos_block}

PULL REQUESTS:
{prs_block}

ISSUES:
{issues_block}

COMMITS:
{commits_block}

SLACK MESSAGES (newest first — first line is the most recent):
{slack_block}

SLACK AUDIO/VIDEO TRANSCRIPTS:
{transcripts_block}

JIRA ISSUES:
{jira_block}"""

    chat_messages: list[dict[str, Any]] = [{"role": "system", "content": STATIC_PREFIX + live_data}]

    if valid_images:
        content = [{"type": "text", "text": "Images recently shared in Slack:\n" + "\n".join(f"- #{f['channel']} <{f['user']}>: {f['name']}" for f, _ in valid_images)}]
        for _, url in valid_images:
            content.append({"type": "image_url", "image_url": {"url": url, "detail": "low"}})
        chat_messages.append({"role": "user", "content": content})
        chat_messages.append({"role": "assistant", "content": "Got it, I have reviewed those images."})

    chat_messages.extend(req.messages)

    use_mini = not wants_images and not valid_images
    model = "gpt-4o-mini" if use_mini else "gpt-4o"

    async def gen():
        full = ""
        try:
            stream = await _openai.chat.completions.create(
                model=model,
                stream=True,
                max_tokens=700,
                messages=chat_messages,
            )
            async for chunk in stream:
                txt = (chunk.choices[0].delta.content or "") if chunk.choices else ""
                if txt:
                    full += txt
                    yield txt
        except Exception as e:
            yield f"\n[error: {e}]"
        finally:
            if req.save_history and full:
                try:
                    sb = service_client()
                    row: dict[str, Any] = {"user_id": user.id, "role": "assistant", "content": full}
                    if req.conversation_id:
                        row["conversation_id"] = req.conversation_id
                    sb.table("chat_history").insert(row).execute()
                except Exception:
                    pass

    return StreamingResponse(gen(), media_type="text/plain", headers={"X-Mycelium-Model": model})


@router.get("/insights")
async def insights_endpoint(user: SupabaseUser = Depends(get_supabase_user)):
    """Generates 5 bulletin-style insights from live data."""
    cached = _cache_get("insights", 900)
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        gh, slack, jira, observer = await asyncio.gather(
            fetch_github(client), fetch_slack(client), fetch_jira(client), fetch_observer_events()
        )

    summary = {
        "commits": gh["commits"][:15],
        "prs": gh["prs"][:10],
        "slack": [{"channel": m["channel"], "user": m["user"], "text": (m["text"] or "")[:120]} for m in slack["messages"][:15]],
        "jira": jira[:10],
        "observer": observer[:10],
    }

    try:
        resp = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            max_tokens=600,
            messages=[
                {"role": "system", "content": "You are a company intelligence system. Return only JSON."},
                {"role": "user", "content": (
                    "Analyze this engineering org data and return exactly 5 insights as JSON: "
                    "{\"insights\": [{\"type\": \"alert\"|\"warning\"|\"info\", \"title\": \"short\", \"description\": \"1-2 sentences\"}]}\n\n"
                    + json.dumps(summary)
                )},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        parsed = json.loads(content)
        insights = parsed.get("insights", [])
    except Exception as e:
        logger.warning("insights gen failed: %s", e)
        insights = [{"type": "info", "title": "Insights unavailable", "description": str(e)[:200]}]

    _cache_set("insights", insights)
    return insights
