import { IngestionUploader } from "@/components/IngestionUploader";
import { ProjectDataViewer } from "@/components/ProjectDataViewer";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function IngestionPage() {
  const [docs, projectData] = await Promise.all([
    api.listDocuments(),
    api.projectDataPreview(),
  ]);

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Ingestion</h2>
          <p>
            Upload docs or working-session transcripts. Transcripts are
            <strong> opt-in </strong>and <strong>explicitly provided</strong> —
            never collected via screen recording.
          </p>
        </div>
      </header>

      <div className="grid-2">
        <IngestionUploader />
        <ProjectDataViewer data={projectData} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Ingested documents</h3>
        {docs.length === 0 ? (
          <p className="muted">No documents ingested yet.</p>
        ) : (
          <div className="list-card">
            {docs.map((doc) => (
              <div className="row" key={doc.id}>
                <div className="flex-col" style={{ gap: 4 }}>
                  <div className="flex">
                    <strong>{doc.title}</strong>
                    <span className="badge badge-purple">{doc.source_type}</span>
                    <span className="badge badge-neutral">
                      {doc.chunk_count} chunks
                    </span>
                  </div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    {new Date(doc.created_at).toLocaleString()} ·{" "}
                    {doc.project_key ?? "no project"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
