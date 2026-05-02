import Link from "next/link";

import { RiskBadge } from "@/components/RiskBadge";
import type { OrchestratorOutput } from "@/lib/types";

export function TaskBrief({
  output,
  taskDbId,
}: {
  output: OrchestratorOutput;
  /** Internal tasks.id when this run is tied to a row (demo seed sets this). */
  taskDbId?: string | null;
}) {
  const understanding = output.task_understanding;
  return (
    <div className="card">
      <h3>Task brief</h3>
      <p style={{ marginTop: 0 }}>
        <strong>Plain-English goal:</strong>{" "}
        <span>{understanding.plain_english_goal}</span>
      </p>
      <p>
        <strong>Technical goal:</strong>{" "}
        <span className="muted">{understanding.technical_goal}</span>
      </p>
      <div className="grid-2">
        <div>
          <div className="section-title">Known constraints</div>
          {understanding.known_constraints.length === 0 ? (
            <p className="muted">None recorded.</p>
          ) : (
            <ul>
              {understanding.known_constraints.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="section-title">Missing information</div>
          {understanding.missing_information.length === 0 ? (
            <p className="muted">None.</p>
          ) : (
            <ul>
              {understanding.missing_information.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="flex" style={{ marginTop: 12, flexWrap: "wrap", gap: 12 }}>
        <RiskBadge risk={output.risk_classification.overall_risk} />
        <span className="muted">{output.risk_classification.reasoning}</span>
        {taskDbId ? (
          <Link href={`/tasks/${taskDbId}`} className="btn">
            View task record
          </Link>
        ) : null}
      </div>
    </div>
  );
}
