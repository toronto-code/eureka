"""Docker-level observability endpoints.

Talks to the Docker daemon via the mounted /var/run/docker.sock. Surfaces:

- GET  /observability/docker/services    — live container snapshot (status, image, ports, uptime)
- GET  /observability/docker/stats       — CPU%, mem%, network, blkio per container
- GET  /observability/docker/logs/{name} — recent log tail for one service
- GET  /observability/docker/events      — last N container events (start/stop/restart/oom/health)
- GET  /observability/docker/health      — combined healthcheck across the stack
- GET  /observability/docker/stream      — SSE stream of live docker events

Used by:
- The chat context (so the model can answer "is anything failing?")
- The frontend Observability dashboard view
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any

import docker
from docker.errors import DockerException
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.supabase_client import SupabaseUser, get_supabase_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/observability/docker", tags=["docker-obs"])

_client: docker.DockerClient | None = None
_recent_events: deque[dict[str, Any]] = deque(maxlen=200)
_event_subscribers: list[asyncio.Queue] = []
_event_task: asyncio.Task | None = None


def _docker() -> docker.DockerClient:
    global _client
    if _client is None:
        try:
            _client = docker.from_env()
        except DockerException as e:
            raise HTTPException(503, f"docker socket unavailable: {e}")
    return _client


def _calc_cpu_percent(stats: dict) -> float:
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        cpu_total = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        precpu_total = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        cpu_delta = cpu_total - precpu_total
        sys_total = cpu_stats.get("system_cpu_usage", 0)
        presys_total = precpu_stats.get("system_cpu_usage", 0)
        sys_delta = sys_total - presys_total
        online = cpu_stats.get("online_cpus") or len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []) or []) or 1
        if sys_delta > 0 and cpu_delta > 0:
            return round((cpu_delta / sys_delta) * online * 100, 2)
    except Exception:
        pass
    return 0.0


def _calc_mem_percent(stats: dict) -> tuple[float, int, int]:
    try:
        mem = stats.get("memory_stats", {})
        usage = mem.get("usage", 0)
        cache = (mem.get("stats") or {}).get("cache", 0) or (mem.get("stats") or {}).get("inactive_file", 0)
        used = max(usage - cache, 0)
        limit = mem.get("limit", 1) or 1
        return round((used / limit) * 100, 2), used, limit
    except Exception:
        return 0.0, 0, 0


async def _run(fn, *args):
    return await asyncio.get_event_loop().run_in_executor(None, fn, *args)


def _list_services_sync():
    client = _docker()
    out = []
    for c in client.containers.list(all=True):
        attrs = c.attrs
        state = attrs.get("State", {})
        cfg = attrs.get("Config", {})
        net = attrs.get("NetworkSettings", {}) or {}
        out.append({
            "name": c.name,
            "service": (cfg.get("Labels") or {}).get("com.docker.compose.service") or c.name,
            "project": (cfg.get("Labels") or {}).get("com.docker.compose.project"),
            "image": cfg.get("Image"),
            "status": c.status,
            "state": state.get("Status"),
            "health": (state.get("Health") or {}).get("Status"),
            "started_at": state.get("StartedAt"),
            "exit_code": state.get("ExitCode"),
            "restart_count": attrs.get("RestartCount", 0),
            "ports": [
                f"{host['HostPort']}->{port}" for port, hosts in (net.get("Ports") or {}).items() if hosts for host in hosts
            ],
        })
    return out


def _stats_sync():
    client = _docker()
    out = []
    for c in client.containers.list():
        try:
            s = c.stats(stream=False)
            cpu = _calc_cpu_percent(s)
            mem_pct, mem_used, mem_limit = _calc_mem_percent(s)
            networks = s.get("networks") or {}
            rx = sum(n.get("rx_bytes", 0) for n in networks.values())
            tx = sum(n.get("tx_bytes", 0) for n in networks.values())
            blk = (s.get("blkio_stats", {}) or {}).get("io_service_bytes_recursive") or []
            read_bytes = sum(b.get("value", 0) for b in blk if b.get("op", "").lower() == "read")
            write_bytes = sum(b.get("value", 0) for b in blk if b.get("op", "").lower() == "write")
            out.append({
                "name": c.name,
                "cpu_percent": cpu,
                "mem_percent": mem_pct,
                "mem_used_mb": round(mem_used / 1024 / 1024, 1),
                "mem_limit_mb": round(mem_limit / 1024 / 1024, 1),
                "net_rx_kb": round(rx / 1024, 1),
                "net_tx_kb": round(tx / 1024, 1),
                "blk_read_mb": round(read_bytes / 1024 / 1024, 1),
                "blk_write_mb": round(write_bytes / 1024 / 1024, 1),
            })
        except Exception as e:
            out.append({"name": c.name, "error": str(e)})
    return out


def _logs_sync(name: str, lines: int):
    client = _docker()
    c = client.containers.get(name)
    raw = c.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
    return [l for l in raw.splitlines() if l]


def _health_sync():
    client = _docker()
    services = []
    healthy = unhealthy = 0
    for c in client.containers.list(all=True):
        state = (c.attrs.get("State") or {})
        h = (state.get("Health") or {}).get("Status")
        running = state.get("Status") == "running"
        ok = (h == "healthy") if h else running
        services.append({
            "name": c.name,
            "running": running,
            "health": h or ("running" if running else state.get("Status")),
            "ok": ok,
        })
        if ok:
            healthy += 1
        else:
            unhealthy += 1
    return {"healthy": healthy, "unhealthy": unhealthy, "total": healthy + unhealthy, "services": services, "checked_at": time.time()}


@router.get("/services")
async def list_services(user: SupabaseUser = Depends(get_supabase_user)):
    return await _run(_list_services_sync)


@router.get("/stats")
async def stats(user: SupabaseUser = Depends(get_supabase_user)):
    return await _run(_stats_sync)


@router.get("/logs/{name}")
async def container_logs(name: str, lines: int = 100, user: SupabaseUser = Depends(get_supabase_user)):
    try:
        result = await _run(_logs_sync, name, lines)
        return {"name": name, "lines": result}
    except docker.errors.NotFound:
        raise HTTPException(404, f"container {name} not found")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/events")
async def recent_events(user: SupabaseUser = Depends(get_supabase_user)):
    return list(_recent_events)


@router.get("/health")
async def stack_health(user: SupabaseUser = Depends(get_supabase_user)):
    return await _run(_health_sync)


def _consume_events_blocking(loop: asyncio.AbstractEventLoop):
    """Runs in a thread. Iterates the blocking docker events generator and
    schedules each event onto the asyncio loop."""
    try:
        client = _docker()
    except Exception as e:
        logger.warning("docker client init failed: %s", e)
        return
    try:
        for raw in client.events(decode=True):
            if raw.get("Type") not in ("container", "health_status"):
                continue
            evt = {
                "type": raw.get("Type"),
                "action": raw.get("Action"),
                "name": (raw.get("Actor") or {}).get("Attributes", {}).get("name"),
                "image": (raw.get("Actor") or {}).get("Attributes", {}).get("image"),
                "service": (raw.get("Actor") or {}).get("Attributes", {}).get("com.docker.compose.service"),
                "exit_code": (raw.get("Actor") or {}).get("Attributes", {}).get("exitCode"),
                "time": raw.get("time"),
            }
            loop.call_soon_threadsafe(_dispatch_event, evt)
    except Exception as e:
        logger.warning("docker event consumer crashed: %s", e)


def _dispatch_event(evt: dict):
    _recent_events.append(evt)
    dead = []
    for q in _event_subscribers:
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in _event_subscribers:
            _event_subscribers.remove(q)


async def _docker_event_loop():
    """Spawns the blocking consumer in a background thread, restarts on crash."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            await loop.run_in_executor(None, _consume_events_blocking, loop)
        except Exception as e:
            logger.warning("docker event loop error: %s", e)
        await asyncio.sleep(5)


def ensure_event_listener():
    global _event_task
    if _event_task is None or _event_task.done():
        try:
            _event_task = asyncio.get_event_loop().create_task(_docker_event_loop())
        except RuntimeError:
            pass


@router.get("/stream")
async def stream(user: SupabaseUser = Depends(get_supabase_user)):
    ensure_event_listener()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _event_subscribers.append(queue)

    async def gen():
        try:
            for evt in list(_recent_events)[-20:]:
                yield f"data: {json.dumps(evt)}\n\n"
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(evt)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            if queue in _event_subscribers:
                _event_subscribers.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")
