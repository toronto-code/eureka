/**
 * GitHub bot onboarding links + env hints (PAT may also be stored encrypted via Settings).
 */
export function GitHubBotSetup({ githubConfigured }: { githubConfigured: boolean }) {
  return (
    <div className="card">
      <h3>Connect GitHub and configure the bot</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        Create a{" "}
        <strong>dedicated bot GitHub account</strong>, add it as a collaborator on the target repo,
        then paste its PAT into <code>GITHUB_TOKEN</code> <strong>or</strong> use{" "}
        <strong>Save GitHub PAT</strong> above (encrypted in Postgres). Set{" "}
        <code>GITHUB_OWNER</code> (or <code>GITHUB_ORG</code>), <code>GITHUB_REPO</code>, and restart
        the API container when changing env vars.
      </p>
      <div className="flex" style={{ gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <a
          className="btn btn-primary"
          href="https://github.com/settings/personal-access-tokens"
          target="_blank"
          rel="noreferrer"
        >
          GitHub token settings
        </a>
        <a
          className="btn"
          href="https://github.com/new"
          target="_blank"
          rel="noreferrer"
        >
          Create a repo (optional)
        </a>
        <a
          className="btn"
          href="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens"
          target="_blank"
          rel="noreferrer"
        >
          PAT documentation
        </a>
      </div>
      <div className="section-title">Wire dry-run vs live writes</div>
      <ul className="muted" style={{ marginTop: 8 }}>
        <li>
          <code>MYCELIUM_ALLOW_REAL_GITHUB=false</code> keeps commits/PRs simulated even with a token.
        </li>
        <li>
          Set <code>MYCELIUM_ALLOW_REAL_GITHUB=true</code> only after you trust the bot account + repo.
        </li>
        <li>
          Assign Jira tickets to <code>MYCELIUM_BOT_JIRA_USER</code> for autonomous execution (see README).
        </li>
      </ul>
      <p className="muted" style={{ marginBottom: 0 }}>
        Integration status (above): GitHub is{" "}
        <strong>{githubConfigured ? "configured for repo reads" : "not configured"}</strong>.
        Restart services after editing <code>.env</code>.
      </p>
    </div>
  );
}
