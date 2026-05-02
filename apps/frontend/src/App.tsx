import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";

interface NavItem {
  to: string;
  label: string;
  divider?: boolean;
  match?: (path: string) => boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", match: (p) => p === "/" },
  { to: "/chat", label: "Chat" },
  { to: "/ol", label: "Orchestrator" },
  { to: "/tasks", label: "Tasks" },
  { to: "/ingestion", label: "Ingestion" },
  { to: "/orchestration", label: "Orchestration (legacy)" },
  { to: "/agents", label: "Agents" },
  { to: "/observability", label: "Observability" },
  { to: "/settings", label: "Settings", divider: true },
];

export function App() {
  const { pathname } = useLocation();
  const { user, signOut } = useAuth();

  function isActive(item: NavItem) {
    if (item.match) return item.match(pathname);
    return pathname.startsWith(item.to);
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="brand">mycelium</h1>
        <nav className="nav" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {NAV.map((item, i) => (
            <div key={item.to}>
              {item.divider && (
                <div className="nav-divider" style={{ height: 1, background: "rgba(255,255,255,0.08)", margin: "12px 6px" }} />
              )}
              <Link to={item.to} className={isActive(item) ? "active" : ""}>
                {item.label}
              </Link>
            </div>
          ))}
        </nav>
        <div className="sidebar-spacer" style={{ flex: 1 }} />
        <footer style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11, color: "#9ca3af", padding: "0 10px" }}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {user?.email ?? "—"}
          </span>
          <button
            onClick={signOut}
            style={{
              background: "transparent",
              border: "1px solid rgba(255,255,255,0.12)",
              color: "#9ca3af",
              padding: "5px 8px",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 11,
              textAlign: "left",
            }}
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
