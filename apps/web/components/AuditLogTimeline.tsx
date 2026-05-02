import { RiskBadge } from "@/components/RiskBadge";
import type { AuditLog } from "@/lib/types";

export function AuditLogTimeline({ logs }: { logs: AuditLog[] }) {
  if (logs.length === 0) {
    return (
      <div className="card">
        <h3>Audit log</h3>
        <p className="muted">No audit events yet.</p>
      </div>
    );
  }
  return (
    <div className="card">
      <h3>Audit log</h3>
      <div className="timeline">
        {logs.map((log) => (
          <div className="timeline-item" key={log.id}>
            <div className="dot" />
            <div>
              <div className="flex" style={{ gap: 8 }}>
                <strong>{log.actor}</strong>
                <span className="badge badge-neutral">{log.action_type}</span>
                <RiskBadge risk={log.risk_level} />
                <span className="badge badge-neutral">
                  approval {log.approval_status}
                </span>
              </div>
              {log.output_summary || log.input_summary ? (
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                  {log.output_summary ?? log.input_summary}
                </div>
              ) : null}
              {log.sources_used.length > 0 ? (
                <div className="faint" style={{ fontSize: 11, marginTop: 4 }}>
                  sources: {log.sources_used.join(", ")}
                </div>
              ) : null}
              <div className="faint" style={{ fontSize: 11 }}>
                {new Date(log.created_at).toLocaleString()}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
