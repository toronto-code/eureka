"use client";

import { useEffect } from "react";

import { RiskBadge } from "@/components/RiskBadge";
import { StatusDot } from "@/components/StatusDot";
import type { AgentRun, AuditLog, RiskLevel } from "@/lib/types";

interface Props {
  run: AgentRun | null;
  auditLogs: AuditLog[];
  onClose: () => void;
}

export function AgentDetailModal({ run, auditLogs, onClose }: Props) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!run) return null;

  const risk =
    (run.structured_output_json?.["risk_level"] as RiskLevel | undefined) ??
    null;
  const linkedAudit = auditLogs.filter((log) => log.agent_run_id === run.id);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="flex" style={{ justifyContent: "space-between" }}>
          <div className="flex">
            <StatusDot status={run.status} />
            <h2 style={{ margin: 0 }}>{run.agent_name}</h2>
            <span className="badge badge-neutral">{run.agent_type}</span>
            <RiskBadge risk={risk} />
          </div>
          <button className="btn" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="muted" style={{ marginTop: 6 }}>
          {run.output_summary || run.input_summary}
        </p>
        <div className="grid-2">
          <div>
            <div className="section-title">Full prompt</div>
            <pre className="scroll-box">{run.full_prompt ?? "—"}</pre>
          </div>
          <div>
            <div className="section-title">project_data subset</div>
            <pre className="scroll-box">
              {JSON.stringify(run.project_data_subset_json ?? {}, null, 2)}
            </pre>
          </div>
        </div>
        <div className="section-title" style={{ marginTop: 16 }}>
          Structured output
        </div>
        <pre className="scroll-box">
          {JSON.stringify(run.structured_output_json ?? {}, null, 2)}
        </pre>
        <div className="section-title" style={{ marginTop: 16 }}>
          Audit events
        </div>
        {linkedAudit.length === 0 ? (
          <p className="muted">No audit events linked to this run.</p>
        ) : (
          <div className="timeline">
            {linkedAudit.map((log) => (
              <div className="timeline-item" key={log.id}>
                <div className="dot" />
                <div>
                  <strong>{log.action_type}</strong>{" "}
                  <span className="muted">— {log.actor}</span>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {log.output_summary ?? log.input_summary ?? ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
