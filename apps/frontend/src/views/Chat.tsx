import { useState } from "react";
import { api } from "../api";

interface Message {
  role: "user" | "agent" | "system";
  text: string;
  correlation_id?: string;
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "system", text: "Mycelium agent ready. Ask anything about your codebase, team, or processes." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    try {
      const r = await api.chat(text);
      setMessages((m) => [
        ...m,
        {
          role: "agent",
          text: `task ${r.task_id} dispatched (correlation_id=${r.correlation_id})`,
          correlation_id: r.correlation_id,
        },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "system", text: `error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <header className="page-header">
        <h2>Chat</h2>
      </header>
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            <div className="msg-role">{m.role}</div>
            <div className="msg-text">{m.text}</div>
            {m.correlation_id && <div className="msg-cid">{m.correlation_id}</div>}
          </div>
        ))}
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
