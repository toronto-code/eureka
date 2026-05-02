import Link from "next/link";

import { RiskBadge } from "@/components/RiskBadge";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TasksPage() {
  const tasks = await api.listTasks();

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Tasks</h2>
          <p>Jira-style tasks Mycelium can analyse with worker agents.</p>
        </div>
      </header>

      <div className="card">
        <h3>All tasks</h3>
        {tasks.length === 0 ? (
          <p className="muted">No tasks loaded yet.</p>
        ) : (
          <div className="list-card">
            {tasks.map((task) => (
              <Link
                href={`/tasks/${task.id}`}
                className="row"
                key={task.id}
                style={{ textDecoration: "none" }}
              >
                <div className="flex-col" style={{ gap: 4, flex: 1 }}>
                  <div className="flex" style={{ flexWrap: "wrap" }}>
                    <strong>{task.title}</strong>
                    <span className="badge badge-neutral">
                      {task.external_id ?? task.id.slice(0, 8)}
                    </span>
                    <span className="badge badge-purple">{task.status}</span>
                    {task.priority ? (
                      <span className="badge badge-neutral">{task.priority}</span>
                    ) : null}
                    <RiskBadge risk={task.risk_level} />
                    <span
                      className={`badge ${
                        task.approval_status === "REQUIRED"
                          ? "badge-amber"
                          : task.approval_status === "APPROVED"
                            ? "badge-green"
                            : task.approval_status === "REJECTED"
                              ? "badge-red"
                              : "badge-neutral"
                      }`}
                    >
                      Approval {task.approval_status.toLowerCase()}
                    </span>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {task.description?.slice(0, 200) ?? "No description."}
                  </div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    {task.assignee ?? "unassigned"} ·{" "}
                    {task.labels.join(", ") || "no labels"}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
