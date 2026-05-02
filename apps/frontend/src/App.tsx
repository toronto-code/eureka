import { Link, Outlet, useLocation } from "react-router-dom";

export function App() {
  const { pathname } = useLocation();
  const isChat = pathname.startsWith("/chat");
  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="brand">mycelium</h1>
        <nav>
          <Link to="/" className={!isChat ? "active" : ""}>Dashboard</Link>
          <Link to="/chat" className={isChat ? "active" : ""}>Chat</Link>
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
