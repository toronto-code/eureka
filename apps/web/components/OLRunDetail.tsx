import type {
  LaneResultDto,
  LaneStep,
  OrchestratorRunRecord,
  RetrievalPlanDto,
  RetrievedChunkDto,
  WorkerDirectiveDto,
} from "../lib/types";

function asRetrievalPlan(
  value: OrchestratorRunRecord["retrieval_plan"],
): RetrievalPlanDto {
  return value as RetrievalPlanDto;
}

function asLaneResult(
  value: OrchestratorRunRecord["lane_result"],
): LaneResultDto {
  return value as LaneResultDto;
}

export function OLRunDetail({
  run,
  chunks,
}: {
  run: OrchestratorRunRecord;
  chunks: RetrievedChunkDto[];
}) {
  const plan = asRetrievalPlan(run.retrieval_plan);
  const lane = asLaneResult(run.lane_result);
  return (
    <div className="ol-run-detail">
      <Header run={run} />

      <section>
        <h2>Classification</h2>
        <dl className="kv-grid">
          <div>
            <dt>Route</dt>
            <dd>{run.route ?? "—"}</dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>{run.confidence != null ? `${(run.confidence * 100).toFixed(1)}%` : "—"}</dd>
          </div>
          <div>
            <dt>Risk</dt>
            <dd>{run.risk_level ?? "—"}</dd>
          </div>
          <div>
            <dt>Origin</dt>
            <dd>
              {run.origin}
              {run.origin_reference ? ` · ${run.origin_reference}` : ""}
            </dd>
          </div>
          <div>
            <dt>Lane</dt>
            <dd>{run.lane_used ?? "—"}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>
              {(run.run_metadata as Record<string, unknown>)?.model as string ??
                "—"}
            </dd>
          </div>
        </dl>
        {run.reasoning_summary && (
          <blockquote className="reasoning">{run.reasoning_summary}</blockquote>
        )}
      </section>

      <section>
        <h2>Retrieval plan</h2>
        <ul className="kv-list">
          <li>
            <strong>Queries:</strong>{" "}
            {(plan.queries || []).join(" · ") || "(none)"}
          </li>
          <li>
            <strong>Source types:</strong>{" "}
            {(plan.source_types || []).join(", ") || "(any)"}
          </li>
          <li>
            <strong>File paths:</strong>{" "}
            {(plan.file_paths || []).join(", ") || "(any)"}
          </li>
          <li>
            <strong>Max chunks:</strong> {plan.max_chunks} · recency bias:{" "}
            {String(plan.recency_bias)}
          </li>
        </ul>
      </section>

      <section>
        <h2>Worker directives ({run.worker_directives.length})</h2>
        <div className="directive-grid">
          {run.worker_directives.length === 0 && (
            <p className="muted">No directives emitted.</p>
          )}
          {run.worker_directives.map((d: WorkerDirectiveDto, i) => (
            <div className="directive-card" key={`${d.worker}-${i}`}>
              <div className="directive-head">
                <span className="tag tag-blue">{d.worker}</span>
                <span className={`tag tag-${d.priority}`}>{d.priority}</span>
              </div>
              <p>{d.purpose}</p>
              <small>schema: {d.expected_output_schema}</small>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2>Retrieved chunks ({chunks.length})</h2>
        {chunks.length === 0 && <p className="muted">No chunks retrieved.</p>}
        <ul className="chunk-list">
          {chunks.map((c) => (
            <li className="chunk-card" key={c.id}>
              <div className="chunk-head">
                <span className="tag tag-grey">{c.source_type}</span>
                {c.file_path && (
                  <span className="chunk-path">
                    {c.file_path}
                    {c.start_line && c.end_line ? ` L${c.start_line}-${c.end_line}` : ""}
                  </span>
                )}
                {c.score != null && (
                  <span className="tag tag-grey">score {c.score.toFixed(3)}</span>
                )}
              </div>
              <pre className="chunk-text">{c.chunk_text}</pre>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Lane result</h2>
        <dl className="kv-grid">
          <div>
            <dt>Status</dt>
            <dd>{lane.status}</dd>
          </div>
          <div>
            <dt>PR URL</dt>
            <dd>
              {lane.pr_url ? (
                <a href={lane.pr_url} target="_blank" rel="noreferrer noopener">
                  {lane.pr_url}
                </a>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt>Jira comment</dt>
            <dd>
              {lane.jira_comment_url ? (
                <a
                  href={lane.jira_comment_url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {lane.jira_comment_url}
                </a>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt>Blocked reason</dt>
            <dd>{lane.blocked_reason ?? "—"}</dd>
          </div>
        </dl>
        {lane.details && (
          <pre className="lane-details">{lane.details}</pre>
        )}
      </section>

      <section>
        <h2>Timeline</h2>
        <ol className="timeline">
          {(lane.steps || []).length === 0 && (
            <li className="muted">No steps recorded.</li>
          )}
          {(lane.steps || []).map((s: LaneStep, i) => (
            <li key={`${s.label}-${i}`} className={s.ok ? "ok" : "fail"}>
              <span className="time">{s.at.slice(11, 19)}</span>
              <span className="label">{s.label}</span>
              {s.detail && <span className="detail">{s.detail}</span>}
            </li>
          ))}
        </ol>
      </section>

      {(run.errors || []).length > 0 && (
        <section>
          <h2>Errors</h2>
          <ul>
            {run.errors.map((e, i) => (
              <li key={i}>
                <code>{JSON.stringify(e)}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Header({ run }: { run: OrchestratorRunRecord }) {
  return (
    <header className="ol-run-header">
      <h1>OL run</h1>
      <p className="request">{run.user_request}</p>
      <div className="meta">
        <span>id: {run.id}</span>
        <span>project: {run.project_id}</span>
        <span>created: {run.created_at}</span>
        {run.finished_at && <span>finished: {run.finished_at}</span>}
      </div>
    </header>
  );
}
