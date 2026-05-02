import { describe, expect, it } from "vitest";
import type { AgentTaskSummary } from "../api";
import { formatActivitySummary } from "./taskActivity";

function task(partial: Partial<AgentTaskSummary> & Pick<AgentTaskSummary, "status">): AgentTaskSummary {
  return {
    task_id: "t1",
    agent_id: "a1",
    agent_type: "project_orchestrator",
    correlation_id: "cid",
    parent_correlation_id: null,
    created_at: "",
    updated_at: "",
    result: null,
    error: null,
    ...partial,
  };
}

describe("formatActivitySummary", () => {
  it("describes queue and running states", () => {
    expect(formatActivitySummary(task({ status: "queued" }))).toContain("Queued");
    expect(formatActivitySummary(task({ status: "running" }))).toContain("Running");
  });

  it("summarizes orchestrator delegations", () => {
    const line = formatActivitySummary(
      task({
        status: "succeeded",
        agent_type: "project_orchestrator",
        result: {
          delegations: [
            { role: "research_agent", skill: "reasoning" },
            { role: "planner_agent", skill: "plan" },
          ],
        },
      }),
    );
    expect(line).toContain("Team run:");
    expect(line).toContain("reasoning");
    expect(line).toContain("plan");
  });
});
