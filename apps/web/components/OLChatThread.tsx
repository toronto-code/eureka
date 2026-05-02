"use client";

import { useEffect, useRef, useState } from "react";

import { authFetch } from "@/lib/auth";
import { OLPagePanels } from "./OLPagePanels";

const API_URL =
  (typeof window !== "undefined" && (window as any).__API_URL__) ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

interface Props {
  projects?: unknown[];
  defaultProjectId?: string;
}

interface Message {
  role: "user" | "assistant" | "system";
  text: string;
  ts: number;
}

interface Conversation {
  id: string;
  title: string;
  mode: "agent" | "intel";
  updated_at: string;
  message_count?: number;
}

interface AgentAction {
  tool: string;
  args?: Record<string, unknown>;
  summary?: string;
  status?: string;
  ts?: number;
}

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

export function OLChatThread(_props: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [agentMode, setAgentMode] = useState(true);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  async function persistMsg(msg: Msg) {
    if (!projectId) return;
    const payload =
      msg.role === "user"
        ? { role: "user", text: msg.text, ts: msg.ts }
        : {
            role: "assistant",
            text: msg.reasoning || msg.error || "",
            ts: msg.ts,
            status: msg.status,
            runId: msg.runId,
            route: msg.route,
            risk: msg.risk,
            laneStatus: msg.laneStatus,
            reasoning: msg.reasoning,
            prUrl: msg.prUrl,
            jiraCommentUrl: msg.jiraCommentUrl,
            blockedReason: msg.blockedReason,
            error: msg.error,
          };
    await fetch(`/api/ol/history?project_id=${projectId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => null);
  }

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    (async () => {
      const res = await fetch(`/api/ol/history?project_id=${projectId}`).catch(() => null);
      if (!res?.ok) return;
      const payload = (await res.json().catch(() => ({}))) as { messages?: Msg[] };
      if (cancelled) return;
      const items = Array.isArray(payload.messages) ? payload.messages : [];
      setMessages(items);
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "24px";
      ta.style.height = `${ta.scrollHeight}px`;
    }
  }, [input]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function refreshConversations(): Promise<Conversation[]> {
    try {
      const res = await authFetch(`${API_URL}/chat/conversations`);
      if (res.ok) {
        const list: Conversation[] = await res.json();
        setConversations(list);
        if (list.length && !activeConvId) {
          setActiveConvId(list[0].id);
          await loadHistory(list[0].id);
        }
        return list;
      }
    } catch {}
    return [];
  }

  async function loadHistory(convId: string) {
    try {
      const res = await authFetch(`${API_URL}/chat/history?conversation_id=${convId}`);
      if (res.ok) {
        const rows: { role: string; content: string }[] = await res.json();
        setMessages(rows.map((r, i) => ({ role: r.role as Message["role"], text: r.content, ts: Date.now() + i })));
      }
    } catch {
      setMessages([]);
    }
  }

  async function newConversation() {
    const res = await authFetch(`${API_URL}/chat/conversations`, {
      method: "POST",
      body: JSON.stringify({ title: "New chat", mode: agentMode ? "agent" : "intel" }),
    });
    if (res.ok) {
      const created: Conversation = await res.json();
      setConversations((prev) => [created, ...prev]);
      setActiveConvId(created.id);
      setMessages([]);
    }
  }

  async function deleteConversation(id: string) {
    await authFetch(`${API_URL}/chat/conversations/${id}`, { method: "DELETE" });
    const remaining = conversations.filter((c) => c.id !== id);
    setConversations(remaining);
    if (activeConvId === id) {
      const next = remaining[0]?.id ?? null;
      setActiveConvId(next);
      if (next) await loadHistory(next);
      else setMessages([]);
    }
  }

  async function selectConversation(id: string) {
    setActiveConvId(id);
    await loadHistory(id);
  }

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
    void persistMsg(userMsg);
    setInput("");
    setBusy(true);
    const next: Message[] = [...messages, { role: "user", text, ts: Date.now() }];
    setMessages([...next, { role: "assistant", text: "", ts: Date.now() + 1 }]);
    setInput("");

    try {
      const endpoint = agentMode ? "/chat/agent" : "/chat/intel";
      const res = await authFetch(`${API_URL}${endpoint}`, {
        method: "POST",
        body: JSON.stringify({
          messages: next.map((m) => ({
            role: m.role === "assistant" ? "assistant" : "user",
            content: m.text,
          })),
          conversation_id: convId,
        }),
      });
      if (!res.ok) throw new Error(`run failed (${res.status})`);
      const payload = (await res.json()) as OLRunDetail;
      const r = payload.run;
      setMessages((prev) => {
        const copy = [...prev];
        const doneMsg: AssistantMsg = {
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
        };
        copy[copy.length - 1] = doneMsg;
        void persistMsg(doneMsg);
        return copy;
      });
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        const errMsg: AssistantMsg = {
          role: "assistant",
          ts: assistantMsg.ts,
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        };
        copy[copy.length - 1] = errMsg;
        void persistMsg(errMsg);
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="ol-thread" style={{ display: "grid", gridTemplateColumns: "220px 1fr 260px", gap: 12, alignItems: "stretch" }}>
      {/* Conversations sidebar */}
      <aside
        style={{
          background: "var(--bg-elev)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          maxHeight: "78vh",
        }}
      >
        <div style={{ padding: 8, borderBottom: "1px solid var(--border)" }}>
          <button onClick={newConversation} className="btn btn-primary" style={{ width: "100%", padding: "7px 10px", fontSize: 12 }}>
            + New chat
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 6 }}>
          {conversations.length === 0 && (
            <p style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "center", marginTop: 16 }}>
              No conversations yet
            </p>
          )}
          {conversations.map((c) => {
            const isActive = c.id === activeConvId;
            return (
              <div
                key={c.id}
                onClick={() => selectConversation(c.id)}
                style={{
                  padding: "7px 9px",
                  marginBottom: 2,
                  borderRadius: 5,
                  background: isActive ? "var(--accent-soft)" : "transparent",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 4,
                }}
              >
                <div style={{ flex: 1, overflow: "hidden" }}>
                  <div style={{ fontSize: 12, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.title}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    {c.mode} · {c.message_count ?? 0} msg
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete "${c.title}"?`)) void deleteConversation(c.id);
                  }}
                  style={{ background: "transparent", color: "var(--text-faint)", border: "none", cursor: "pointer", fontSize: 14, padding: 2 }}
                  title="Delete"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Chat thread */}
      <div style={{ display: "flex", flexDirection: "column", minHeight: "78vh" }}>
        <OLPagePanels />

        <div ref={scrollRef} className="ol-thread-scroll" style={{ flex: 1, minHeight: 300 }}>
          {isEmpty ? (
            <div className="ol-thread-empty">
              <p className="ol-thread-empty-hint">Try one of these to start:</p>
              <div className="ol-example-prompts">
                {EXAMPLE_PROMPTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="ol-example-prompt"
                    onClick={() => setInput(p)}
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
                  <UserBubble key={i} text={m.text} />
                ) : m.role === "system" ? (
                  <ErrorBubble key={i} text={m.text} />
                ) : (
                  <AssistantBubble key={i} text={m.text} thinking={busy && i === messages.length - 1 && m.text === ""} />
                ),
              )}
            </div>
          )}
        </div>

        <form
          className="ol-thread-input"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
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
                onChange={(e) => setAgentMode(e.target.checked)}
                style={{ width: 12, height: 12 }}
              />
              agent mode {agentMode ? "(can read + write — needs 'yes' confirm)" : "(read-only)"}
            </label>
          </div>
          <div className="ol-chat-input-wrapper">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              placeholder="Ask a question or describe a task..."
              disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
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

      {/* Right: persistent live agent actions panel (eureka-style) */}
      <aside
        style={{
          background: "var(--bg-elev)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: 12,
          overflowY: "auto",
          maxHeight: "78vh",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
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
            No actions yet. Ask the agent to do something — list tickets, comment on Jira, post in Slack — and they'll appear here in real time.
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
                {a.args && Object.keys(a.args).length > 0 && (
                  <div
                    style={{
                      color: "var(--text-muted)",
                      fontSize: 10,
                      marginTop: 2,
                      fontFamily: "var(--mono)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {JSON.stringify(a.args).slice(0, 80)}
                  </div>
                )}
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

function UserBubble({ text }: { text: string }) {
  return (
    <div className="ol-msg ol-msg-user">
      <div className="ol-msg-bubble">{text}</div>
    </div>
  );
}

function AssistantBubble({ text, thinking }: { text: string; thinking: boolean }) {
  if (thinking) {
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
  // Highlight tool-call lines (start with "→ tool_name(...)") in monospace
  const lines = text.split("\n");
  return (
    <div className="ol-msg ol-msg-assistant">
      <div className="ol-msg-bubble" style={{ whiteSpace: "pre-wrap" }}>
        {lines.map((line, i) => {
          const isToolCall = line.startsWith("→ ");
          return (
            <div
              key={i}
              style={{
                fontFamily: isToolCall ? "var(--mono)" : "inherit",
                color: isToolCall ? "var(--accent)" : "inherit",
                background: isToolCall ? "var(--accent-soft)" : "transparent",
                padding: isToolCall ? "2px 6px" : 0,
                borderRadius: isToolCall ? 4 : 0,
                margin: isToolCall ? "2px 0" : 0,
                fontSize: isToolCall ? 11 : "inherit",
              }}
            >
              {line}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ErrorBubble({ text }: { text: string }) {
  return (
    <div className="ol-msg ol-msg-assistant">
      <div className="ol-msg-bubble ol-msg-error">{text}</div>
    </div>
  );
}
