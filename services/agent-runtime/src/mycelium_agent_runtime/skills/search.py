"""Search skills - grep, find, and semantic search."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mycelium_agent_runtime.actions.types import Action
from mycelium_agent_runtime.permissions.rules import ActionType
from mycelium_agent_runtime.skills.base import BaseSkill

if TYPE_CHECKING:
    from mycelium_agent_runtime.actions.executor import ActionExecutor


class GrepSkill(BaseSkill):
    """Search file contents using grep/ripgrep.

    Input data:
        - pattern: Search pattern (regex)
        - path: Directory or file to search (default: .)
        - case_sensitive: Whether search is case-sensitive (default: False)
        - whole_word: Match whole words only (default: False)
        - context_lines: Lines of context around matches (default: 0)
        - file_pattern: File glob pattern to filter (e.g., "*.py")
        - reasoning: Why this search is being performed

    Returns:
        - matches: List of matches with file, line, content
        - total_matches: Total number of matches
    """

    name = "grep"
    description = "Search file contents using grep/ripgrep"
    required_capabilities = [ActionType.SHELL_COMMAND]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        pattern = input_data.get("pattern")
        if not pattern:
            return {"error": "No pattern provided", "success": False}

        path = input_data.get("path", ".")
        case_sensitive = input_data.get("case_sensitive", False)
        whole_word = input_data.get("whole_word", False)
        context_lines = input_data.get("context_lines", 0)
        file_pattern = input_data.get("file_pattern")
        reasoning = input_data.get("reasoning", f"Search for: {pattern[:30]}")

        cmd = "rg --json"

        if not case_sensitive:
            cmd += " -i"
        if whole_word:
            cmd += " -w"
        if context_lines > 0:
            cmd += f" -C {context_lines}"
        if file_pattern:
            cmd += f" -g '{file_pattern}'"

        cmd += f" '{pattern}' {path}"

        action = Action.shell(command=cmd, reasoning=reasoning)
        result = await executor.execute(action)

        if not result.success and result.exit_code == 1:
            return {
                "success": True,
                "matches": [],
                "total_matches": 0,
                "message": "No matches found",
            }

        if not result.success:
            cmd_fallback = f"grep -rn"
            if not case_sensitive:
                cmd_fallback += " -i"
            cmd_fallback += f" '{pattern}' {path} 2>/dev/null | head -100"

            action = Action.shell(command=cmd_fallback, reasoning=reasoning)
            result = await executor.execute(action)

        matches = []
        if result.output:
            for line in result.output.strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({
                        "file": parts[0],
                        "line": parts[1],
                        "content": parts[2],
                    })
                elif len(parts) == 2:
                    matches.append({
                        "file": parts[0],
                        "line": "?",
                        "content": parts[1],
                    })

        return {
            "success": True,
            "matches": matches[:100],
            "total_matches": len(matches),
            "truncated": len(matches) > 100,
        }


class FindSkill(BaseSkill):
    """Find files by name or attributes.

    Input data:
        - name: File name pattern (glob)
        - path: Directory to search (default: .)
        - type: "f" for files, "d" for directories
        - max_depth: Maximum directory depth
        - size: Size filter (e.g., "+1M", "-100k")
        - modified: Modified time filter (e.g., "-1d", "+1w")
        - reasoning: Why this search is being performed

    Returns:
        - files: List of matching file paths
        - total: Total number of matches
    """

    name = "find"
    description = "Find files by name or attributes"
    required_capabilities = [ActionType.SHELL_COMMAND]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        name = input_data.get("name", "*")
        path = input_data.get("path", ".")
        file_type = input_data.get("type")
        max_depth = input_data.get("max_depth")
        reasoning = input_data.get("reasoning", f"Find files: {name}")

        if input_data.get("use_fd", True):
            cmd = f"fd '{name}' {path}"
            if file_type == "f":
                cmd += " --type f"
            elif file_type == "d":
                cmd += " --type d"
            if max_depth:
                cmd += f" --max-depth {max_depth}"
        else:
            cmd = f"find {path}"
            if max_depth:
                cmd += f" -maxdepth {max_depth}"
            if file_type:
                cmd += f" -type {file_type}"
            cmd += f" -name '{name}'"

        cmd += " 2>/dev/null | head -200"

        action = Action.shell(command=cmd, reasoning=reasoning)
        result = await executor.execute(action)

        files = []
        if result.output:
            files = [f for f in result.output.strip().split("\n") if f]

        return {
            "success": result.success or len(files) > 0,
            "files": files[:200],
            "total": len(files),
            "truncated": len(files) >= 200,
            "error": result.error if not result.success and not files else None,
        }


class SearchSkill(BaseSkill):
    """Combined search skill - grep for content, find for files.

    Input data:
        - query: Search query
        - type: "content" (grep) or "files" (find)
        - path: Directory to search
        - Additional type-specific options

    Returns:
        Type-specific results
    """

    name = "search"
    description = "Search for content or files"
    required_capabilities = [ActionType.SHELL_COMMAND]

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
        executor: ActionExecutor,
    ) -> dict[str, Any]:
        search_type = input_data.get("type", "content")
        query = input_data.get("query") or input_data.get("pattern") or input_data.get("name")

        if not query:
            return {"error": "No query provided", "success": False}

        if search_type == "content":
            skill = GrepSkill()
            return await skill.execute(
                {**input_data, "pattern": query},
                context,
                executor,
            )
        elif search_type == "files":
            skill = FindSkill()
            return await skill.execute(
                {**input_data, "name": query},
                context,
                executor,
            )
        else:
            return {"error": f"Unknown search type: {search_type}", "success": False}
