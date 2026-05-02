import { api } from "../../lib/api";
import { OLChatInterface } from "../../components/OLChatInterface";

export const dynamic = "force-dynamic";

export default async function OLPage() {
  const projects = await api.listProjects();
  const defaultProject = projects[0];

  return (
    <main className="page ol-page" style={{ maxWidth: 1100 }}>
      <header className="ol-page-header" style={{ marginBottom: 24 }}>
        <h1>Orchestrator</h1>
      </header>
      <OLChatInterface
        projects={projects}
        defaultProjectId={defaultProject?.id}
      />
    </main>
  );
}
