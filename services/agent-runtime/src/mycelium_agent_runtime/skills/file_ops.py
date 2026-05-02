"""File operations skill - read, write, delete files through permission guard."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.actions.types import Action
from mycelium_agent_runtime.permissions.rules import ActionType
from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


class FileReadSkill(BaseSkill):
    """Read file contents.

    Input data:
        - path: Path to the file to read
        - reasoning: Why this file is being read

    Returns:
        - content: File contents
        - path: Absolute path that was read
        - size: File size in bytes
    """

    name = "file_read"
    description = "Read file contents with permission checking"
    required_capabilities = [ActionType.FILE_READ]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        path = input_data.get("path")
        if not path:
            return {"error": "No path provided", "success": False}

        reasoning = input_data.get("reasoning", f"Read file: {path}")

        action = Action.file_read(path=path, reasoning=reasoning)
        result = await executor.execute(action)

        return {
            "success": result.success,
            "content": result.output,
            "path": result.metadata.get("path"),
            "size": result.metadata.get("size"),
            "error": result.error,
            "blocked": result.metadata.get("blocked", False),
        }


class FileWriteSkill(BaseSkill):
    """Write content to a file.

    Input data:
        - path: Path to the file to write
        - content: Content to write
        - reasoning: Why this file is being written

    Returns:
        - path: Path that was written
        - size: Bytes written
    """

    name = "file_write"
    description = "Write content to files with permission checking"
    required_capabilities = [ActionType.FILE_WRITE]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        path = input_data.get("path")
        content = input_data.get("content")

        if not path:
            return {"error": "No path provided", "success": False}
        if content is None:
            return {"error": "No content provided", "success": False}

        reasoning = input_data.get("reasoning", f"Write file: {path}")

        action = Action.file_write(path=path, content=content, reasoning=reasoning)
        result = await executor.execute(action)

        return {
            "success": result.success,
            "output": result.output,
            "path": result.metadata.get("path"),
            "size": result.metadata.get("size"),
            "error": result.error,
            "pending_approval": result.metadata.get("pending_approval", False),
        }


class FileDeleteSkill(BaseSkill):
    """Delete a file.

    Input data:
        - path: Path to the file to delete
        - reasoning: Why this file is being deleted

    Returns:
        - path: Path that was deleted
    """

    name = "file_delete"
    description = "Delete files with permission checking"
    required_capabilities = [ActionType.FILE_DELETE]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        path = input_data.get("path")
        if not path:
            return {"error": "No path provided", "success": False}

        reasoning = input_data.get("reasoning", f"Delete file: {path}")

        action = Action.file_delete(path=path, reasoning=reasoning)
        result = await executor.execute(action)

        return {
            "success": result.success,
            "output": result.output,
            "path": result.metadata.get("path"),
            "error": result.error,
            "pending_approval": result.metadata.get("pending_approval", False),
        }


class FileOpsSkill(BaseSkill):
    """Combined file operations - read, write, delete, list, search.

    Input data:
        - operation: "read" | "write" | "delete" | "list" | "search"
        - path: File or directory path
        - content: Content for write operations
        - pattern: Search pattern for search operations
        - reasoning: Why this operation is being performed

    Returns:
        Operation-specific results
    """

    name = "file_ops"
    description = "File operations (read, write, delete, list, search)"
    required_capabilities = [ActionType.FILE_READ, ActionType.FILE_WRITE, ActionType.FILE_DELETE]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        operation = input_data.get("operation", "read")
        path = input_data.get("path")
        reasoning = input_data.get("reasoning", f"File operation: {operation}")

        if not path and operation != "search":
            return {"error": "No path provided", "success": False}

        if operation == "read":
            action = Action.file_read(path=path, reasoning=reasoning)
        elif operation == "write":
            content = input_data.get("content", "")
            action = Action.file_write(path=path, content=content, reasoning=reasoning)
        elif operation == "delete":
            action = Action.file_delete(path=path, reasoning=reasoning)
        elif operation == "list":
            action = Action.shell(
                command=f"ls -la {path}",
                reasoning=reasoning,
            )
        elif operation == "search":
            pattern = input_data.get("pattern", "")
            search_path = path or "."
            action = Action.shell(
                command=f"find {search_path} -name '{pattern}' 2>/dev/null | head -100",
                reasoning=reasoning,
            )
        else:
            return {"error": f"Unknown operation: {operation}", "success": False}

        result = await executor.execute(action)

        return {
            "success": result.success,
            "operation": operation,
            "output": result.output,
            "error": result.error,
            "metadata": result.metadata,
        }
