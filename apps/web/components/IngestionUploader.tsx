"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function IngestionUploader() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [sourceType, setSourceType] = useState<"doc" | "transcript">("doc");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit() {
    setError(null);
    setSuccess(null);
    setPending(true);
    try {
      const fd = new FormData();
      fd.append("title", title || "Untitled");
      fd.append("source_type", sourceType);
      fd.append("raw_text", text);
      const res = await fetch("/api/ingestion/upload", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      const json = (await res.json()) as { document_id: string };
      setSuccess(`Ingested ${json.document_id}`);
      setText("");
      setTitle("");
      router.refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="card">
      <h3>Add document or transcript</h3>
      <div className="flex-col">
        <label>
          <div className="section-title">Title</div>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. payments-service onboarding draft"
          />
        </label>
        <label>
          <div className="section-title">Source type</div>
          <select
            value={sourceType}
            onChange={(e) =>
              setSourceType(e.target.value === "transcript" ? "transcript" : "doc")
            }
          >
            <option value="doc">Document / spec / README</option>
            <option value="transcript">Working-session transcript</option>
          </select>
        </label>
        <label>
          <div className="section-title">Content</div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste the markdown or transcript text here…"
          />
        </label>
        <div className="flex">
          <button
            className="btn btn-primary"
            onClick={() => void submit()}
            disabled={pending || !text.trim()}
          >
            {pending ? "Uploading…" : "Ingest"}
          </button>
          {error ? <span className="badge badge-red">{error}</span> : null}
          {success ? <span className="badge badge-green">{success}</span> : null}
        </div>
      </div>
    </div>
  );
}
