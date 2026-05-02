"""Git operations skill - version control through permission guard."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.actions.types import Action
from mycelium_agent_runtime.permissions.rules import ActionType
from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


class GitSkill(BaseSkill):
    """Git operations with permission-based access control.

    Read operations (status, log, diff, etc.) are auto-approved.
    Write operations (commit, push, etc.) require approval.

    Input data:
        - operation: Git operation to perform
        - args: Additional arguments for the operation
        - reasoning: Why this operation is being performed

    Operations:
        Read (auto): status, log, diff, show, branch, remote, blame, ls-files
        Write (approval): add, commit, push, pull, checkout, merge, rebase, etc.
    """

    name = "git"
    description = "Git version control operations"
    required_capabilities = [ActionType.GIT_READ, ActionType.GIT_WRITE]

    READ_OPERATIONS = {
        "status", "log", "diff", "show", "branch", "remote", "blame",
        "ls-files", "ls-tree", "rev-parse", "describe", "shortlog",
        "stash list", "tag", "config --list", "config -l",
    }

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        operation = input_data.get("operation", "status")
        args = input_data.get("args", "")
        reasoning = input_data.get("reasoning", f"Git {operation}")

        command = f"git {operation}"
        if args:
            command = f"{command} {args}"

        is_read = any(
            operation.startswith(read_op)
            for read_op in self.READ_OPERATIONS
        )

        if is_read:
            action = Action.git_read(command=command, reasoning=reasoning)
        else:
            action = Action.git_write(command=command, reasoning=reasoning)

        result = await executor.execute(action)

        return {
            "success": result.success,
            "operation": operation,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code,
            "is_read_operation": is_read,
            "pending_approval": result.metadata.get("pending_approval", False),
        }


class GitStatusSkill(BaseSkill):
    """Quick git status check."""

    name = "git_status"
    description = "Check git repository status"
    required_capabilities = [ActionType.GIT_READ]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        reasoning = input_data.get("reasoning", "Check git status")

        action = Action.git_read(command="git status --porcelain", reasoning=reasoning)
        result = await executor.execute(action)

        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "is_repo": False,
            }

        lines = (result.output or "").strip().split("\n") if result.output else []
        changes = []

        for line in lines:
            if not line:
                continue
            status = line[:2]
            path = line[3:]
            changes.append({
                "status": status,
                "path": path,
                "staged": status[0] != " " and status[0] != "?",
                "modified": status[1] != " ",
            })

        return {
            "success": True,
            "is_repo": True,
            "clean": len(changes) == 0,
            "changes": changes,
            "summary": {
                "total": len(changes),
                "staged": sum(1 for c in changes if c["staged"]),
                "unstaged": sum(1 for c in changes if c["modified"]),
                "untracked": sum(1 for c in changes if c["status"] == "??"),
            },
        }


class GitCommitSkill(BaseSkill):
    """Create a git commit (requires approval)."""

    name = "git_commit"
    description = "Stage and commit changes"
    required_capabilities = [ActionType.GIT_WRITE]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        message = input_data.get("message")
        if not message:
            return {"error": "Commit message required", "success": False}

        files = input_data.get("files", [])
        all_files = input_data.get("all", False)
        reasoning = input_data.get("reasoning", f"Commit: {message[:50]}")

        results = []

        if files:
            for f in files:
                action = Action.git_write(command=f"git add {f}", reasoning=reasoning)
                result = await executor.execute(action)
                results.append({"action": f"add {f}", "success": result.success})
                if not result.success:
                    return {
                        "success": False,
                        "error": f"Failed to stage {f}: {result.error}",
                        "results": results,
                    }
        elif all_files:
            action = Action.git_write(command="git add -A", reasoning=reasoning)
            result = await executor.execute(action)
            results.append({"action": "add -A", "success": result.success})
            if not result.success:
                return {
                    "success": False,
                    "error": f"Failed to stage all: {result.error}",
                    "results": results,
                }

        escaped_message = message.replace('"', '\\"')
        action = Action.git_write(
            command=f'git commit -m "{escaped_message}"',
            reasoning=reasoning,
        )
        result = await executor.execute(action)
        results.append({"action": "commit", "success": result.success})

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "results": results,
            "pending_approval": result.metadata.get("pending_approval", False),
        }


class GitDiffSkill(BaseSkill):
    """Show git diff."""

    name = "git_diff"
    description = "Show changes between commits, commit and working tree, etc."
    required_capabilities = [ActionType.GIT_READ]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        target = input_data.get("target", "")
        staged = input_data.get("staged", False)
        stat_only = input_data.get("stat_only", False)
        reasoning = input_data.get("reasoning", "Show git diff")

        command = "git diff"
        if staged:
            command += " --staged"
        if stat_only:
            command += " --stat"
        if target:
            command += f" {target}"

        action = Action.git_read(command=command, reasoning=reasoning)
        result = await executor.execute(action)

        return {
            "success": result.success,
            "diff": result.output,
            "error": result.error,
        }
