import type { ExecutedAction, ExecutionResultDto } from "@/lib/types";

interface Props {
  execution: ExecutionResultDto | null | undefined;
  actions: ExecutedAction[];
  jiraKey?: string | null;
}

function StatusBadge({ dryRun, errors }: { dryRun: boolean; errors: string[] }) {
  if (errors.length > 0) {
    return <span className="badge badge-red">Execution errors</span>;
  }
  if (dryRun) {
    return <span className="badge badge-amber">Dry run</span>;
  }
  return <span className="badge badge-green">Executed</span>;
}

export function ExecutionPanel({ execution, actions, jiraKey }: Props) {
  if (!execution) {
    if (actions.length === 0) {
      return null;
    }
    // Fall back to just showing recorded actions.
    return (
      <div className="card">
        <h3>Executed actions</h3>
        <ActionList actions={actions} />
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Autonomous execution</h3>
      <div className="flex" style={{ gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <StatusBadge dryRun={execution.dry_run} errors={execution.errors} />
        {jiraKey ? (
          <span className="badge badge-neutral">Jira {jiraKey}</span>
        ) : null}
        {execution.branch ? (
          <span className="badge badge-purple">branch {execution.branch}</span>
        ) : null}
        {execution.jira_transition ? (
          <span className="badge badge-neutral">
            moved to {execution.jira_transition}
          </span>
        ) : null}
      </div>
      <dl className="kv">
        <dt>Pull request</dt>
        <dd>
          {execution.pr_url ? (
            <a href={execution.pr_url} target="_blank" rel="noreferrer">
              {execution.pr_url}
            </a>
          ) : (
            <span className="muted">—</span>
          )}
          {execution.pr_number ? (
            <span className="faint" style={{ marginLeft: 6 }}>
              #{execution.pr_number}
            </span>
          ) : null}
        </dd>
        <dt>Jira comment</dt>
        <dd>
          {execution.jira_comment_url ? (
            <a
              href={execution.jira_comment_url}
              target="_blank"
              rel="noreferrer"
            >
              {execution.jira_comment_url}
            </a>
          ) : (
            <span className="muted">—</span>
          )}
        </dd>
        <dt>Base → head</dt>
        <dd>
          <code>{execution.base_branch ?? "—"}</code> →{" "}
          <code>{execution.branch ?? "—"}</code>
        </dd>
      </dl>

      {execution.skipped_reason ? (
        <p className="muted">Skipped: {execution.skipped_reason}</p>
      ) : null}

      {execution.file_changes.length > 0 ? (
        <>
          <div className="section-title" style={{ marginTop: 14 }}>
            Files written
          </div>
          <div className="list-card">
            {execution.file_changes.map((fc, i) => (
              <div className="row" key={`${fc.path}-${i}`}>
                <div className="flex-col" style={{ gap: 4 }}>
                  <div className="flex">
                    <strong>{fc.path}</strong>
                    {fc.operation ? (
                      <span className="badge badge-neutral">{fc.operation}</span>
                    ) : null}
                    {fc.safety_blocked ? (
                      <span className="badge badge-red">blocked</span>
                    ) : fc.dry_run ? (
                      <span className="badge badge-amber">dry-run</span>
                    ) : (
                      <span className="badge badge-green">committed</span>
                    )}
                  </div>
                  {fc.description ? (
                    <div className="muted" style={{ fontSize: 12 }}>
                      {fc.description}
                    </div>
                  ) : null}
                </div>
                {fc.html_url ? (
                  <a
                    href={fc.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="btn"
                  >
                    Open
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        </>
      ) : null}

      {execution.errors.length > 0 ? (
        <>
          <div className="section-title" style={{ marginTop: 14 }}>
            Errors
          </div>
          <ul>
            {execution.errors.map((e, i) => (
              <li key={i} className="muted">
                {e}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {actions.length > 0 ? (
        <>
          <div className="section-title" style={{ marginTop: 14 }}>
            Raw side-effect log
          </div>
          <ActionList actions={actions} />
        </>
      ) : null}
    </div>
  );
}

function ActionList({ actions }: { actions: ExecutedAction[] }) {
  return (
    <div className="list-card">
      {actions.map((a) => (
        <div className="row" key={a.id}>
          <div className="flex-col" style={{ gap: 4 }}>
            <div className="flex">
              <strong>
                {a.integration}.{a.action_type}
              </strong>
              <span
                className={`badge ${
                  a.error_message
                    ? "badge-red"
                    : a.dry_run
                      ? "badge-amber"
                      : "badge-green"
                }`}
              >
                {a.error_message ? "error" : a.dry_run ? "dry-run" : "executed"}
              </span>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              {a.summary}
            </div>
            {a.error_message ? (
              <div className="faint" style={{ fontSize: 11 }}>
                {a.error_message}
              </div>
            ) : null}
          </div>
          {a.target_url ? (
            <a
              href={a.target_url}
              target="_blank"
              rel="noreferrer"
              className="btn"
            >
              Open
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
}
