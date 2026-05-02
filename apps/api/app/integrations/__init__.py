"""Third-party integration clients (Jira, GitHub).

Each module exposes a typed client whose constructor reads env vars. When
credentials are missing, clients fall back to seeded fixtures so the local
demo runs without external services.
"""

from app.integrations.github import GitHubClient, get_github_client
from app.integrations.jira import JiraClient, get_jira_client

__all__ = ["GitHubClient", "JiraClient", "get_github_client", "get_jira_client"]
