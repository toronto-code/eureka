import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export function Login() {
  const { user, loading, signIn, signUp } = useAuth();

  // If already signed in, bounce to the app immediately.
  if (!loading && user) {
    return <Navigate to="/" replace />;
  }

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
    if (result.error) {
      setErr(result.error);
    } else if (mode === "signup") {
      // If "Confirm email" is still on in Supabase, no session is created until
      // the user clicks the link. Tell them.
      setInfo("Account created. If you're not redirected in a moment, your project still has email confirmation on — disable it in Auth → Providers → Email.");
    }
  }

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#0a0a0a",
        color: "#e5e7eb",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
      }}
    >
      <form
        onSubmit={submit}
        style={{
          width: 360,
          padding: 28,
          background: "#0c0c0c",
          border: "1px solid #1f2937",
          borderRadius: 12,
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        <div style={{ marginBottom: 8 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>mycelium</h1>
          <p style={{ fontSize: 12, color: "#6b7280" }}>
            {mode === "signin" ? "Welcome back. Sign in to continue." : "Create an account."}
          </p>
        </div>

        {mode === "signup" && (
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Display name (optional)"
            style={inputStyle}
          />
        )}
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          style={inputStyle}
        />
        <input
          type="password"
          required
          minLength={6}
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password (6+ chars)"
          style={inputStyle}
        />

        {err && (
          <div style={{ fontSize: 11, color: "#fca5a5", padding: "6px 10px", background: "#1a0c0c", borderRadius: 6 }}>
            {err}
          </div>
        )}
        {info && (
          <div style={{ fontSize: 11, color: "#93c5fd", padding: "6px 10px", background: "#0c1120", borderRadius: 6 }}>
            {info}
          </div>
        )}

        <button
          type="submit"
          disabled={busy}
          style={{
            padding: "10px 14px",
            background: busy ? "#374151" : "#3b82f6",
            color: "white",
            border: "none",
            borderRadius: 8,
            cursor: busy ? "not-allowed" : "pointer",
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          {busy ? "…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>

        <button
          type="button"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setErr(null);
          }}
          style={{
            background: "transparent",
            color: "#9ca3af",
            border: "none",
            cursor: "pointer",
            fontSize: 12,
            textDecoration: "underline",
          }}
        >
          {mode === "signin" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "10px 12px",
  background: "#0a0a0a",
  border: "1px solid #1f2937",
  borderRadius: 8,
  color: "#e5e7eb",
  fontSize: 13,
};
