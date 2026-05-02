import { RunDemoButton } from "@/components/RunDemoButton";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AgentsPage() {
  const [{ agent_types: agentTypes }, runs] = await Promise.all([
    api.agentTypes(),
    api.listRuns(8),
  ]);

  const orchestratorRuns = runs.filter((r) => r.agent_type === "orchestrator");
  const latest = orchestratorRuns[0] ?? null;

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Agents</h2>
          <p>
            Specialised GPT-4o agents the orchestrator can spawn. Each agent is
            a class with its own prompt, schema, and project_data subset.
          </p>
        </div>
        <RunDemoButton />
      </header>

      <div className="grid-2">
        {agentTypes.map((agent) => (
          <div className="card" key={agent.agent_type}>
            <h3>{agent.agent_name}</h3>
            <div className="flex" style={{ gap: 8, marginBottom: 8 }}>
              <span className="badge badge-purple">{agent.agent_type}</span>
              <span className="badge badge-neutral">{agent.default_model}</span>
            </div>
            <p className="muted" style={{ marginTop: 0 }}>
              {agent.system_prompt}
            </p>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Latest orchestrator output</h3>
        {latest ? (
          <pre className="scroll-box">
            {JSON.stringify(latest.structured_output_json ?? {}, null, 2)}
          </pre>
        ) : (
          <p className="muted">
            No orchestrator runs yet. Click <strong>Run demo orchestration</strong>
            .
          </p>
        )}
      </div>
    </div>
  );
}
