import { describe, expect, it } from "vitest";
import type { AgentTaskSummary } from "../api";
import { formatAgentReply } from "./agentReplyFormat";

function task(partial: Partial<AgentTaskSummary> & Pick<AgentTaskSummary, "status">): AgentTaskSummary {
  return {
    task_id: "t",
    agent_id: "a",
    agent_type: "chat",
    correlation_id: "c",
    parent_correlation_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    result: null,
    error: null,
    ...partial,
  };
}

describe("formatAgentReply", () => {
  it("returns error text for failed tasks", () => {
    expect(formatAgentReply(task({ status: "failed", error: "boom" }))).toBe("boom");
  });

  it("falls back when failed with no error", () => {
    expect(formatAgentReply(task({ status: "failed", error: null }))).toBe("Agent task failed.");
  });

  it("handles cancelled", () => {
    expect(formatAgentReply(task({ status: "cancelled" }))).toBe("Task was cancelled.");
  });

  it("extracts summary string from result", () => {
    expect(
      formatAgentReply(
        task({
          status: "succeeded",
          result: { summary: "hello" },
        }),
      ),
    ).toBe("hello");
  });

  it("json-encodes non-summary results", () => {
    expect(
      formatAgentReply(
        task({
          status: "succeeded",
          result: { foo: 1 },
        }),
      ),
    ).toBe(JSON.stringify({ foo: 1 }));
  });
});
