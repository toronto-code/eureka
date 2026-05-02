/**
 * correlation_id helpers (TypeScript).
 *
 * Generation rules (priority order):
 *   1. Natural ID if one exists (PR number, Slack thread ID).
 *   2. hash(source + object_id + time_window) + uuid suffix.
 *   3. API assigns a fallback if the producer omits it.
 */

function timeWindowBucket(when: Date, windowSeconds = 60): number {
  return Math.floor(when.getTime() / 1000 / windowSeconds);
}

async function sha256Hex(data: string): Promise<string> {
  const enc = new TextEncoder().encode(data);
  const digest = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function uuid4Suffix(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 8);
}

export async function deriveCorrelationId(opts: {
  source: string;
  objectId: string;
  naturalId?: string | null;
  when?: Date;
  windowSeconds?: number;
}): Promise<string> {
  const { source, objectId, naturalId, when = new Date(), windowSeconds = 60 } = opts;

  if (naturalId) return `${source}:${naturalId}`;

  const bucket = timeWindowBucket(when, windowSeconds);
  const digest = (await sha256Hex(`${source}|${objectId}|${bucket}`)).slice(0, 16);
  return `${source}:${digest}:${uuid4Suffix()}`;
}
