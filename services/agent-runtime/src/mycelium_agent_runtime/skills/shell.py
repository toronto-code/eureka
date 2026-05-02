"""Shell command skill - execute shell commands through permission guard."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.actions.types import Action
from mycelium_agent_runtime.permissions.rules import ActionType
from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


class ShellSkill(BaseSkill):
    """Execute shell commands with permission checking.

    Input data:
        - command: The shell command to execute
        - cwd: Optional working directory
        - env: Optional environment variables
        - reasoning: Why this command is being run

    Returns:
        - output: Command output (stdout)
        - exit_code: Command exit code
        - error: Error message if failed
    """

    name = "shell"
    description = "Execute shell commands with permission-based safety checks"
    required_capabilities = [ActionType.SHELL_COMMAND]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        command = input_data.get("command")
        if not command:
            return {"error": "No command provided", "success": False}

        reasoning = input_data.get("reasoning", f"Execute: {command[:50]}")
        cwd = input_data.get("cwd")
        env = input_data.get("env")

        action = Action.shell(
            command=command,
            reasoning=reasoning,
            cwd=cwd,
            env=env,
        )

        result = await executor.execute(action)

        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "blocked": result.metadata.get("blocked", False),
            "pending_approval": result.metadata.get("pending_approval", False),
        }


class MultiShellSkill(BaseSkill):
    """Execute multiple shell commands in sequence.

    Stops on first failure unless continue_on_error is True.

    Input data:
        - commands: List of commands to execute
        - cwd: Optional working directory (shared)
        - continue_on_error: Continue even if a command fails
        - reasoning: Why these commands are being run

    Returns:
        - results: List of results for each command
        - success: True if all commands succeeded
        - failed_at: Index of first failed command (if any)
    """

    name = "multi_shell"
    description = "Execute multiple shell commands in sequence"
    required_capabilities = [ActionType.SHELL_COMMAND]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        commands = input_data.get("commands", [])
        if not commands:
            return {"error": "No commands provided", "success": False}

        cwd = input_data.get("cwd")
        continue_on_error = input_data.get("continue_on_error", False)
        base_reasoning = input_data.get("reasoning", "Multi-command execution")

        results = []
        failed_at = None

        for i, cmd in enumerate(commands):
            action = Action.shell(
                command=cmd,
                reasoning=f"{base_reasoning} (step {i + 1}/{len(commands)})",
                cwd=cwd,
            )

            result = await executor.execute(action)
            results.append({
                "command": cmd,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "exit_code": result.exit_code,
            })

            if not result.success:
                if failed_at is None:
                    failed_at = i
                if not continue_on_error:
                    break

        return {
            "success": failed_at is None,
            "results": results,
            "failed_at": failed_at,
            "total_commands": len(commands),
            "executed_commands": len(results),
        }
