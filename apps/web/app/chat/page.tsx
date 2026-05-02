"use client";

import { useEffect, useRef, useState } from "react";
import { authFetch } from "@/lib/auth";

const API_URL =
  (typeof window !== "undefined" && (window as any).__API_URL__) ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

interface Message {
  role: "user" | "assistant" | "system";
  text: string;
}
interface Insight {
  type: "alert" | "warning" | "info";
  title: string;
  description: string;
}
interface AgentAction {
  tool: string;
  args?: Record<string, unknown>;
  summary?: string;
  status?: string;
  ts?: number;
}
interface Conversation {
  id: string;
  title: string;
  mode: "agent" | "intel";
  updated_at: string;
  message_count?: number;
}

const insightStyles: Record<string, { bg: string; fg: string; border: string }> = {
  alert: { bg: "var(--red-soft)", fg: "var(--red)", border: "var(--red)" },
  warning: { bg: "var(--amber-soft)", fg: "var(--amber)", border: "var(--amber)" },
  info: { bg: "var(--accent-soft)", fg: "var(--accent)", border: "var(--accent)" },
};
const actionColor = (s?: string) =>
  s === "error" || s === "blocked"
    ? "var(--red)"
    : s === "running" || s === "awaiting_confirm"
    ? "var(--amber)"
    : "var(--green)";

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [agentMode, setAgentMode] = useState(true);
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sseRef = useRef<EventSource | null>(null);

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
        setMessages(rows.map((r) => ({ role: r.role as Message["role"], text: r.content })));
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

  useEffect(() => {
    void refreshConversations();
  }, []);

  useEffect(() => {
    authFetch(`${API_URL}/chat/insights`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setInsights)
      .catch(() => setInsights([]));
  }, []);

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

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

    let convId = activeConvId;
    if (!convId) {
      const res = await authFetch(`${API_URL}/chat/conversations`, {
        method: "POST",
        body: JSON.stringify({ title: text.slice(0, 60), mode: agentMode ? "agent" : "intel" }),
      });
      if (res.ok) {
        const created: Conversation = await res.json();
        setConversations((prev) => [created, ...prev]);
        convId = created.id;
        setActiveConvId(convId);
      }
    }

    setBusy(true);
    const next: Message[] = [...messages, { role: "user", text }];
    setMessages([...next, { role: "assistant", text: "" }]);
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
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value);
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = { role: "assistant", text: acc };
          return copy;
        });
      }
      void refreshConversations();
    } catch (e) {
      setMessages((prev) => [...prev.slice(0, -1), { role: "system", text: `error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page" style={{ maxWidth: "100%", padding: 0, height: "100vh", display: "flex", flexDirection: "column" }}>
      <header className="page-header" style={{ padding: "20px 32px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2>Chat</h2>
          <p>{agentMode ? "Agentic — can read AND write to Jira, GitHub, Slack" : "Read-only intelligence"}</p>
        </div>
        <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={agentMode}
            onChange={(e) => setAgentMode(e.target.checked)}
            style={{ width: 14, height: 14 }}
          />
          agent mode
        </label>
      </header>

      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "240px 240px 1fr 280px", overflow: "hidden" }}>
        {/* Conversations */}
        <aside style={{ borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--bg-elev)" }}>
          <div style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
            <button onClick={newConversation} className="btn btn-primary" style={{ width: "100%", padding: "8px 12px", fontSize: 13 }}>
              + New chat
            </button>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: 8 }}>
            {conversations.length === 0 && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", marginTop: 24 }}>No conversations yet</p>
            )}
            {conversations.map((c) => {
              const isActive = c.id === activeConvId;
              return (
                <div
                  key={c.id}
                  onClick={() => selectConversation(c.id)}
                  style={{
                    padding: "8px 10px",
                    marginBottom: 3,
                    borderRadius: 6,
                    background: isActive ? "var(--accent-soft)" : "transparent",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 6,
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

        {/* Insights */}
        <aside style={{ borderRight: "1px solid var(--border)", padding: 16, overflowY: "auto", background: "var(--bg)" }}>
          <h3 style={{ fontSize: 11, fontWeight: 600, marginBottom: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
            Insights
          </h3>
          {!insights && <p style={{ fontSize: 11, color: "var(--text-muted)" }}>Loading…</p>}
          {insights?.length === 0 && <p style={{ fontSize: 11, color: "var(--text-muted)" }}>No insights yet.</p>}
          {insights?.map((ins, i) => {
            const c = insightStyles[ins.type] ?? insightStyles.info;
            return (
              <div
                key={i}
                style={{
                  borderLeft: `3px solid ${c.border}`,
                  background: c.bg,
                  padding: "8px 10px",
                  borderRadius: 5,
                  marginBottom: 6,
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 600, color: c.fg, marginBottom: 2 }}>{ins.title}</div>
                <div style={{ fontSize: 11, color: "var(--text)", lineHeight: 1.45 }}>{ins.description}</div>
              </div>
            );
          })}
        </aside>

        {/* Center conversation */}
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0, background: "var(--bg-page)" }}>
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 24 }}>
            {messages.length === 0 && (
              <div style={{ color: "var(--text-muted)", textAlign: "center", marginTop: 60, fontSize: 13 }}>
                <p style={{ marginBottom: 12 }}>Try:</p>
                <p style={{ color: "var(--text)" }}>"List my Jira tickets"</p>
                <p style={{ color: "var(--text)" }}>"Take care of KAN-3"</p>
                <p style={{ color: "var(--text)" }}>"Who's working on what?"</p>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  margin: "6px 0",
                  padding: "10px 14px",
                  background: m.role === "user" ? "var(--accent)" : m.role === "system" ? "var(--red-soft)" : "var(--bg-elev)",
                  color: m.role === "user" ? "white" : m.role === "system" ? "var(--red)" : "var(--text)",
                  border: m.role === "assistant" ? "1px solid var(--border)" : "none",
                  borderRadius: 12,
                  maxWidth: "82%",
                  marginLeft: m.role === "user" ? "auto" : 0,
                  fontSize: 13,
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                  fontFamily: m.text.includes("→ ") ? "var(--mono)" : "inherit",
                }}
              >
                {m.text || (busy && i === messages.length - 1 ? "…" : "")}
              </div>
            ))}
          </div>

          <form
            style={{ borderTop: "1px solid var(--border)", padding: 12, display: "flex", gap: 8, background: "var(--bg)" }}
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={agentMode ? "Tell the agent what to do..." : "Ask about your stack..."}
              disabled={busy}
              style={{ flex: 1 }}
            />
            <button type="submit" disabled={busy || !input.trim()} className="btn btn-primary">
              {busy ? "…" : "Send"}
            </button>
          </form>
        </div>

        {/* Live actions */}
        <aside style={{ borderLeft: "1px solid var(--border)", padding: 16, overflowY: "auto", background: "var(--bg)" }}>
          <h3 style={{ fontSize: 11, fontWeight: 600, marginBottom: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5 }}>
            Agent actions
          </h3>
          {actions.length === 0 && <p style={{ fontSize: 11, color: "var(--text-muted)" }}>None yet.</p>}
          {actions.map((a, i) => (
            <div
              key={i}
              style={{
                borderLeft: `2px solid ${actionColor(a.status)}`,
                padding: "5px 9px",
                marginBottom: 4,
                fontSize: 11,
                background: "var(--bg-elev)",
                borderRadius: 4,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: actionColor(a.status), fontWeight: 600 }}>{a.tool}</span>
                <span style={{ color: "var(--text-faint)", fontSize: 9 }}>
                  {a.ts ? new Date(a.ts * 1000).toLocaleTimeString() : ""}
                </span>
              </div>
              {a.summary && a.status !== "running" && (
                <div style={{ color: "var(--text-muted)", fontSize: 10, marginTop: 2 }}>{a.summary.slice(0, 100)}</div>
              )}
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}
