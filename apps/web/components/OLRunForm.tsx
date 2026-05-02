"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { ProjectSummary } from "../lib/types";

interface Props {
  projects: ProjectSummary[];
  defaultProjectId?: string;
}

export function OLRunForm({ projects, defaultProjectId }: Props) {
  const router = useRouter();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const projectId = defaultProjectId ?? projects[0]?.id ?? "";
  const [request, setRequest] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = submitting || !projectId || !request.trim();

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "24px";
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [request]);

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/ol/run?project_id=${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_request: request,
          origin: "manual",
        }),
      });
      if (!res.ok) throw new Error(`run failed (${res.status})`);
      const payload = (await res.json()) as { run?: { id: string } };
      if (payload.run?.id) {
        router.push(`/ol/${payload.run.id}`);
        router.refresh();
      } else {
        router.refresh();
      }
      setRequest("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (projects.length === 0) {
    return (
      <div className="card muted">
        No projects yet. Seed the database or create a project to start an OL
        run.
      </div>
    );
  }

  const examplePrompts = [
    "Summarize recent runs",
    "Debug ingestion errors",
    "Review open PRs",
    "Check integration status",
  ];

  const handleExampleClick = (prompt: string) => {
    setRequest(prompt);
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  return (
    <div className="ol-chat-form">
      {!request && (
        <div className="ol-example-prompts">
          {examplePrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="ol-example-prompt"
              onClick={() => handleExampleClick(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={onSubmit}>
        <div className="ol-chat-input-wrapper">
          <textarea
            ref={textareaRef}
            rows={1}
            value={request}
            placeholder="Ask a question or describe a task..."
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!disabled) onSubmit(e);
              }
            }}
            required
          />
          <button type="submit" disabled={disabled} aria-label="Send">
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
        {error && <div className="ol-chat-error">{error}</div>}
      </form>
    </div>
  );
}
