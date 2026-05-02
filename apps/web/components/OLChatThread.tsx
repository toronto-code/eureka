"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import type { OLRunDetail, ProjectSummary } from "../lib/types";
import { OLPagePanels } from "./OLPagePanels";

interface Props {
  projects: ProjectSummary[];
  defaultProjectId?: string;
}

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
  "Debug ingestion errors",
  "Review open PRs",
  "Check integration status",
];

export function OLChatThread({ projects, defaultProjectId }: Props) {
  const projectId = defaultProjectId ?? projects[0]?.id ?? "";
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
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
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

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

  if (projects.length === 0) {
    return (
      <div className="card muted">
        No projects yet. Seed the database or create a project to start using
        the orchestrator.
      </div>
    );
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="ol-thread">
      <OLPagePanels />

      <div ref={scrollRef} className="ol-thread-scroll">
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
          void send();
        }}
      >
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
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="Send"
          >
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
  );
}

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
          <span className="tag tag-blue">
            {ROUTE_LABELS[route] ?? route}
          </span>
          <span className={`tag ${RISK_TINTS[risk] ?? "tag-grey"}`}>
            risk: {risk}
          </span>
          {msg.laneStatus && (
            <span className="tag tag-grey">lane: {msg.laneStatus}</span>
          )}
        </div>
        {msg.reasoning && (
          <p className="ol-msg-reasoning">{msg.reasoning}</p>
        )}
        {msg.blockedReason && (
          <p className="ol-msg-blocked">Blocked: {msg.blockedReason}</p>
        )}
        <div className="ol-msg-links">
          {msg.prUrl && (
            <a
              href={msg.prUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="tag tag-link"
            >
              PR ↗
            </a>
          )}
          {msg.jiraCommentUrl && (
            <a
              href={msg.jiraCommentUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="tag tag-link"
            >
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
