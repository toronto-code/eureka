interface Props {
  title: string;
  description?: string;
  hint?: string;
}

export function StubView({ title, description, hint }: Props) {
  return (
    <div style={{ padding: 32, color: "#e5e7eb", background: "#0a0a0a", height: "100%", overflow: "auto" }}>
      <header style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>{title}</h2>
        {description && <p style={{ fontSize: 13, color: "#9ca3af", marginTop: 6 }}>{description}</p>}
      </header>
      {hint && (
        <div
          style={{
            padding: 18,
            border: "1px dashed #374151",
            borderRadius: 8,
            background: "#0c0c0c",
            color: "#9ca3af",
            fontSize: 13,
            lineHeight: 1.6,
          }}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

export const Orchestrator = () => (
  <StubView
    title="Orchestrator"
    description="Multi-agent execution graph. Plan → run → observe."
    hint="The full orchestrator UI lives in apps/web (Next.js). This Vite shell links to it for layout parity. To use the real orchestrator, switch the running stack to docker-compose.yml (which serves apps/web) or open the same view at /ol in the Next.js app."
  />
);

export const Tasks = () => (
  <StubView
    title="Tasks"
    description="Agent task queue with status, output, and retries."
    hint="Real-time task data is in agent_actions in Supabase. The detailed task UI is in apps/web/app/tasks. This shell stub keeps the layout aligned with the Next.js app."
  />
);

export const Ingestion = () => (
  <StubView
    title="Ingestion"
    description="Upload and process raw event data into the knowledge graph."
    hint="Ingestion pipeline lives in apps/web/app/ingestion (Next.js). Use the Chat with agent mode to test the end-to-end pipeline interactively."
  />
);

export const OrchestrationLegacy = () => (
  <StubView
    title="Orchestration (legacy)"
    description="Older orchestration flow — kept for reference."
    hint="The legacy orchestration UI is in apps/web/app/orchestration. Prefer the new Orchestrator tab for current work."
  />
);

export const Settings = () => (
  <StubView
    title="Settings"
    description="Integration credentials, agent guardrails, allowlists."
    hint={
      "Current allowlist behavior is controlled via .env:\n" +
      "  • MYCELIUM_REPO_ALLOWLIST (empty = unrestricted)\n" +
      "  • MYCELIUM_SLACK_CHANNEL_ALLOWLIST\n" +
      "  • MYCELIUM_JIRA_PROJECT_ALLOWLIST\n" +
      "  • MYCELIUM_MAX_WRITES_PER_MIN\n\n" +
      "Edit .env and restart the api container to apply changes."
    }
  />
);
