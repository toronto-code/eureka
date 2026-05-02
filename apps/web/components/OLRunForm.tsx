"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import type { ProjectSummary } from "../lib/types";

interface Props {
  projects: ProjectSummary[];
  defaultProjectId?: string;
}

export function OLRunForm({ projects, defaultProjectId }: Props) {
  const router = useRouter();
  const [projectId, setProjectId] = useState(
    defaultProjectId ?? projects[0]?.id ?? "",
  );
  const [request, setRequest] = useState("");
  const [jiraKey, setJiraKey] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = submitting || !projectId || !request.trim();

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/ol/run?project_id=${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_request: request,
          origin: "manual",
          jira_ticket_key: jiraKey || null,
          acceptance_criteria: acceptance
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error(`run failed (${res.status})`);
      const payload = (await res.json()) as { run?: { id: string } };
      if (payload.run?.id) {
        router.push(`/ol/${payload.run.id}`);
        router.refresh();
      } else {
        router.refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (projects.length === 0) {
    return (
      <div className="card muted">
        No projects yet. Seed the database or create a project to start an OL
        run.
      </div>
    );
  }

  return (
    <form className="card ol-run-form" onSubmit={onSubmit}>
      <label>
        <span>Project</span>
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Request</span>
        <textarea
          rows={4}
          value={request}
          placeholder="e.g. Add a short onboarding section to the payments docs."
          onChange={(e) => setRequest(e.target.value)}
          required
        />
      </label>
      <div className="row">
        <label className="flex-1">
          <span>Jira ticket key (optional)</span>
          <input
            type="text"
            value={jiraKey}
            onChange={(e) => setJiraKey(e.target.value.toUpperCase())}
            placeholder="PAY-101"
          />
        </label>
      </div>
      <label>
        <span>Acceptance criteria (one per line, optional)</span>
        <textarea
          rows={3}
          value={acceptance}
          onChange={(e) => setAcceptance(e.target.value)}
        />
      </label>
      {error && <div className="error">{error}</div>}
      <button type="submit" disabled={disabled}>
        {submitting ? "Running OL…" : "Run OL"}
      </button>
    </form>
  );
}
