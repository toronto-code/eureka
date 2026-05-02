export function StatusDot({ status }: { status: string }) {
  const known = ["completed", "running", "failed", "pending"].includes(status)
    ? status
    : "pending";
  return <span className={`dot-status ${known}`} aria-label={status} />;
}
