"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setInfo(null);
    setBusy(true);
    const result =
      mode === "signin"
        ? await signIn(email, password)
        : await signUp(email, password, displayName || undefined);
    setBusy(false);
    if (result.error) setErr(result.error);
    else if (mode === "signup") {
      setInfo(
        "Account created. If you're not redirected, your project still has email confirmation on — disable it in Auth → Providers → Email.",
      );
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-page)",
        padding: 24,
      }}
    >
      <form onSubmit={submit} className="card" style={{ width: 400, padding: 32 }}>
        <header style={{ marginBottom: 20 }}>
          <h1
            style={{
              fontFamily: "var(--brand-font)",
              fontSize: 26,
              fontWeight: 600,
              margin: 0,
              letterSpacing: "-0.4px",
              color: "var(--text-strong)",
            }}
          >
            Mycelium
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 6, margin: "6px 0 0" }}>
            {mode === "signin" ? "Sign in to continue." : "Create an account."}
          </p>
        </header>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {mode === "signup" && (
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Display name (optional)"
            />
          )}
          <input
            type="text"
            inputMode="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
          />
          <input
            type="text"
            required
            minLength={6}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (6+ chars)"
            style={{ WebkitTextSecurity: "disc" } as any}
          />

          {err && (
            <div
              style={{
                fontSize: 12,
                color: "var(--red)",
                padding: "8px 10px",
                background: "var(--red-soft)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              {err}
            </div>
          )}
          {info && (
            <div
              style={{
                fontSize: 12,
                color: "var(--accent)",
                padding: "8px 10px",
                background: "var(--accent-soft)",
                borderRadius: "var(--radius-sm)",
              }}
            >
              {info}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="btn btn-primary"
            style={{ marginTop: 4 }}
          >
            {busy ? "…" : mode === "signin" ? "Sign in" : "Sign up"}
          </button>

          <button
            type="button"
            onClick={() => {
              setMode(mode === "signin" ? "signup" : "signin");
              setErr(null);
              setInfo(null);
            }}
            style={{
              background: "transparent",
              color: "var(--text-muted)",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              textDecoration: "underline",
              padding: 4,
            }}
          >
            {mode === "signin" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
