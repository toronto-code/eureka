/** HealthCheck shape — identical across every Mycelium service. */

export type HealthStatus = "ok" | "error";

export interface HealthCheck {
  status: HealthStatus;
  service: string;
  /** ISO 8601 timestamp */
  timestamp: string;
}
