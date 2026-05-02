"use client";

/**
 * SessionRecorder — floating record button + review modal.
 *
 * Renders a pill in the bottom-right corner of the app. When the user clicks
 * Record, the underlying `EventRecorder` starts capturing clicks, navigation,
 * and form submissions. When they stop, a review modal opens so they can
 * inspect the captured events, title the session, and ingest it as context.
 *
 * Everything is opt-in and local-only until the user explicitly ingests.
 */

import { useEffect, useRef, useState } from "react";

import {
  getEventRecorder,
  type RecorderStatus,
  type RecordingSession,
  type WebSessionEvent,
} from "@/lib/event-recorder";
import {
  deleteRecording,
  saveRecording,
  updateRecording,
} from "@/lib/recording-storage";

export function SessionRecorder() {
  const [mounted, setMounted] = useState(false);
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [eventCount, setEventCount] = useState(0);
  const [reviewing, setReviewing] = useState<RecordingSession | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recorderRef = useRef<ReturnType<typeof getEventRecorder> | null>(null);

  // Get the recorder only on the client side
  const getRecorder = () => {
    if (!recorderRef.current && typeof window !== "undefined") {
      recorderRef.current = getEventRecorder();
    }
    return recorderRef.current;
  };

  useEffect(() => {
    setMounted(true);
    const recorder = getRecorder();
    if (!recorder) return;
    const unsub = recorder.subscribe((s) => {
      setStatus(s);
      setEventCount(recorder.getEventCount());
    });
    return () => {
      unsub();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const recorder = getRecorder();
    if (!recorder) return;
    if (status === "recording") {
      const start = recorder.getStartTime();
      setElapsed(Math.floor((Date.now() - start) / 1000));
      tickRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - start) / 1000));
        setEventCount(recorder.getEventCount());
      }, 500);
    } else if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [status]);

  const start = () => getRecorder()?.start();
  const stop = () => {
    const session = getRecorder()?.stop();
    if (session) {
      saveRecording(session);
      setReviewing(session);
    }
  };

  const closeReview = () => {
    setReviewing(null);
    getRecorder()?.reset();
  };

  // Don't render during SSR to avoid hydration mismatch
  if (!mounted) return null;

  return (
    <>
      <div className="recorder-pill" data-no-record="true">
        {status === "recording" ? (
          <button
            type="button"
            className="recorder-btn recorder-btn-recording"
            onClick={stop}
            aria-label="Stop recording"
          >
            <span className="recorder-dot recorder-dot-pulse" />
            <span className="recorder-label">
              {formatDuration(elapsed)} · {eventCount} events
            </span>
            <span className="recorder-stop-hint">Stop</span>
          </button>
        ) : (
          <button
            type="button"
            className="recorder-btn recorder-btn-idle"
            onClick={start}
            aria-label="Start recording session"
            title="Record a session to ingest as agent context"
          >
            <span className="recorder-dot" />
            <span className="recorder-label">Record session</span>
          </button>
        )}
      </div>

      {reviewing && (
        <SessionReviewModal
          session={reviewing}
          onClose={closeReview}
          onDiscard={() => {
            deleteRecording(reviewing.session_id);
            closeReview();
          }}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------- */
/* Session review modal                                                  */
/* -------------------------------------------------------------------- */

function SessionReviewModal({
  session,
  onClose,
  onDiscard,
}: {
  session: RecordingSession;
  onClose: () => void;
  onDiscard: () => void;
}) {
  const [title, setTitle] = useState(session.title);
  const [description, setDescription] = useState(session.description ?? "");
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function ingest() {
    setPending(true);
    setError(null);
    try {
      updateRecording(session.session_id, { title, description });
      const payload: SessionIngestPayload = {
        session_id: session.session_id,
        title: title || session.title,
        description,
        started_at: session.started_at,
        ended_at: session.ended_at,
        duration_seconds: session.duration_seconds,
        pages_visited: session.pages_visited,
        events: session.events,
      };
      const fd = new FormData();
      fd.append("title", payload.title);
      fd.append("source_type", "web_session");
      fd.append("raw_text", JSON.stringify(payload));
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
      setDone(true);
    } catch (err) {
      setError(String(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="recorder-modal-backdrop" onClick={onClose}>
      <div
        className="recorder-modal card"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <header className="recorder-modal-header">
          <div>
            <h3 style={{ margin: 0, fontSize: 16, letterSpacing: 0 }}>
              {done ? "Session ingested" : "Review recorded session"}
            </h3>
            <div className="faint" style={{ fontSize: 11, marginTop: 4 }}>
              {session.event_count} events · {formatDuration(session.duration_seconds)} ·{" "}
              {session.pages_visited.length} pages
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {done ? (
          <div style={{ padding: "20px 0" }}>
            <p>
              This session is now available to the agents as context. You can
              see it in the{" "}
              <a href="/ingestion" style={{ textDecoration: "underline" }}>
                ingestion page
              </a>
              .
            </p>
            <div className="flex" style={{ marginTop: 12 }}>
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="recorder-modal-body">
              <div className="flex-col">
                <label>
                  <div className="section-title">Title</div>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </label>
                <label>
                  <div className="section-title">
                    Description (optional)
                  </div>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What were you trying to do in this session?"
                    rows={2}
                  />
                </label>
              </div>

              <div className="section-title" style={{ marginTop: 16 }}>
                Timeline ({session.events.length})
              </div>
              <SessionTimeline events={session.events} />

              <label
                className="recorder-privacy-check"
                style={{ marginTop: 12 }}
              >
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                <span>
                  I've reviewed the timeline and confirm it contains no
                  sensitive data.
                </span>
              </label>

              {error ? (
                <div className="badge badge-red" style={{ marginTop: 8 }}>
                  {error}
                </div>
              ) : null}
            </div>

            <footer className="recorder-modal-footer">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={onDiscard}
                disabled={pending}
              >
                Discard
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!confirmed || pending || !title.trim()}
                onClick={() => void ingest()}
              >
                {pending ? "Ingesting…" : "Ingest as context"}
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- */
/* Timeline                                                              */
/* -------------------------------------------------------------------- */

export function SessionTimeline({ events }: { events: WebSessionEvent[] }) {
  const groups = groupByPage(events);
  return (
    <div className="recorder-timeline">
      {groups.map((g, i) => (
        <div className="recorder-timeline-group" key={i}>
          <div className="recorder-timeline-page">
            <span className="recorder-timeline-path">{g.path}</span>
            <span className="faint" style={{ fontSize: 10 }}>
              {g.events.length} events
            </span>
          </div>
          <div className="recorder-timeline-events">
            {g.events.map((ev) => (
              <div key={ev.id} className="recorder-timeline-event">
                <span className="recorder-timeline-time">
                  {formatTime(ev.timestamp)}
                </span>
                <span
                  className="recorder-timeline-type"
                  title={ev.type}
                >
                  {EVENT_ICONS[ev.type] ?? "•"}
                </span>
                <span className="recorder-timeline-text">
                  {describeEvent(ev)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const EVENT_ICONS: Record<string, string> = {
  "web.click": "☲",
  "web.navigation": "→",
  "web.form.submit": "⏎",
  "web.input.change": "✎",
  "web.visibility": "◐",
  "web.page_exit": "⤴",
  "web.page_resume": "⤵",
  "web.scroll.milestone": "↓",
};

function groupByPage(events: WebSessionEvent[]): Array<{
  path: string;
  events: WebSessionEvent[];
}> {
  const groups: Array<{ path: string; events: WebSessionEvent[] }> = [];
  for (const ev of events) {
    const last = groups[groups.length - 1];
    if (!last || last.path !== ev.page_path) {
      groups.push({ path: ev.page_path, events: [ev] });
    } else {
      last.events.push(ev);
    }
  }
  return groups;
}

function describeEvent(ev: WebSessionEvent): string {
  const t = ev.target;
  switch (ev.type) {
    case "web.navigation":
      return `Navigated to ${t.selector ?? ev.page_path}`;
    case "web.click": {
      const label = t.text || t.role || t.tag || "element";
      return `Clicked ${label}`;
    }
    case "web.form.submit": {
      const fc = (ev.metadata?.field_count as number) ?? 0;
      return `Submitted form (${fc} fields)`;
    }
    case "web.input.change":
      return `Changed ${t.name ?? t.tag ?? "field"}`;
    case "web.visibility":
      return ev.metadata?.hidden ? "Tab hidden" : "Tab visible";
    case "web.page_exit":
      return `Left page (${(ev.metadata?.reason as string) ?? "unknown"})`;
    case "web.page_resume":
      return `Returned to page`;
    default:
      return ev.type;
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

/* -------------------------------------------------------------------- */
/* Shared payload shape (must stay in sync with backend SessionProcessor) */
/* -------------------------------------------------------------------- */

interface SessionIngestPayload {
  session_id: string;
  title: string;
  description?: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  pages_visited: string[];
  events: WebSessionEvent[];
}
