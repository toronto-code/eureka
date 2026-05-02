"""Local execution backend - runs actions in-process for dev/testing."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiofiles
import httpx

from mycelium_agent_runtime.actions.types import Action, ActionResult
from mycelium_agent_runtime.execution.result import ExecutionResult, ExecutionStatus
from mycelium_agent_runtime.permissions.rules import ActionType

logger = logging.getLogger(__name__)

MAX_OUTPUT_SIZE = 100 * 1024  # 100KB max output
DEFAULT_TIMEOUT = 30  # seconds


class LocalBackend:
    """Local execution backend for dev/testing.

    Executes actions in-process using asyncio subprocesses, aiofiles, etc.
    Includes safety measures like timeouts and output truncation.
    """

    def __init__(
        self,
        working_directory: str | Path | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        allowed_paths: list[str] | None = None,
    ) -> None:
        self._working_directory = Path(working_directory) if working_directory else Path.cwd()
        self._timeout = timeout
        self._allowed_paths = [Path(p).resolve() for p in (allowed_paths or [])]
        self._executions: dict[str, ExecutionStatus] = {}
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def close(self) -> None:
        """Close any open resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _is_path_allowed(self, path: str | Path) -> bool:
        """Check if a path is within allowed directories."""
        if not self._allowed_paths:
            return True

        resolved = Path(path).resolve()
        return any(
            resolved == allowed or allowed in resolved.parents
            for allowed in self._allowed_paths
        )

    def _truncate_output(self, output: str) -> str:
        """Truncate output if too large."""
        if len(output) > MAX_OUTPUT_SIZE:
            return output[:MAX_OUTPUT_SIZE] + f"\n... (truncated, {len(output)} bytes total)"
        return output

    async def execute_task(
        self, task: Any, context: dict
    ) -> ExecutionResult:
        """Execute an entire agent task.

        For local backend, this is a simple wrapper that marks execution complete.
        Real execution happens through execute_action called by skills.
        """
        execution_id = str(uuid4())
        self._executions[execution_id] = ExecutionStatus.RUNNING
        start_time = time.time()

        try:
            self._executions[execution_id] = ExecutionStatus.SUCCEEDED
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult.success(
                execution_id=execution_id,
                result={"task_id": task.task_id if hasattr(task, "task_id") else str(task)},
                duration_ms=duration_ms,
            )
        except Exception as e:
            self._executions[execution_id] = ExecutionStatus.FAILED
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult.failure(
                execution_id=execution_id,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def execute_action(self, action: Action) -> ActionResult:
        """Execute a single action."""
        start_time = time.time()

        try:
            if action.type == ActionType.SHELL_COMMAND:
                result = await self._execute_shell(action)
            elif action.type == ActionType.FILE_READ:
                result = await self._execute_file_read(action)
            elif action.type == ActionType.FILE_WRITE:
                result = await self._execute_file_write(action)
            elif action.type == ActionType.FILE_DELETE:
                result = await self._execute_file_delete(action)
            elif action.type in (ActionType.GIT_READ, ActionType.GIT_WRITE):
                result = await self._execute_git(action)
            elif action.type == ActionType.HTTP_REQUEST:
                result = await self._execute_http(action)
            elif action.type == ActionType.CODE_EXECUTION:
                result = await self._execute_code(action)
            else:
                result = ActionResult.failure(
                    action.id,
                    f"Unknown action type: {action.type}",
                )

            duration_ms = int((time.time() - start_time) * 1000)
            result.duration_ms = duration_ms
            return result

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            return ActionResult.failure(
                action.id,
                f"Action timed out after {self._timeout}s",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception("Action execution error: %s", e)
            return ActionResult.failure(
                action.id,
                str(e),
                duration_ms=duration_ms,
            )

    async def _execute_shell(self, action: Action) -> ActionResult:
        """Execute a shell command."""
        command = action.payload.get("command", "")
        cwd = action.payload.get("cwd", str(self._working_directory))
        env = action.payload.get("env")

        if env:
            full_env = {**os.environ, **env}
        else:
            full_env = None

        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=full_env,
                ),
                timeout=self._timeout,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout,
            )

            exit_code = process.returncode or 0
            stdout_str = self._truncate_output(stdout.decode("utf-8", errors="replace"))
            stderr_str = self._truncate_output(stderr.decode("utf-8", errors="replace"))

            if exit_code == 0:
                output = stdout_str
                if stderr_str:
                    output += f"\n[stderr]\n{stderr_str}"
                return ActionResult.success(
                    action.id,
                    output=output,
                    exit_code=exit_code,
                    command=command,
                )
            else:
                error = stderr_str or stdout_str or f"Command exited with code {exit_code}"
                return ActionResult.failure(
                    action.id,
                    error=error,
                    exit_code=exit_code,
                    command=command,
                )

        except asyncio.TimeoutError:
            return ActionResult.failure(
                action.id,
                f"Command timed out after {self._timeout}s",
                command=command,
            )

    async def _execute_file_read(self, action: Action) -> ActionResult:
        """Read a file."""
        path = Path(action.payload.get("path", ""))

        if not path.is_absolute():
            path = self._working_directory / path

        if not self._is_path_allowed(path):
            return ActionResult.failure(
                action.id,
                f"Path not allowed: {path}",
            )

        if not path.exists():
            return ActionResult.failure(
                action.id,
                f"File not found: {path}",
            )

        if not path.is_file():
            return ActionResult.failure(
                action.id,
                f"Not a file: {path}",
            )

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()

            content = self._truncate_output(content)
            return ActionResult.success(
                action.id,
                output=content,
                path=str(path),
                size=len(content),
            )
        except UnicodeDecodeError:
            return ActionResult.failure(
                action.id,
                f"Cannot read binary file: {path}",
            )

    async def _execute_file_write(self, action: Action) -> ActionResult:
        """Write a file."""
        path = Path(action.payload.get("path", ""))
        content = action.payload.get("content", "")

        if not path.is_absolute():
            path = self._working_directory / path

        if not self._is_path_allowed(path):
            return ActionResult.failure(
                action.id,
                f"Path not allowed: {path}",
            )

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)

            return ActionResult.success(
                action.id,
                output=f"Wrote {len(content)} bytes to {path}",
                path=str(path),
                size=len(content),
            )
        except Exception as e:
            return ActionResult.failure(
                action.id,
                f"Failed to write file: {e}",
            )

    async def _execute_file_delete(self, action: Action) -> ActionResult:
        """Delete a file."""
        path = Path(action.payload.get("path", ""))

        if not path.is_absolute():
            path = self._working_directory / path

        if not self._is_path_allowed(path):
            return ActionResult.failure(
                action.id,
                f"Path not allowed: {path}",
            )

        if not path.exists():
            return ActionResult.failure(
                action.id,
                f"File not found: {path}",
            )

        try:
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()

            return ActionResult.success(
                action.id,
                output=f"Deleted: {path}",
                path=str(path),
            )
        except Exception as e:
            return ActionResult.failure(
                action.id,
                f"Failed to delete: {e}",
            )

    async def _execute_git(self, action: Action) -> ActionResult:
        """Execute a git command."""
        command = action.payload.get("command", "")

        if not command.startswith("git "):
            command = f"git {command}"

        git_action = Action.shell(
            command=command,
            reasoning=action.reasoning,
            cwd=str(self._working_directory),
        )
        git_action.id = action.id

        return await self._execute_shell(git_action)

    async def _execute_http(self, action: Action) -> ActionResult:
        """Execute an HTTP request."""
        method = action.payload.get("method", "GET").upper()
        url = action.payload.get("url", "")
        headers = action.payload.get("headers", {})
        body = action.payload.get("body")

        if not url:
            return ActionResult.failure(
                action.id,
                "URL is required for HTTP requests",
            )

        try:
            client = await self._get_http_client()

            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=body)
            elif method == "PUT":
                response = await client.put(url, headers=headers, json=body)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=body)
            else:
                return ActionResult.failure(
                    action.id,
                    f"Unsupported HTTP method: {method}",
                )

            content = self._truncate_output(response.text)

            if response.is_success:
                return ActionResult.success(
                    action.id,
                    output=content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
            else:
                return ActionResult.failure(
                    action.id,
                    f"HTTP {response.status_code}: {content}",
                    status_code=response.status_code,
                )

        except httpx.RequestError as e:
            return ActionResult.failure(
                action.id,
                f"HTTP request failed: {e}",
            )

    async def _execute_code(self, action: Action) -> ActionResult:
        """Execute code (Python for now)."""
        code = action.payload.get("code", "")
        language = action.payload.get("language", "python")

        if language != "python":
            return ActionResult.failure(
                action.id,
                f"Unsupported language: {language}",
            )

        shell_action = Action.shell(
            command=f'python3 -c "{code}"',
            reasoning=action.reasoning,
            cwd=str(self._working_directory),
        )
        shell_action.id = action.id

        return await self._execute_shell(shell_action)

    async def get_status(self, execution_id: str) -> ExecutionStatus:
        """Get the status of an execution."""
        return self._executions.get(execution_id, ExecutionStatus.PENDING)

    async def cancel(self, execution_id: str) -> bool:
        """Cancel an execution."""
        if execution_id not in self._executions:
            return False

        if self._executions[execution_id] in (
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ):
            return False

        self._executions[execution_id] = ExecutionStatus.CANCELLED
        return True
