"use client";

import { useState } from "react";

import type { ProjectSummary } from "@/lib/types";

interface Props {
  projects: ProjectSummary[];
}

interface Payload {
  ok: boolean;
  error?: string;
  project_id?: string;
  project_slug?: string;
  path?: string;
  exists?: boolean;
  messages_count?: number;
  messages?: Array<Record<string, unknown>>;
}

export function HistoryFileViewerCard({ projects }: Props) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<Payload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function loadFile() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/settings/orchestrator/history-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId || null }),
      });
      const payload = (await res.json().catch(() => ({}))) as Payload;
      if (!res.ok || payload.ok === false) {
        throw new Error(payload.error || `request_failed_${res.status}`);
      }
      setData(payload);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>Orchestrator history file</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        View the JSON file saved on disk under your OS app-data directory.
      </p>
      <div className="flex" style={{ alignItems: "stretch", gap: 8 }}>
        <select value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={busy}>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.slug})
            </option>
          ))}
        </select>
        <button className="btn btn-primary" onClick={loadFile} disabled={busy}>
          {busy ? "Loading..." : "View history JSON"}
        </button>
      </div>
      {err && <p className="pat-err">{err}</p>}
      {data?.path && (
        <p className="muted" style={{ marginBottom: 8 }}>
          Path: <code>{data.path}</code>
        </p>
      )}
      {data && (
        <pre className="lane-details">
{JSON.stringify(
  {
    exists: data.exists,
    messages_count: data.messages_count,
    project_id: data.project_id,
    project_slug: data.project_slug,
    messages_preview: (data.messages || []).slice(-10),
  },
  null,
  2,
)}
        </pre>
      )}
    </div>
  );
}
