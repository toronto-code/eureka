import { useEffect, useRef, useState } from "react";
import { authFetch } from "../lib/auth";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
  last_message?: string | null;
  message_count?: number;
}

const insightColors: Record<string, { border: string; bg: string; fg: string }> = {
  alert: { border: "#ef4444", bg: "#1a0c0c", fg: "#fca5a5" },
  warning: { border: "#f59e0b", bg: "#1a160a", fg: "#fcd34d" },
  info: { border: "#3b82f6", bg: "#0c1120", fg: "#93c5fd" },
};
const actionColor = (s?: string) => (s === "error" || s === "blocked" ? "#ef4444" : s === "running" || s === "awaiting_confirm" ? "#f59e0b" : "#22c55e");

export function Chat() {
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

  // Load conversations on mount
  useEffect(() => {
    void refreshConversations();
  }, []);

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

  // Insights
  useEffect(() => {
    authFetch(`${API_URL}/chat/insights`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setInsights)
      .catch(() => setInsights([]));
  }, []);

  // Live agent actions
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
      // refresh conversation list so the title (auto-derived from first user msg) updates
      void refreshConversations();
    } catch (e) {
      setMessages((prev) => [...prev.slice(0, -1), { role: "system", text: `error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden", background: "#0a0a0a", color: "#e5e7eb" }}>
      {/* Far-left: conversation list */}
      <aside style={{ width: 240, borderRight: "1px solid #1f2937", display: "flex", flexDirection: "column", background: "#070707" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #1f2937" }}>
          <button
            onClick={newConversation}
            style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1e293b", color: "#e5e7eb", border: "1px solid #334155", cursor: "pointer", fontSize: 12, fontWeight: 500 }}
          >
            + New chat
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: 8 }}>
          {conversations.length === 0 && (
            <p style={{ fontSize: 11, color: "#6b7280", textAlign: "center", marginTop: 20 }}>No conversations yet</p>
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
                  borderRadius: 5,
                  background: isActive ? "#1e293b" : "transparent",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 6,
                }}
              >
                <div style={{ flex: 1, overflow: "hidden" }}>
                  <div style={{ fontSize: 12, color: "#e5e7eb", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.title}
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280" }}>{c.mode} · {c.message_count ?? 0} msg</div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Delete "${c.title}"?`)) deleteConversation(c.id);
                  }}
                  style={{ background: "transparent", color: "#6b7280", border: "none", cursor: "pointer", fontSize: 12, padding: 2 }}
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
      <aside style={{ width: 240, borderRight: "1px solid #1f2937", padding: 12, overflowY: "auto" }}>
        <h3 style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>Insights</h3>
        {!insights && <p style={{ fontSize: 11, color: "#6b7280" }}>Loading…</p>}
        {insights?.length === 0 && <p style={{ fontSize: 11, color: "#6b7280" }}>No insights yet.</p>}
        {insights?.map((ins, i) => {
          const c = insightColors[ins.type] ?? insightColors.info;
          return (
            <div key={i} style={{ borderLeft: `3px solid ${c.border}`, background: c.bg, padding: "7px 9px", borderRadius: 5, marginBottom: 6 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: c.fg, marginBottom: 2 }}>{ins.title}</div>
              <div style={{ fontSize: 10, color: "#9ca3af", lineHeight: 1.4 }}>{ins.description}</div>
            </div>
          );
        })}
      </aside>

      {/* Center: Chat */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 360 }}>
        <header style={{ padding: 12, borderBottom: "1px solid #1f2937", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ fontSize: 14, fontWeight: 600 }}>{conversations.find((c) => c.id === activeConvId)?.title ?? "New conversation"}</h2>
            <p style={{ fontSize: 10, color: "#6b7280" }}>{agentMode ? "Agentic — can read AND write" : "Read-only intelligence"}</p>
          </div>
          <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
            <input type="checkbox" checked={agentMode} onChange={(e) => setAgentMode(e.target.checked)} />
            agent mode
          </label>
        </header>

        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 14 }}>
          {messages.length === 0 && (
            <div style={{ color: "#6b7280", textAlign: "center", marginTop: 60, fontSize: 12 }}>
              <p style={{ marginBottom: 10 }}>Try:</p>
              <p style={{ color: "#9ca3af", marginBottom: 4 }}>"List my Jira tickets"</p>
              <p style={{ color: "#9ca3af", marginBottom: 4 }}>"Take care of KAN-3"</p>
              <p style={{ color: "#9ca3af" }}>"Who's working on what right now?"</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              style={{
                margin: "6px 0",
                padding: "9px 12px",
                background: m.role === "user" ? "#1e293b" : m.role === "system" ? "#1a0c0c" : "#0f172a",
                color: m.role === "system" ? "#fca5a5" : "#e5e7eb",
                borderRadius: 8,
                maxWidth: "92%",
                marginLeft: m.role === "user" ? "auto" : 0,
                fontSize: 12,
                lineHeight: 1.55,
                whiteSpace: "pre-wrap",
                fontFamily: m.text.includes("→ ") ? "ui-monospace, monospace" : "inherit",
              }}
            >
              {m.text || (busy && i === messages.length - 1 ? "…" : "")}
            </div>
          ))}
        </div>

        <form
          style={{ borderTop: "1px solid #1f2937", padding: 10, display: "flex", gap: 6 }}
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={agentMode ? "Tell the agent what to do..." : "Ask about your stack..."}
            disabled={busy}
            style={{ flex: 1, padding: "9px 12px", borderRadius: 7, border: "1px solid #1f2937", background: "#0a0a0a", color: "#e5e7eb", fontSize: 12 }}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            style={{ padding: "9px 16px", borderRadius: 7, background: busy ? "#374151" : "#3b82f6", color: "white", border: "none", cursor: busy ? "not-allowed" : "pointer", fontSize: 12 }}
          >
            {busy ? "…" : "Send"}
          </button>
        </form>
      </div>

      {/* Right: live agent actions */}
      <aside style={{ width: 280, borderLeft: "1px solid #1f2937", padding: 12, overflowY: "auto" }}>
        <h3 style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>Agent actions</h3>
        {actions.length === 0 && <p style={{ fontSize: 11, color: "#6b7280" }}>None yet.</p>}
        {actions.map((a, i) => (
          <div key={i} style={{ borderLeft: `2px solid ${actionColor(a.status)}`, padding: "5px 8px", marginBottom: 4, fontSize: 10, background: "#0c0c0c", borderRadius: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: actionColor(a.status), fontWeight: 600 }}>{a.tool}</span>
              <span style={{ color: "#6b7280", fontSize: 9 }}>{a.ts ? new Date(a.ts * 1000).toLocaleTimeString() : ""}</span>
            </div>
            {a.summary && a.status !== "running" && (
              <div style={{ color: "#9ca3af", fontSize: 9, marginTop: 2 }}>{a.summary.slice(0, 100)}</div>
            )}
          </div>
        ))}
      </aside>
    </div>
  );
}
