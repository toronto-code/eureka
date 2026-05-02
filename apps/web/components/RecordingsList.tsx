"use client";

/**
 * Client-side list of web sessions recorded in this browser.
 * Sessions live in localStorage until the user ingests them — this
 * component lets them review, re-ingest, or discard drafts.
 */

import { useEffect, useState } from "react";

import type { RecordingSession } from "@/lib/event-recorder";
import {
  deleteRecording,
  listRecordings,
  subscribeRecordings,
  updateRecording,
} from "@/lib/recording-storage";
import { SessionTimeline } from "./SessionRecorder";

export function RecordingsList() {
  const [sessions, setSessions] = useState<RecordingSession[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setSessions(listRecordings());
    return subscribeRecordings(() => setSessions(listRecordings()));
  }, []);

  if (sessions.length === 0) {
    return (
      <div className="card">
        <h3>Recorded sessions</h3>
        <p className="muted">
          No recorded sessions yet. Use the{" "}
          <strong>Record session</strong> button in the bottom-right to
          capture your next workflow.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Recorded sessions</h3>
      <p
        className="muted"
        style={{ fontSize: 12, marginTop: -4, marginBottom: 10 }}
      >
        Stored in your browser. Ingest the ones you want the agents to use as
        context.
      </p>
      <div className="list-card">
        {sessions.map((session) => (
          <RecordingRow
            key={session.session_id}
            session={session}
            expanded={expanded === session.session_id}
            onToggle={() =>
              setExpanded(
                expanded === session.session_id ? null : session.session_id,
              )
            }
          />
        ))}
      </div>
    </div>
  );
}

function RecordingRow({
  session,
  expanded,
  onToggle,
}: {
  session: RecordingSession;
  expanded: boolean;
  onToggle: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justIngested, setJustIngested] = useState(false);

  async function ingestNow() {
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("title", session.title);
      fd.append("source_type", "web_session");
      fd.append(
        "raw_text",
        JSON.stringify({
          session_id: session.session_id,
          title: session.title,
          description: session.description,
          started_at: session.started_at,
          ended_at: session.ended_at,
          duration_seconds: session.duration_seconds,
          pages_visited: session.pages_visited,
          events: session.events,
        }),
      );
      const res = await fetch("/api/ingestion/upload", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(`Ingest failed (${res.status})`);
      const json = (await res.json()) as { document_id: string };
      updateRecording(session.session_id, {
        ingested: true,
        ingested_at: new Date().toISOString(),
        ingested_document_id: json.document_id,
      });
      setJustIngested(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const ingested = session.ingested || justIngested;

  return (
    <div className="row" style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div
        className="flex"
        style={{ justifyContent: "space-between", width: "100%", gap: 12 }}
      >
        <div className="flex-col" style={{ gap: 4, flex: 1, minWidth: 0 }}>
          <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
            <strong
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {session.title}
            </strong>
            {ingested ? (
              <span className="badge badge-green">Ingested</span>
            ) : (
              <span className="badge badge-neutral">Draft</span>
            )}
            <span className="badge badge-neutral">
              {session.event_count} events
            </span>
            <span className="badge badge-neutral">
              {formatDuration(session.duration_seconds)}
            </span>
          </div>
          <div className="faint" style={{ fontSize: 11 }}>
            {new Date(session.started_at).toLocaleString()} ·{" "}
            {session.pages_visited.slice(0, 4).join(", ") || "no pages"}
          </div>
        </div>
        <div className="flex" style={{ gap: 6, flexShrink: 0 }}>
          <button type="button" className="btn btn-ghost" onClick={onToggle}>
            {expanded ? "Hide" : "Review"}
          </button>
          {!ingested ? (
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void ingestNow()}
            >
              {busy ? "Ingesting…" : "Ingest"}
            </button>
          ) : null}
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy}
            onClick={() => {
              if (confirm("Delete this recording from your browser?")) {
                deleteRecording(session.session_id);
              }
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {error ? (
        <div className="badge badge-red" style={{ marginTop: 8 }}>
          {error}
        </div>
      ) : null}

      {expanded ? (
        <div style={{ marginTop: 12 }}>
          <SessionTimeline events={session.events} />
        </div>
      ) : null}
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}
