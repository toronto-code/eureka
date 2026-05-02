"""Permission rules and types for agent actions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Any


class ActionType(str, Enum):
    """Types of actions an agent can perform."""

    SHELL_COMMAND = "shell_command"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    GIT_READ = "git_read"
    GIT_WRITE = "git_write"
    HTTP_REQUEST = "http_request"
    CODE_EXECUTION = "code_execution"


class PermissionLevel(str, Enum):
    """Permission levels for actions."""

    AUTO = "auto"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


@dataclass
class PermissionDecision:
    """Result of a permission check."""

    level: PermissionLevel
    reason: str
    matched_rule: PermissionRule | None = None

    @property
    def is_allowed(self) -> bool:
        return self.level == PermissionLevel.AUTO

    @property
    def needs_approval(self) -> bool:
        return self.level == PermissionLevel.REQUIRES_APPROVAL

    @property
    def is_blocked(self) -> bool:
        return self.level == PermissionLevel.BLOCKED


@dataclass
class PermissionRule:
    """A rule that determines permission level for an action.

    Rules can match on:
    - action_type: The type of action (required)
    - command_pattern: Regex pattern for shell commands
    - path_pattern: Glob pattern for file paths
    - url_pattern: Regex pattern for HTTP URLs
    - custom_matcher: Callable for complex matching logic
    """

    name: str
    action_type: ActionType
    level: PermissionLevel
    description: str = ""
    command_pattern: str | None = None
    path_pattern: str | None = None
    url_pattern: str | None = None
    priority: int = 0

    _compiled_command: re.Pattern[str] | None = field(
        default=None, init=False, repr=False
    )
    _compiled_url: re.Pattern[str] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.command_pattern:
            self._compiled_command = re.compile(self.command_pattern, re.IGNORECASE)
        if self.url_pattern:
            self._compiled_url = re.compile(self.url_pattern, re.IGNORECASE)

    def matches(self, action_type: ActionType, payload: dict[str, Any]) -> bool:
        """Check if this rule matches the given action."""
        if action_type != self.action_type:
            return False

        if self.command_pattern and action_type == ActionType.SHELL_COMMAND:
            command = payload.get("command", "")
            if not self._compiled_command or not self._compiled_command.search(command):
                return False

        if self.path_pattern and action_type in (
            ActionType.FILE_READ,
            ActionType.FILE_WRITE,
            ActionType.FILE_DELETE,
        ):
            path = payload.get("path", "")
            if not fnmatch(path, self.path_pattern):
                return False

        if self.url_pattern and action_type == ActionType.HTTP_REQUEST:
            url = payload.get("url", "")
            if not self._compiled_url or not self._compiled_url.search(url):
                return False

        return True
