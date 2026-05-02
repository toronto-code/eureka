/**
 * MyceliumEvent — the canonical event schema across every service.
 *
 * Contract:
 *  - `correlationId` is mandatory; never null.
 *  - `parentCorrelationId` is set when this event modifies/extends an earlier
 *    event (Slack edits, GitHub force-pushes, Jira merges, threaded replies).
 *  - `schemaVersion` is mandatory; default "1.0". Bump on field changes.
 *    Consumers must handle unknown versions gracefully.
 *
 * Wire format (over Redis Streams + HTTP) keeps snake_case to stay aligned with
 * the Python services. The TypeScript types use the same field names.
 */

export const DEFAULT_SCHEMA_VERSION = "1.0";

export interface MyceliumEventActor {
  id: string;
  /** "user" | "agent" | "service" | "bot" */
  type: string;
  display_name?: string;
}

export interface MyceliumEventObject {
  id: string;
  /** "pull_request" | "commit" | "message" | "ticket" | "file" | "service" | ... */
  type: string;
  url?: string;
}

export interface MyceliumEvent {
  id: string;
  /** e.g. "github.pr.opened", "slack.message.posted", "observer.command.run" */
  type: string;
  /** "github" | "slack" | "jira" | "observer" | "agent" | "api" | ... */
  source: string;
  actor: MyceliumEventActor;
  object: MyceliumEventObject;
  /** ISO 8601 timestamp */
  timestamp: string;

  /** Mandatory. Default "1.0". Bump on field changes. */
  schema_version: string;

  metadata: Record<string, unknown>;

  /** Mandatory. Groups related events into a stream partition. */
  correlation_id: string;
  /** Set when this event modifies/extends a prior event. */
  parent_correlation_id?: string | null;
}
