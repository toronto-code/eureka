import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";

export function App() {
  const { pathname } = useLocation();
  const { user, signOut } = useAuth();
  const isChat = pathname.startsWith("/chat");
  const isObs = pathname.startsWith("/observability");
  const isDash = !isChat && !isObs;
  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="brand">mycelium</h1>
        <nav>
          <Link to="/" className={isDash ? "active" : ""}>Dashboard</Link>
          <Link to="/chat" className={isChat ? "active" : ""}>Chat</Link>
          <Link to="/observability" className={isObs ? "active" : ""}>Observability</Link>
        </nav>
        <footer style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: "#9ca3af", marginTop: "auto" }}>
          <span>{user?.email}</span>
          <button
            onClick={signOut}
            style={{ background: "transparent", border: "1px solid #374151", color: "#9ca3af", padding: "4px 8px", borderRadius: 4, cursor: "pointer", fontSize: 11, textAlign: "left" }}
          >
            Sign out
          </button>
        </footer>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
