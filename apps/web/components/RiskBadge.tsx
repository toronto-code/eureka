import type { RiskLevel } from "@/lib/types";

const LABELS: Record<RiskLevel, string> = {
  READ_ONLY: "Read only",
  LOW_RISK_WRITE: "Low-risk write",
  HIGH_RISK_WRITE: "High-risk write",
};

const CLASSES: Record<RiskLevel, string> = {
  READ_ONLY: "badge badge-green",
  LOW_RISK_WRITE: "badge badge-amber",
  HIGH_RISK_WRITE: "badge badge-red",
};

export function RiskBadge({ risk }: { risk: RiskLevel | null | undefined }) {
  if (!risk) {
    return <span className="badge badge-neutral">Unclassified</span>;
  }
  return <span className={CLASSES[risk]}>{LABELS[risk]}</span>;
}
