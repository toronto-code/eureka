import { useState } from "react";
import { api } from "../api";
import type { AgentTaskSummary } from "../api";
import { formatAgentReply } from "../lib/agentReplyFormat";

interface Message {
  role: "user" | "agent" | "system";
  text: string;
  correlation_id?: string;
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

async function pollUntilTerminal(agentId: string, taskId: string): Promise<AgentTaskSummary> {
  let delayMs = 200;
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const t = await api.agentTask(agentId, taskId);
    if (TERMINAL.has(t.status)) {
      return t;
    }
    await new Promise((r) => setTimeout(r, delayMs));
    delayMs = Math.min(Math.floor(delayMs * 1.2), 2000);
  }
  throw new Error("Timed out waiting for agent task (60s).");
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "system",
      text:
        "Mycelium agent runs tasks via Redis. Replies shown here poll GET /agents/{id}/tasks/{task_id} until succeeded or failed.",
    },
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
          role: "system",
          text: `Queued ${r.task_id} — waiting for agent-runtime…`,
          correlation_id: r.correlation_id,
        },
      ]);
      const task = await pollUntilTerminal(r.agent_id, r.task_id);
      setMessages((m) => [
        ...m,
        {
          role: "agent",
          text: formatAgentReply(task),
          correlation_id: task.correlation_id,
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
