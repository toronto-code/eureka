import Link from "next/link";

import { api } from "@/lib/api";
import type { IntegrationDiagnostic } from "@/lib/types";

export const dynamic = "force-dynamic";

type SourceKey = "github" | "jira" | "slack";

const SOURCE_META: Record<
  SourceKey,
  { label: string; description: string; logs: string[] }
> = {
  github: {
    label: "Git / GitHub",
    description: "Logs repository activity from the configured GitHub repo.",
    logs: ["commits", "pull requests", "reviews", "issues"],
  },
  jira: {
    label: "Jira",
    description: "Logs ticket movement from the configured Jira workspace.",
    logs: ["issue creation", "status changes", "comments", "assignees"],
  },
  slack: {
    label: "Slack",
    description: "Logs public-channel collaboration from the configured Slack token.",
    logs: ["public channel messages", "threads", "files", "user directory"],
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
        Logs: {meta.logs.join(", ")}.
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
  const integrations = await api.integrations();
  const d = integrations.diagnostics ?? {};

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Ingestion</h2>
          <p>
            Agents build context from <strong>work activity logs</strong> in
            Jira, Git, and Slack. There is no browser or screen recording.
            Configure the sources below in <Link href="/settings">Settings</Link>,
            and watch the live feed in{" "}
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
          These are artifact-level signals only: tickets, code activity, and
          public collaboration. Private browser activity, keystrokes, and screen
          contents are not collected.
        </p>
        <div className="list-card">
          <SourceCard sourceKey="github" diag={d.github} />
          <SourceCard sourceKey="jira" diag={d.jira} />
          <SourceCard sourceKey="slack" diag={d.slack} />
        </div>
      </div>

      <div className="card">
        <h3>Privacy boundary</h3>
        <p className="muted">
          Mycelium logs meaningful work artifacts from approved integrations.
          It does not record the browser, screen, keystrokes, form values,
          or private local activity. Slack collection is limited to configured
          workspace/channel access.
        </p>
      </div>
    </div>
  );
}
