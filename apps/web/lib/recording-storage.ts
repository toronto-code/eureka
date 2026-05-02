/**
 * LocalStorage persistence for recorded web sessions.
 * Deliberately local-only for MVP — sessions are only sent to the backend
 * when the user explicitly ingests them.
 */

import type { RecordingSession } from "./event-recorder";

const KEY = "mycelium.recordings.v1";

function safeRead(): RecordingSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as RecordingSession[]) : [];
  } catch {
    return [];
  }
}

function safeWrite(sessions: RecordingSession[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(sessions));
    window.dispatchEvent(new Event("mycelium:recordings-changed"));
  } catch (err) {
    console.warn("Failed to persist recordings:", err);
  }
}

export function listRecordings(): RecordingSession[] {
  return safeRead().sort((a, b) =>
    b.started_at.localeCompare(a.started_at),
  );
}

export function getRecording(sessionId: string): RecordingSession | null {
  return safeRead().find((s) => s.session_id === sessionId) ?? null;
}

export function saveRecording(session: RecordingSession): void {
  const all = safeRead();
  const idx = all.findIndex((s) => s.session_id === session.session_id);
  if (idx >= 0) {
    all[idx] = session;
  } else {
    all.push(session);
  }
  safeWrite(all);
}

export function updateRecording(
  sessionId: string,
  patch: Partial<RecordingSession>,
): RecordingSession | null {
  const all = safeRead();
  const idx = all.findIndex((s) => s.session_id === sessionId);
  if (idx < 0) return null;
  all[idx] = { ...all[idx], ...patch };
  safeWrite(all);
  return all[idx];
}

export function deleteRecording(sessionId: string): void {
  const all = safeRead().filter((s) => s.session_id !== sessionId);
  safeWrite(all);
}

export function subscribeRecordings(fn: () => void): () => void {
  if (typeof window === "undefined") return () => void 0;
  const handler = () => fn();
  window.addEventListener("mycelium:recordings-changed", handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener("mycelium:recordings-changed", handler);
    window.removeEventListener("storage", handler);
  };
}
