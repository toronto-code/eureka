"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import { authFetch } from "@/lib/auth";
import type { OLRunDetail, ProjectSummary } from "../lib/types";
import { OLPagePanels } from "./OLPagePanels";

const API_URL =
  (typeof window !== "undefined" && (window as any).__API_URL__) ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

const STORAGE_KEY = "ol-sessions-v1";

// ---- Types ----------------------------------------------------------------

interface UserMsg {
  role: "user";
  text: string;
  ts: number;
}

interface AssistantMsg {
  role: "assistant";
  ts: number;
  status: "thinking" | "done" | "error";
  runId?: string;
  route?: string | null;
  risk?: string | null;
  laneStatus?: string | null;
  reasoning?: string | null;
  prUrl?: string | null;
  jiraCommentUrl?: string | null;
  blockedReason?: string | null;
  error?: string;
}

type Msg = UserMsg | AssistantMsg;

interface Session {
  id: string;
  title: string;
  messages: Msg[];
  createdAt: number;
  lastOpenedAt: number;
}

interface AgentAction {
  tool: string;
  args?: Record<string, unknown>;
  summary?: string;
  status?: string;
  ts?: number;
}

interface Props {
  projects: ProjectSummary[];
  defaultProjectId?: string;
}

// ---- Constants ------------------------------------------------------------

const ROUTE_LABELS: Record<string, string> = {
  inquiry: "Inquiry",
  simple_code: "Simple code",
  complex_code: "Complex code",
  planning: "Planning",
  blocked: "Blocked",
  needs_human_review: "Needs human review",
};

const RISK_TINTS: Record<string, string> = {
  low: "tag-green",
  medium: "tag-amber",
  high: "tag-red",
};

const EXAMPLE_PROMPTS = [
  "Summarize recent runs",
  "List my Jira tickets",
  "Review open PRs",
  "Check integration status",
];

const actionColor = (s?: string) =>
  s === "error" || s === "blocked"
    ? "var(--red)"
    : s === "running" || s === "awaiting_confirm"
    ? "var(--amber)"
    : "var(--green)";

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// ---- localStorage helpers -------------------------------------------------

function readSessions(): Session[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeSessions(sessions: Session[]): void {
  if (typeof window === "undefined") return;
  // Sort by lastOpenedAt desc before persisting
  const sorted = [...sessions].sort((a, b) => b.lastOpenedAt - a.lastOpenedAt);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sorted));
}

function upsertSession(session: Session): void {
  const sessions = readSessions();
  const idx = sessions.findIndex((s) => s.id === session.id);
  if (idx >= 0) {
    sessions[idx] = session;
  } else {
    sessions.unshift(session);
  }
  writeSessions(sessions);
}

function deleteSessionById(id: string): void {
  writeSessions(readSessions().filter((s) => s.id !== id));
}

// ---- Main component -------------------------------------------------------

export function OLChatInterface({ projects, defaultProjectId }: Props) {
  const projectId = defaultProjectId ?? projects[0]?.id ?? "";

  const [tab, setTab] = useState<"run" | "history">("run");
  const [sessionId, setSessionId] = useState<string>(() => newId());
  const [messages, setMessages] = useState<Msg[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [agentMode, setAgentMode] = useState(true);
  const [actions, setActions] = useState<AgentAction[]>([]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sseRef = useRef<EventSource | null>(null);
  // Track sessionId in a ref so the auto-save effect always uses the current value
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "24px";
      ta.style.height = `${ta.scrollHeight}px`;
    }
  }, [input]);

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  // Load sessions from localStorage on mount
  useEffect(() => {
    setSessions(readSessions());
  }, []);

  // Auto-save the current session whenever messages change
  useEffect(() => {
    if (messages.length === 0) return;
    const firstUser = messages.find((m) => m.role === "user") as UserMsg | undefined;
    const title = firstUser
      ? firstUser.text.slice(0, 60)
      : "Untitled session";
    const session: Session = {
      id: sessionIdRef.current,
      title,
      messages,
      createdAt: messages[0]?.ts ?? Date.now(),
      lastOpenedAt: Date.now(),
    };
    upsertSession(session);
    setSessions(readSessions());
  }, [messages]);

  // SSE stream for live agent actions
  useEffect(() => {
    const es = new EventSource(`${API_URL}/chat/actions/stream`);
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        if (evt.tool) setActions((prev) => [evt, ...prev].slice(0, 30));
      } catch {}
    };
    es.onerror = () => es.close();
    sseRef.current = es;
    return () => sseRef.current?.close();
  }, []);

  // ---- Session management ------------------------------------------------

  function startNewChat() {
    // Current messages are already auto-saved — just reset state
    setSessionId(newId());
    setMessages([]);
    setInput("");
    setTab("run");
  }

  function loadSession(session: Session) {
    // Update lastOpenedAt and persist
    const updated: Session = { ...session, lastOpenedAt: Date.now() };
    upsertSession(updated);
    setSessions(readSessions());
    setSessionId(updated.id);
    setMessages(updated.messages);
    setTab("run");
  }

  function removeSession(id: string) {
    deleteSessionById(id);
    setSessions(readSessions());
    // If we deleted the active session, start fresh
    if (id === sessionIdRef.current) {
      setSessionId(newId());
      setMessages([]);
    }
  }

  // ---- Send ---------------------------------------------------------------

  async function send() {
    const text = input.trim();
    if (!text || busy || !projectId) return;

    const userMsg: UserMsg = { role: "user", text, ts: Date.now() };
    const assistantMsg: AssistantMsg = {
      role: "assistant",
      ts: Date.now() + 1,
      status: "thinking",
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch(`/api/ol/run?project_id=${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_request: text, origin: "manual" }),
      });
      if (!res.ok) throw new Error(`run failed (${res.status})`);
      const payload = (await res.json()) as OLRunDetail;
      const r = payload.run;
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          role: "assistant",
          ts: assistantMsg.ts,
          status: "done",
          runId: r.id,
          route: r.route,
          risk: r.risk_level,
          laneStatus: r.lane_status,
          reasoning: r.reasoning_summary,
          prUrl: r.pr_url,
          jiraCommentUrl: r.jira_comment_url,
          blockedReason: r.blocked_reason,
        } satisfies AssistantMsg;
        return copy;
      });
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          role: "assistant",
          ts: assistantMsg.ts,
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        } satisfies AssistantMsg;
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  if (projects.length === 0) {
    return (
      <div className="card muted">
        No projects yet. Seed the database or create a project to start.
      </div>
    );
  }

  // ---- Render -------------------------------------------------------------

  return (
    <div className="ol-interface">
      {/* Tab bar + New chat */}
      <div className="ol-iface-topbar">
        <div className="ol-tabs-bar">
          <button
            type="button"
            className={`ol-tab ${tab === "run" ? "active" : ""}`}
            onClick={() => setTab("run")}
          >
            Chat
          </button>
          <button
            type="button"
            className={`ol-tab ${tab === "history" ? "active" : ""}`}
            onClick={() => {
              setSessions(readSessions());
              setTab("history");
            }}
          >
            History
            {sessions.length > 0 && (
              <span className="ol-tab-count">{sessions.length}</span>
            )}
          </button>
        </div>
        <button
          type="button"
          className="btn"
          onClick={startNewChat}
          title="Start a new conversation"
        >
          + New chat
        </button>
      </div>

      {/* Panels */}
      {tab === "run" ? (
        <RunTab
          messages={messages}
          input={input}
          busy={busy}
          agentMode={agentMode}
          actions={actions}
          scrollRef={scrollRef}
          textareaRef={textareaRef}
          onInputChange={setInput}
          onAgentModeChange={setAgentMode}
          onSend={send}
        />
      ) : (
        <HistoryTab
          sessions={sessions}
          activeSessionId={sessionId}
          onLoad={loadSession}
          onDelete={removeSession}
        />
      )}
    </div>
  );
}

// ---- Run tab --------------------------------------------------------------

interface RunTabProps {
  messages: Msg[];
  input: string;
  busy: boolean;
  agentMode: boolean;
  actions: AgentAction[];
  scrollRef: React.RefObject<HTMLDivElement>;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  onInputChange: (v: string) => void;
  onAgentModeChange: (v: boolean) => void;
  onSend: () => void;
}

function RunTab({
  messages,
  input,
  busy,
  agentMode,
  actions,
  scrollRef,
  textareaRef,
  onInputChange,
  onAgentModeChange,
  onSend,
}: RunTabProps) {
  const isEmpty = messages.length === 0;

  return (
    <div
      className="ol-thread"
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 260px",
        gap: 12,
        alignItems: "stretch",
      }}
    >
      {/* Chat column */}
      <div style={{ display: "flex", flexDirection: "column", minHeight: "72vh" }}>
        <OLPagePanels />

        <div
          ref={scrollRef}
          className="ol-thread-scroll"
          style={{ flex: 1, minHeight: 300 }}
        >
          {isEmpty ? (
            <div className="ol-thread-empty">
              <p className="ol-thread-empty-hint">Try one of these to start:</p>
              <div className="ol-example-prompts">
                {EXAMPLE_PROMPTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="ol-example-prompt"
                    onClick={() => onInputChange(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="ol-thread-messages">
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <UserBubble key={i} msg={m} />
                ) : (
                  <AssistantBubble key={i} msg={m} />
                ),
              )}
            </div>
          )}
        </div>

        <form
          className="ol-thread-input"
          onSubmit={(e) => {
            e.preventDefault();
            onSend();
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "0 4px 6px",
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={agentMode}
                onChange={(e) => onAgentModeChange(e.target.checked)}
                style={{ width: 12, height: 12 }}
              />
              agent mode {agentMode ? "(can read + write)" : "(read-only)"}
            </label>
          </div>
          <div className="ol-chat-input-wrapper">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              placeholder="Ask a question or describe a task..."
              disabled={busy}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSend();
                }
              }}
            />
            <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path
                  d="M7 11L12 6L17 11M12 18V7"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
        </form>
      </div>

      {/* Live agent actions panel */}
      <aside
        style={{
          background: "var(--bg-elev)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: 12,
          overflowY: "auto",
          maxHeight: "72vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 10,
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            Live agent actions
          </div>
          <span
            style={{
              fontSize: 10,
              background: actions.length ? "var(--accent-soft)" : "var(--neutral-100)",
              color: actions.length ? "var(--accent)" : "var(--text-muted)",
              padding: "1px 7px",
              borderRadius: "var(--radius-pill)",
            }}
          >
            {actions.length}
          </span>
        </div>
        {actions.length === 0 ? (
          <p style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
            No actions yet. Ask the agent to do something and they'll appear here in real time.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {actions.map((a, i) => (
              <div
                key={i}
                style={{
                  borderLeft: `3px solid ${actionColor(a.status)}`,
                  padding: "5px 9px",
                  fontSize: 11,
                  background: "var(--bg)",
                  borderRadius: 4,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: actionColor(a.status), fontWeight: 600, fontFamily: "var(--mono)" }}>
                    {a.tool}
                  </span>
                  <span style={{ color: "var(--text-faint)", fontSize: 9 }}>
                    {a.ts ? new Date(a.ts * 1000).toLocaleTimeString() : ""}
                  </span>
                </div>
                {a.summary && a.status !== "running" && (
                  <div style={{ color: "var(--text-muted)", fontSize: 10, marginTop: 2, lineHeight: 1.4 }}>
                    {a.summary.slice(0, 110)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}

// ---- History tab ----------------------------------------------------------

interface HistoryTabProps {
  sessions: Session[];
  activeSessionId: string;
  onLoad: (s: Session) => void;
  onDelete: (id: string) => void;
}

function HistoryTab({ sessions, activeSessionId, onLoad, onDelete }: HistoryTabProps) {
  // sessions already sorted by lastOpenedAt desc from readSessions()
  const sorted = [...sessions].sort((a, b) => b.lastOpenedAt - a.lastOpenedAt);

  if (sorted.length === 0) {
    return (
      <div className="card muted" style={{ marginTop: 12 }}>
        No saved conversations yet. Start chatting and your sessions will appear here.
      </div>
    );
  }

  return (
    <div className="ol-history-list">
      {sorted.map((s) => {
        const isActive = s.id === activeSessionId;
        const userMsgs = s.messages.filter((m) => m.role === "user") as UserMsg[];
        const lastMsg = userMsgs[userMsgs.length - 1];
        const date = new Date(s.lastOpenedAt);
        const dateStr = isToday(date)
          ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          : date.toLocaleDateString([], { month: "short", day: "numeric" });

        return (
          <div
            key={s.id}
            className={`ol-history-item ${isActive ? "active" : ""}`}
            onClick={() => onLoad(s)}
          >
            <div className="ol-history-item-main">
              <div className="ol-history-item-title">{s.title}</div>
              {lastMsg && lastMsg.text !== s.title && (
                <div className="ol-history-item-preview">{lastMsg.text.slice(0, 80)}</div>
              )}
              <div className="ol-history-item-meta">
                {userMsgs.length} message{userMsgs.length !== 1 ? "s" : ""} · {dateStr}
              </div>
            </div>
            <button
              type="button"
              className="ol-history-item-delete"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm("Delete this conversation?")) onDelete(s.id);
              }}
              title="Delete"
              aria-label="Delete conversation"
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}

function isToday(date: Date): boolean {
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

// ---- Message bubbles ------------------------------------------------------

function UserBubble({ msg }: { msg: UserMsg }) {
  return (
    <div className="ol-msg ol-msg-user">
      <div className="ol-msg-bubble">{msg.text}</div>
    </div>
  );
}

function AssistantBubble({ msg }: { msg: AssistantMsg }) {
  if (msg.status === "thinking") {
    return (
      <div className="ol-msg ol-msg-assistant">
        <div className="ol-msg-bubble ol-msg-thinking">
          <span className="ol-dot" />
          <span className="ol-dot" />
          <span className="ol-dot" />
        </div>
      </div>
    );
  }
  if (msg.status === "error") {
    return (
      <div className="ol-msg ol-msg-assistant">
        <div className="ol-msg-bubble ol-msg-error">
          Error: {msg.error ?? "unknown"}
        </div>
      </div>
    );
  }
  const route = msg.route ?? "unknown";
  const risk = msg.risk ?? "low";
  return (
    <div className="ol-msg ol-msg-assistant">
      <div className="ol-msg-bubble">
        <div className="ol-msg-meta">
          <span className="tag tag-blue">{ROUTE_LABELS[route] ?? route}</span>
          <span className={`tag ${RISK_TINTS[risk] ?? "tag-grey"}`}>risk: {risk}</span>
          {msg.laneStatus && (
            <span className="tag tag-grey">lane: {msg.laneStatus}</span>
          )}
        </div>
        {msg.reasoning && <p className="ol-msg-reasoning">{msg.reasoning}</p>}
        {msg.blockedReason && (
          <p className="ol-msg-blocked">Blocked: {msg.blockedReason}</p>
        )}
        <div className="ol-msg-links">
          {msg.prUrl && (
            <a href={msg.prUrl} target="_blank" rel="noreferrer noopener" className="tag tag-link">
              PR ↗
            </a>
          )}
          {msg.jiraCommentUrl && (
            <a href={msg.jiraCommentUrl} target="_blank" rel="noreferrer noopener" className="tag tag-link">
              Jira comment ↗
            </a>
          )}
          {msg.runId && (
            <Link href={`/ol/${msg.runId}`} className="ol-msg-detail-link">
              View full run →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
