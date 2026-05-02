"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface Props {
  storageEnabled: boolean;
  savedInDatabase: boolean;
  secretHint: string | null;
}

export function GitHubPatStorage({
  storageEnabled,
  savedInDatabase,
  secretHint,
}: Props) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function savePat() {
    setMessage(null);
    if (!token.trim()) {
      setMessage("Paste a PAT first.");
      return;
    }
    setBusy(true);
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (setupToken.trim()) {
        headers["x-mycelium-setup-token"] = setupToken.trim();
      }
      const res = await fetch("/api/settings/github-pat", {
        method: "POST",
        headers,
        body: JSON.stringify({ token: token.trim() }),
      });
      const text = await res.text();
      if (!res.ok) {
        let detail = text;
        try {
          detail = JSON.parse(text).detail ?? text;
        } catch {
          /* raw text */
        }
        setMessage(typeof detail === "string" ? detail : JSON.stringify(detail));
        return;
      }
      setToken("");
      setMessage("Saved. The token is encrypted in Postgres; only a short hint is shown.");
      router.refresh();
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clearPat() {
    setMessage(null);
    setBusy(true);
    try {
      const headers: Record<string, string> = {};
      if (setupToken.trim()) {
        headers["x-mycelium-setup-token"] = setupToken.trim();
      }
      const res = await fetch("/api/settings/github-pat", {
        method: "DELETE",
        headers,
      });
      const text = await res.text();
      if (!res.ok) {
        setMessage(text);
        return;
      }
      setMessage("Stored PAT removed.");
      router.refresh();
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!storageEnabled) {
    return (
      <div className="card pat-card">
        <h3>Save GitHub PAT from the browser</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Add <code>MYCELIUM_CREDENTIALS_KEY</code> to the API environment (a Fernet key), restart the
          API, then reload this page. Generate a key with:
        </p>
        <pre className="pat-snippet">
          python -c &quot;from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())&quot;
        </pre>
        <p className="muted" style={{ marginBottom: 0 }}>
          Until then, use <code>GITHUB_TOKEN</code> in <code>.env</code> only — nothing is stored from the UI.
        </p>
      </div>
    );
  }

  return (
    <div className="card pat-card">
      <h3>Save GitHub PAT (encrypted)</h3>
      <p className="muted" style={{ marginTop: 0 }}>
        The PAT is encrypted with your server&apos;s <code>MYCELIUM_CREDENTIALS_KEY</code> before it is written to
        Postgres. It is never sent back to the browser. If <code>GITHUB_TOKEN</code> is set in the environment, it
        overrides the stored value.
      </p>
      {savedInDatabase && secretHint && (
        <p className="pat-hint-line">
          Stored token hint: <code>{secretHint}</code>
        </p>
      )}
      <label className="pat-label">
        Personal access token
        <input
          type="password"
          autoComplete="off"
          className="pat-input"
          placeholder="ghp_… or github_pat_…"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          disabled={busy}
        />
      </label>
      <label className="pat-label">
        Setup token (optional)
        <input
          type="password"
          autoComplete="off"
          className="pat-input"
          placeholder="Only if MYCELIUM_SETUP_TOKEN is set on the API"
          value={setupToken}
          onChange={(e) => setSetupToken(e.target.value)}
          disabled={busy}
        />
      </label>
      <div className="flex" style={{ gap: 10, flexWrap: "wrap", marginTop: 12 }}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void savePat()}>
          Save encrypted PAT
        </button>
        <button type="button" className="btn" disabled={busy || !savedInDatabase} onClick={() => void clearPat()}>
          Remove stored PAT
        </button>
      </div>
      {message && (
        <p className={message.startsWith("Saved") ? "pat-ok" : "pat-err"} style={{ marginTop: 12 }}>
          {message}
        </p>
      )}
    </div>
  );
}
