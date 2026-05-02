import Link from "next/link";

import { api } from "@/lib/api";
import type {
  IncomingGitHubCommit,
  IncomingGitHubIssue,
  IncomingGitHubPR,
  IncomingGitHubRepo,
  IncomingJiraIssue,
  IncomingObserverEvent,
  IncomingSlackMessage,
  IncomingSourceSummary,
} from "@/lib/types";

export const dynamic = "force-dynamic";

function SourceHeader({
  label,
  summary,
  settingsHash,
}: {
  label: string;
  summary: IncomingSourceSummary | undefined;
  settingsHash?: string;
}) {
  const ok = summary?.ok ?? false;
  const configured = summary?.configured ?? false;
  const count = summary?.item_count ?? 0;

  const badge = !configured
    ? { cls: "badge-amber", label: "not configured" }
    : ok
      ? { cls: "badge-green", label: `${count} items` }
      : { cls: "badge-red", label: "error" };

  return (
    <div className="flex" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
      <div className="flex" style={{ gap: 8, alignItems: "center" }}>
        <h3 style={{ margin: 0 }}>{label}</h3>
        <span className={`badge ${badge.cls}`}>{badge.label}</span>
      </div>
      {!configured ? (
        <Link
          href={settingsHash ? `/settings#${settingsHash}` : "/settings"}
          className="btn btn-ghost"
          style={{ fontSize: 12 }}
        >
          Configure →
        </Link>
      ) : null}
    </div>
  );
}

function EmptyRow({ reason }: { reason: string | null | undefined }) {
  return (
    <div className="empty-state" style={{ padding: "14px 10px" }}>
      <p style={{ margin: 0 }}>{reason ?? "No data yet."}</p>
    </div>
  );
}

export default async function IncomingPage() {
  const data = await api.incomingOverview();
  const fetchedAt = new Date(data.fetched_at).toLocaleString();

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>Incoming Data</h2>
          <p>
            Live window into what the agents pull from your integrations on
            every turn. Use this to confirm the orchestrator is seeing real
            context — if a source is empty, wire it up in{" "}
            <Link href="/settings">Settings</Link>.
          </p>
        </div>
        <div className="faint" style={{ fontSize: 12 }}>
          fetched {fetchedAt}
        </div>
      </header>

      <div className="card">
        <SourceHeader label="GitHub" summary={data.summary.github} />
        {!data.summary.github?.configured ? (
          <EmptyRow reason={data.summary.github?.reason} />
        ) : (
          <GitHubPanel
            repos={data.github.repos}
            commits={data.github.commits}
            prs={data.github.prs}
            issues={data.github.issues}
          />
        )}
      </div>

      <div className="card">
        <SourceHeader label="Jira" summary={data.summary.jira} />
        {!data.summary.jira?.configured ? (
          <EmptyRow reason={data.summary.jira?.reason} />
        ) : data.jira.issues.length === 0 ? (
          <EmptyRow reason="No issues returned. Check JQL and project visibility." />
        ) : (
          <JiraPanel issues={data.jira.issues} />
        )}
      </div>

      <div className="card">
        <SourceHeader label="Slack" summary={data.summary.slack} />
        {!data.summary.slack?.configured ? (
          <EmptyRow reason={data.summary.slack?.reason} />
        ) : data.slack.messages.length === 0 ? (
          <EmptyRow reason="Bot isn't in any public channels yet, or none have recent messages." />
        ) : (
          <SlackPanel messages={data.slack.messages} />
        )}
      </div>

      <div className="card">
        <SourceHeader label="Local git observer" summary={data.summary.observer} />
        {data.observer.events.length === 0 ? (
          <EmptyRow reason={data.summary.observer?.reason} />
        ) : (
          <ObserverPanel events={data.observer.events} />
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- */
/* Panels                                                                 */
/* --------------------------------------------------------------------- */

function GitHubPanel({
  repos,
  commits,
  prs,
  issues,
}: {
  repos: IncomingGitHubRepo[];
  commits: IncomingGitHubCommit[];
  prs: IncomingGitHubPR[];
  issues: IncomingGitHubIssue[];
}) {
  return (
    <div className="flex-col" style={{ gap: 16 }}>
      {repos.length > 0 ? (
        <div>
          <div className="section-title">Repositories ({repos.length})</div>
          <div className="flex" style={{ gap: 6, flexWrap: "wrap" }}>
            {repos.map((r) => (
              <span key={`${r.owner}/${r.name}`} className="badge badge-neutral">
                {r.owner}/{r.name}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <div className="section-title">Recent commits ({commits.length})</div>
        {commits.length === 0 ? (
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            No commits.
          </p>
        ) : (
          <div className="list-card">
            {commits.slice(0, 10).map((c, i) => (
              <div className="row" key={i}>
                <div className="flex-col" style={{ gap: 2, minWidth: 0 }}>
                  <div
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <strong>{c.repo}</strong>{" "}
                    <span className="muted">{c.message}</span>
                  </div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    {c.author ?? "unknown"} ·{" "}
                    {c.date ? new Date(c.date).toLocaleString() : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="section-title">Pull requests ({prs.length})</div>
        {prs.length === 0 ? (
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            No pull requests.
          </p>
        ) : (
          <div className="list-card">
            {prs.slice(0, 10).map((p, i) => (
              <div className="row" key={i}>
                <div className="flex-col" style={{ gap: 2, minWidth: 0 }}>
                  <div
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <strong>
                      {p.repo}#{p.number}
                    </strong>{" "}
                    <span className="muted">{p.title}</span>
                  </div>
                  <div className="flex" style={{ gap: 6, fontSize: 11 }}>
                    <span
                      className={`badge ${p.merged ? "badge-purple" : p.state === "open" ? "badge-green" : "badge-neutral"}`}
                    >
                      {p.merged ? "merged" : p.state}
                    </span>
                    <span className="faint">{p.author ?? "unknown"}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="section-title">Issues ({issues.length})</div>
        {issues.length === 0 ? (
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            No issues.
          </p>
        ) : (
          <div className="list-card">
            {issues.slice(0, 10).map((iss, i) => (
              <div className="row" key={i}>
                <div className="flex-col" style={{ gap: 2, minWidth: 0 }}>
                  <div
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <strong>
                      {iss.repo}#{iss.number}
                    </strong>{" "}
                    <span className="muted">{iss.title}</span>
                  </div>
                  <div className="flex" style={{ gap: 6, fontSize: 11 }}>
                    <span
                      className={`badge ${iss.state === "open" ? "badge-green" : "badge-neutral"}`}
                    >
                      {iss.state}
                    </span>
                    <span className="faint">
                      {iss.assignee ? `assigned ${iss.assignee}` : "unassigned"}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function JiraPanel({ issues }: { issues: IncomingJiraIssue[] }) {
  return (
    <div className="list-card">
      {issues.slice(0, 15).map((j) => (
        <div className="row" key={j.key}>
          <div className="flex-col" style={{ gap: 2, minWidth: 0 }}>
            <div
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              <strong>{j.key}</strong>{" "}
              <span className="muted">{j.summary ?? "(no summary)"}</span>
            </div>
            <div className="flex" style={{ gap: 6, fontSize: 11 }}>
              {j.status ? (
                <span className="badge badge-neutral">{j.status}</span>
              ) : null}
              {j.priority ? (
                <span className="badge badge-neutral">{j.priority}</span>
              ) : null}
              {j.type ? (
                <span className="badge badge-neutral">{j.type}</span>
              ) : null}
              <span className="faint">{j.assignee}</span>
              {j.updated ? (
                <span className="faint">
                  · {new Date(j.updated).toLocaleDateString()}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SlackPanel({ messages }: { messages: IncomingSlackMessage[] }) {
  const JOIN_RE = /(joined #|has joined|<@.+> joined)/i;
  const visible = messages
    .filter((m) => (m.text ?? "").trim() && !JOIN_RE.test(m.text ?? ""))
    .slice(0, 15);

  if (visible.length === 0) {
    return (
      <EmptyRow reason="All recent messages were system/join notices." />
    );
  }

  return (
    <div className="list-card">
      {visible.map((m, i) => (
        <div className="row" key={`${m.ts}-${i}`}>
          <div className="flex-col" style={{ gap: 2, minWidth: 0, flex: 1 }}>
            <div className="flex" style={{ gap: 6, fontSize: 11 }}>
              <strong>#{m.channel}</strong>
              <span className="faint">{m.user}</span>
              {m.thread_ts && m.thread_ts !== m.ts ? (
                <span className="badge badge-neutral">reply</span>
              ) : null}
              {m.files && m.files.length > 0 ? (
                <span className="badge badge-purple">
                  {m.files.length} file{m.files.length === 1 ? "" : "s"}
                </span>
              ) : null}
            </div>
            <div
              className="muted"
              style={{
                fontSize: 12,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {m.text}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ObserverPanel({ events }: { events: IncomingObserverEvent[] }) {
  return (
    <div className="list-card">
      {events.slice(0, 15).map((e, i) => (
        <div className="row" key={i}>
          <div className="flex-col" style={{ gap: 2, minWidth: 0 }}>
            <div className="flex" style={{ gap: 6, fontSize: 12 }}>
              <span className="badge badge-neutral">{e.type}</span>
              <strong>{e.actor ?? "—"}</strong>
              <span className="faint">{e.object ?? ""}</span>
            </div>
            <div className="faint" style={{ fontSize: 11 }}>
              {e.timestamp ? new Date(e.timestamp).toLocaleString() : ""}
              {e.source ? ` · ${e.source}` : ""}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
