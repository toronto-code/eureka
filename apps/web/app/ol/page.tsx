import { api } from "../../lib/api";
import { OLRunCard } from "../../components/OLRunCard";
import { OLRunForm } from "../../components/OLRunForm";

export const dynamic = "force-dynamic";

export default async function OLPage() {
  const projects = await api.listProjects();
  const defaultProject = projects[0];
  const runs = defaultProject
    ? await api.listOrchestratorRuns(defaultProject.id, 30)
    : [];

  return (
    <main className="page">
      <header className="page-header">
        <h1>Orchestrator</h1>
        <p className="muted">
          OL classifies each request, builds a retrieval plan, and dispatches to
          one of six lanes. Every decision is audited here.
        </p>
      </header>

      <OLRunForm projects={projects} defaultProjectId={defaultProject?.id} />

      <section>
        <h2>Recent runs</h2>
        {runs.length === 0 && (
          <div className="card muted">
            No runs yet. Submit a request above to create one.
          </div>
        )}
        <div className="run-grid">
          {runs.map((r) => (
            <OLRunCard key={r.id} run={r} />
          ))}
        </div>
      </section>
    </main>
  );
}
