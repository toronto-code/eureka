import { Link, Outlet, useLocation } from "react-router-dom";

export function App() {
  const { pathname } = useLocation();
  const tab =
    pathname.startsWith("/chat") ? "chat" : pathname.startsWith("/agents") ? "agents" : "dash";
  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="brand">mycelium</h1>
        <nav>
          <Link to="/" className={tab === "dash" ? "active" : ""}>Dashboard</Link>
          <Link to="/chat" className={tab === "chat" ? "active" : ""}>Chat</Link>
          <Link to="/agents" className={tab === "agents" ? "active" : ""}>Agents</Link>
        </nav>
        <footer>
          <span className="dev-badge">DEV_MODE</span>
        </footer>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
