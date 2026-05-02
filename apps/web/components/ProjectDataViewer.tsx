import type { ProjectDataPreview } from "@/lib/types";

export function ProjectDataViewer({ data }: { data: ProjectDataPreview }) {
  return (
    <div className="card">
      <h3>Project data preview</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        This is the seeded `project_data` the orchestrator would receive.
      </p>
      <dl className="kv">
        <dt>User goal</dt>
        <dd>{data.user_goal ?? "—"}</dd>
        <dt>Jira tasks</dt>
        <dd>{data.jira_tasks.length}</dd>
        <dt>Repos</dt>
        <dd>{data.github_repositories.length}</dd>
        <dt>Code files</dt>
        <dd>{data.code_files.length}</dd>
        <dt>Docs</dt>
        <dd>{data.docs.length}</dd>
        <dt>Transcripts</dt>
        <dd>{data.transcripts.length}</dd>
        <dt>Previous runs</dt>
        <dd>{data.previous_agent_runs.length}</dd>
        <dt>Constraints</dt>
        <dd>
          {data.constraints.length === 0
            ? "—"
            : data.constraints.map((c) => <div key={c}>{c}</div>)}
        </dd>
        <dt>Available tools</dt>
        <dd>{data.available_tools.join(", ") || "—"}</dd>
      </dl>
    </div>
  );
}
