export const ErrorCategory = {
  CLASSIFICATION_FAILED: "classification_failed",
  SCHEMA_INVALID: "schema_invalid",
  HANDLER_EXCEPTION: "handler_exception",
  DOWNSTREAM_UNAVAILABLE: "downstream_unavailable",
  UNKNOWN: "unknown",
} as const;

export type ErrorCategory = (typeof ErrorCategory)[keyof typeof ErrorCategory];

export interface DLQMessage {
  error_category: ErrorCategory;
  retry_count: number;
  original_event: Record<string, unknown>;
  error_message: string;
  /** ISO 8601 timestamp */
  failed_at: string;
  failed_by: string;
}
