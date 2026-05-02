"""LLM clients for the agent runtime.

Exports both the legacy ``ClaudeClient`` / ``ClaudeResponse`` names and the
newer multi-provider ``LLMClient`` / ``LLMResponse``. They are the same
object; the Claude names are kept for backwards compatibility.
"""

from mycelium_agent_runtime.llm.claude import (
    ClaudeClient,
    ClaudeResponse,
    LLMClient,
    LLMResponse,
)

__all__ = [
    "ClaudeClient",
    "ClaudeResponse",
    "LLMClient",
    "LLMResponse",
]
