import Link from "next/link";

import { RecordingsList } from "@/components/RecordingsList";
import { api } from "@/lib/api";
import type { IntegrationDiagnostic } from "@/lib/types";

export const dynamic = "force-dynamic";

type SourceKey = "github" | "jira" | "slack";

const SOURCE_META: Record<
  SourceKey,
  { label: string; description: string; pulls: string[] }
> = {
  github: {
    label: "GitHub",
    description: "Connected via Personal Access Token.",
    pulls: ["repos", "commits", "pull requests", "issues"],
  },
  jira: {
    label: "Jira",
    description: "Connected via API token + email.",
    pulls: ["issues", "statuses", "assignees", "priority"],
  },
  slack: {
    label: "Slack",
    description: "Connected via bot/user token.",
    pulls: ["public channel messages", "files", "user directory"],
  },
};

function SourceCard({
  sourceKey,
  diag,
}: {
  sourceKey: SourceKey;
  diag: IntegrationDiagnostic | undefined;
}) {
  const meta = SOURCE_META[sourceKey];
  const ok = diag?.ok ?? false;
  const status = diag?.status ?? "not_configured";
  const badgeClass =
    status === "operational"
      ? "badge-green"
      : status === "error"
        ? "badge-red"
        : "badge-amber";
  const label =
    status === "operational"
      ? "pulling"
      : status === "error"
        ? "error"
        : "not configured";

  return (
    <div className="row" style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div className="flex" style={{ justifyContent: "space-between", gap: 12 }}>
        <div className="flex-col" style={{ gap: 4, minWidth: 0 }}>
          <div className="flex" style={{ gap: 8, alignItems: "center" }}>
            <strong>{meta.label}</strong>
            <span className={`badge ${badgeClass}`}>{label}</span>
          </div>
          <div className="faint" style={{ fontSize: 12 }}>
            {meta.description}
          </div>
        </div>
      </div>
      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
        Pulls: {meta.pulls.join(", ")}.
      </div>
      {!ok && diag?.detail ? (
        <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
          {diag.detail}
        </div>
      ) : null}
    </div>
  );
}

export default async function IngestionPage() {
  const [docs, integrations] = await Promise.all([
    api.listDocuments(),
    api.integrations(),
  ]);
  const sessionDocs = docs.filter((d) => d.source_type === "web_session");
  const d = integrations.diagnostics ?? {};

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Ingestion</h2>
          <p>
            Agents pull context <strong>automatically</strong> from your
            configured integrations — there is no manual upload. Configure the
            sources below in <Link href="/settings">Settings</Link>, and watch
            the live feed in{" "}
            <Link href="/incoming">Incoming Data</Link>.
          </p>
        </div>
      </header>

      <div className="card">
        <h3>Data sources</h3>
        <p
          className="muted"
          style={{ fontSize: 12, marginTop: -4, marginBottom: 10 }}
        >
          Everything below flows directly into the orchestrator on every chat
          turn. No copy-paste required.
        </p>
        <div className="list-card">
          <SourceCard sourceKey="github" diag={d.github} />
          <SourceCard sourceKey="jira" diag={d.jira} />
          <SourceCard sourceKey="slack" diag={d.slack} />
        </div>
      </div>

      <RecordingsList />

      <div className="card">
        <h3>Ingested web sessions</h3>
        {sessionDocs.length === 0 ? (
          <p className="muted">
            No sessions ingested yet. Use the{" "}
            <strong>Record session</strong> pill (bottom-right) to capture a
            workflow and feed it to the agents.
          </p>
        ) : (
          <div className="list-card">
            {sessionDocs.map((doc) => (
              <div className="row" key={doc.id}>
                <div className="flex-col" style={{ gap: 4 }}>
                  <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
                    <strong>{doc.title}</strong>
                    <span className="badge badge-purple">web session</span>
                    <span className="badge badge-neutral">
                      {doc.chunk_count} chunks
                    </span>
                  </div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    {new Date(doc.created_at).toLocaleString()}
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
