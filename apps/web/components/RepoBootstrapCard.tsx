"use client";

import { useState } from "react";

export function RepoBootstrapCard({ hasProjects }: { hasProjects: boolean }) {
  const [repoUrl, setRepoUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onAddRepo() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await fetch("/api/settings/repository/bootstrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl.trim() || null }),
      });
      const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      if (!res.ok || payload.ok === false) {
        throw new Error(String(payload.error || `request_failed_${res.status}`));
      }
      setMsg(
        `Connected ${String(payload.repository || "")}. Using PAT/webhook from .env when configured.`,
      );
      setRepoUrl("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>Repository link</h3>
      {!hasProjects ? (
        <p className="muted" style={{ marginTop: 0 }}>
          No seeded project found. Add a repo link to bootstrap one now.
        </p>
      ) : (
        <p className="muted" style={{ marginTop: 0 }}>
          Add or re-link a GitHub repository for OL runs.
        </p>
      )}
      <div className="flex" style={{ alignItems: "stretch" }}>
        <input
          type="text"
          placeholder="https://github.com/owner/repo"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          disabled={busy}
        />
        <button className="btn btn-primary" onClick={onAddRepo} disabled={busy}>
          {busy ? "Adding..." : "Add repo link"}
        </button>
      </div>
      {msg && <p className="pat-ok">{msg}</p>}
      {err && <p className="pat-err">{err}</p>}
    </div>
  );
}
