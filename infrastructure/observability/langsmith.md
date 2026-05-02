# LangSmith

LangSmith is used for agent / LLM call tracing. Enable it by setting:

```
LANGSMITH_API_KEY=<your-key>
LANGSMITH_PROJECT=mycelium-dev
LANGSMITH_TRACING=true
```

In `services/agent-runtime`, wrap each skill invocation with the LangSmith
context manager. The skill-registry stub is a deliberate placeholder so the
LLM provider call site is obvious.

In production, run a small sidecar that forwards `agents.results` summaries
to LangSmith for offline analysis. We don't ship that today.
