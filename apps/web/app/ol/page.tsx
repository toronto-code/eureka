import { api } from "../../lib/api";
import { OLChatThread } from "../../components/OLChatThread";
import { OLPageTabs } from "../../components/OLPageTabs";
import { OLRunCard } from "../../components/OLRunCard";

export const dynamic = "force-dynamic";

export default async function OLPage() {
  const projects = await api.listProjects();
  const defaultProject = projects[0];
  const runs = defaultProject
    ? await api.listOrchestratorRuns(defaultProject.id, 30)
    : [];

  const runPanel = (
    <div className="ol-center">
      <header className="ol-page-header">
        <h1>Orchestrator</h1>
      </header>
      <OLChatThread projects={projects} defaultProjectId={defaultProject?.id} />
    </div>
  );

  const historyPanel = (
    <div className="ol-center">
      <header className="ol-page-header">
        <h1>History</h1>
      </header>
      {runs.length === 0 ? (
        <div className="card muted">
          No runs yet. Submit a request from the Run tab to create one.
        </div>
      ) : (
        <div className="run-grid">
          {runs.map((r) => (
            <OLRunCard key={r.id} run={r} />
          ))}
        </div>
      )}
    </div>
  );

  return (
    <main className="page ol-page">
      <OLPageTabs runPanel={runPanel} historyPanel={historyPanel} />
    </main>
  );
}
