"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/ol", label: "Orchestrator" },
  { href: "/tasks", label: "Tasks" },
  { href: "/ingestion", label: "Ingestion" },
  { href: "/orchestration", label: "Orchestration (legacy)" },
  { href: "/agents", label: "Agents" },
  { href: "/settings", label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname() ?? "/";
  return (
    <aside className="sidebar">
      <h1>Mycelium</h1>
      <div className="tag">Agentic intelligence</div>
      <nav className="nav">
        {NAV.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={active ? "active" : ""}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
