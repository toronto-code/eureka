"use client";

import { useState } from "react";

import { RiskBadge } from "@/components/RiskBadge";
import type { ApprovalRecord, RiskLevel } from "@/lib/types";

interface Props {
  taskId: string;
  approval: ApprovalRecord | null;
  blockedActions: string[];
  recommendedAction: { description: string } | null;
  riskLevel: RiskLevel | null;
}

export function ApprovalPanel({
  taskId,
  approval,
  blockedActions,
  recommendedAction,
  riskLevel,
}: Props) {
  const [notes, setNotes] = useState("");
  const [decision, setDecision] = useState<string | null>(
    approval?.status ?? null,
  );
  const [pending, setPending] = useState(false);

  if (!approval) {
    return (
      <div className="card">
        <h3>Human approval</h3>
        <p className="muted">No approval is required for this task right now.</p>
      </div>
    );
  }

  async function decide(kind: "approve" | "reject") {
    setPending(true);
    try {
      const res = await fetch(`/api/tasks/${taskId}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ approver: "demo-user", notes }),
        headers: { "Content-Type": "application/json" },
      });
      if (res.ok) {
        const json = await res.json();
        setDecision(json.approval_status ?? (kind === "approve" ? "APPROVED" : "REJECTED"));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="card">
      <h3>Human approval</h3>
      <div className="flex" style={{ gap: 10, marginBottom: 10 }}>
        <RiskBadge risk={riskLevel} />
        <span className="badge badge-amber">Approval {decision ?? approval.status}</span>
      </div>
      <p style={{ marginTop: 0 }}>
        <strong>Why approval is required:</strong>{" "}
        <span className="muted">{approval.reason ?? "Risky write action."}</span>
      </p>
      {recommendedAction ? (
        <p>
          <strong>Recommended action:</strong>{" "}
          <span className="muted">{recommendedAction.description}</span>
        </p>
      ) : null}
      {blockedActions.length > 0 ? (
        <div>
          <div className="section-title">Blocked actions</div>
          <ul>
            {blockedActions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="flex-col" style={{ marginTop: 12 }}>
        <textarea
          placeholder="Add a note (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={decision === "APPROVED" || decision === "REJECTED" || pending}
        />
        <div className="flex">
          <button
            className="btn btn-primary"
            onClick={() => void decide("approve")}
            disabled={
              decision === "APPROVED" || decision === "REJECTED" || pending
            }
          >
            Approve
          </button>
          <button
            className="btn btn-danger"
            onClick={() => void decide("reject")}
            disabled={
              decision === "APPROVED" || decision === "REJECTED" || pending
            }
          >
            Reject
          </button>
          {decision ? (
            <span className="muted">Decision recorded: {decision}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
