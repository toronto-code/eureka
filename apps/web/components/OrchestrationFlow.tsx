"use client";

import { useState } from "react";

import { AgentDetailModal } from "@/components/AgentDetailModal";
import { RiskBadge } from "@/components/RiskBadge";
import { StatusDot } from "@/components/StatusDot";
import type { AgentRun, AuditLog, RiskLevel } from "@/lib/types";

interface Props {
  orchestrator: AgentRun;
  workers: AgentRun[];
  auditLogs: AuditLog[];
}

export function OrchestrationFlow({
  orchestrator,
  workers,
  auditLogs,
}: Props) {
  const [selected, setSelected] = useState<AgentRun | null>(null);

  return (
    <div className="card">
      <h3>Agent flow</h3>
      <div className="flow-graph">
        <div
          className="flow-orchestrator"
          onClick={() => setSelected(orchestrator)}
          style={{ cursor: "pointer" }}
        >
          <div className="flex" style={{ justifyContent: "center", gap: 8 }}>
            <StatusDot status={orchestrator.status} />
            <strong>{orchestrator.agent_name}</strong>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {orchestrator.output_summary ?? "Orchestrator run"}
          </div>
        </div>
        <div className="flow-edge" />
        <div className="flow-workers">
          {workers.length === 0 ? (
            <p className="muted">No worker agents were spawned.</p>
          ) : (
            workers.map((worker) => {
              const risk =
                (worker.structured_output_json?.["risk_level"] as
                  | RiskLevel
                  | undefined) ?? null;
              return (
                <div
                  className="flow-worker"
                  key={worker.id}
                  onClick={() => setSelected(worker)}
                >
                  <div className="flex" style={{ justifyContent: "space-between" }}>
                    <div className="flex" style={{ gap: 6 }}>
                      <StatusDot status={worker.status} />
                      <strong style={{ fontSize: 13 }}>{worker.agent_name}</strong>
                    </div>
                    <RiskBadge risk={risk} />
                  </div>
                  <div
                    className="muted"
                    style={{ fontSize: 12, marginTop: 4 }}
                  >
                    {worker.output_summary ?? worker.input_summary ?? ""}
                  </div>
                  <div className="faint" style={{ fontSize: 11, marginTop: 4 }}>
                    {worker.agent_type} · {worker.model}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
      <AgentDetailModal
        run={selected}
        auditLogs={auditLogs}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
