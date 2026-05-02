import Link from "next/link";

import type { OrchestratorRunRecord } from "../lib/types";

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

export function OLRunCard({ run }: { run: OrchestratorRunRecord }) {
  const when = run.finished_at ?? run.started_at ?? run.created_at;
  const route = run.route ?? "unknown";
  const risk = run.risk_level ?? "low";
  return (
    <Link href={`/ol/${run.id}`} className="card card-link">
      <div className="card-header">
        <div className="card-title">
          {run.user_request.slice(0, 120) || "(empty request)"}
        </div>
        <span className={`tag ${run.status === "completed" ? "tag-green" : run.status === "blocked" ? "tag-amber" : "tag-grey"}`}>
          {run.status}
        </span>
      </div>
      <div className="card-meta">
        <span className="tag tag-blue">{ROUTE_LABELS[route] ?? route}</span>
        <span className={`tag ${RISK_TINTS[risk] ?? "tag-grey"}`}>risk: {risk}</span>
        <span className="tag tag-grey">origin: {run.origin}</span>
        {run.confidence != null && (
          <span className="tag tag-grey">
            confidence: {(run.confidence * 100).toFixed(0)}%
          </span>
        )}
        {run.lane_used && <span className="tag tag-grey">lane: {run.lane_used}</span>}
      </div>
      {run.reasoning_summary && (
        <p className="card-summary">{run.reasoning_summary}</p>
      )}
      <div className="card-footer">
        {run.pr_url && (
          <a
            href={run.pr_url}
            target="_blank"
            rel="noreferrer noopener"
            onClick={(e) => e.stopPropagation()}
            className="tag tag-link"
          >
            PR ↗
          </a>
        )}
        {run.jira_comment_url && (
          <a
            href={run.jira_comment_url}
            target="_blank"
            rel="noreferrer noopener"
            onClick={(e) => e.stopPropagation()}
            className="tag tag-link"
          >
            Jira comment ↗
          </a>
        )}
        <span className="card-timestamp">{when}</span>
      </div>
    </Link>
  );
}
