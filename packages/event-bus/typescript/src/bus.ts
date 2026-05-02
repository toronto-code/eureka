/**
 * Redis Streams-backed event bus (TypeScript).
 *
 * Mirrors the Python implementation. See ../README.md for the contract and
 * ../../../docs/contracts.md for the ordering guarantee.
 */

import { createHash } from "node:crypto";
import { Redis } from "ioredis";
import type { Topic } from "./topics.js";

const DEFAULT_PARTITIONS = 8;

export type Handler = (
  messageId: string,
  payload: Record<string, unknown>,
) => Promise<void>;

export interface EventBusConfig {
  redisUrl: string;
  partitions?: number;
  consumerGroup?: string;
}

export class EventBus {
  private readonly redis: Redis;
  private readonly partitions: number;
  readonly consumerGroup: string;

  constructor(cfg: EventBusConfig) {
    this.redis = new Redis(cfg.redisUrl, { maxRetriesPerRequest: null });
    this.partitions = cfg.partitions ?? DEFAULT_PARTITIONS;
    this.consumerGroup = cfg.consumerGroup ?? "mycelium";
  }

  private partitionKey(correlationId: string): number {
    const h = createHash("sha256").update(correlationId).digest();
    return h.readUInt32BE(0) % this.partitions;
  }

  private streamName(topic: Topic | string, correlationId: string): string {
    return `${topic}.p${this.partitionKey(correlationId)}`;
  }

  private allPartitionStreams(topic: Topic | string): string[] {
    return Array.from({ length: this.partitions }, (_, i) => `${topic}.p${i}`);
  }

  /**
   * Publish an event to a topic. The partition is selected by `correlationId`
   * (or `event.correlation_id` if not passed). Throws if neither is set.
   */
  async publish(
    topic: Topic | string,
    event: Record<string, unknown>,
    opts: { correlationId?: string } = {},
  ): Promise<string> {
    const cid =
      opts.correlationId ?? (event.correlation_id as string | undefined);
    if (!cid) {
      throw new Error(
        "EventBus.publish requires correlation_id (mandatory on every event)",
      );
    }

    const stream = this.streamName(topic, cid);
    const id = await this.redis.xadd(
      stream,
      "*",
      "payload",
      JSON.stringify(event),
      "correlation_id",
      cid,
    );
    return id ?? "";
  }

  async ensureGroup(topic: Topic | string, group: string): Promise<void> {
    for (const stream of this.allPartitionStreams(topic)) {
      try {
        await this.redis.xgroup("CREATE", stream, group, "0", "MKSTREAM");
      } catch (err) {
        if (!(err as Error).message.includes("BUSYGROUP")) throw err;
      }
    }
  }

  /** Long-running consumer loop. */
  async consume(
    topic: Topic | string,
    group: string,
    consumerName: string,
    handler: Handler,
    opts: { blockMs?: number; count?: number } = {},
  ): Promise<void> {
    const blockMs = opts.blockMs ?? 5000;
    const count = opts.count ?? 16;

    await this.ensureGroup(topic, group);
    const streams = this.allPartitionStreams(topic);

    while (true) {
      try {
        const args = [
          "GROUP",
          group,
          consumerName,
          "COUNT",
          String(count),
          "BLOCK",
          String(blockMs),
          "STREAMS",
          ...streams,
          ...streams.map(() => ">"),
        ];
        const response = (await (this.redis as any).xreadgroup(...args)) as
          | Array<[string, Array<[string, string[]]>]>
          | null;
        if (!response) continue;

        for (const [, messages] of response) {
          for (const [messageId, fields] of messages) {
            const payloadIdx = fields.indexOf("payload");
            const raw = payloadIdx >= 0 ? fields[payloadIdx + 1] : "{}";
            let payload: Record<string, unknown> = {};
            try {
              payload = JSON.parse(raw);
            } catch {
              await this.ack(topic, group, messageId);
              continue;
            }
            await handler(messageId, payload);
          }
        }
      } catch (err) {
        // log and back off
        await new Promise((r) => setTimeout(r, 250));
      }
    }
  }

  async ack(topic: Topic | string, group: string, messageId: string): Promise<void> {
    for (const stream of this.allPartitionStreams(topic)) {
      try {
        await this.redis.xack(stream, group, messageId);
      } catch {
        // continue
      }
    }
  }

  async retry(
    topic: Topic | string,
    group: string,
    messageId: string,
    consumerName = "retry",
    minIdleMs = 0,
  ): Promise<void> {
    for (const stream of this.allPartitionStreams(topic)) {
      try {
        await this.redis.xclaim(stream, group, consumerName, minIdleMs, messageId);
      } catch {
        // continue
      }
    }
  }

  async close(): Promise<void> {
    await this.redis.quit();
  }
}
