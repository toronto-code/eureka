"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

type NavItem = {
  href: string;
  label: string;
  /** Render a thin divider above this item (used to separate Settings). */
  divider?: boolean;
};

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/ol", label: "Orchestrator" },
  { href: "/ingestion", label: "Ingestion" },
  { href: "/observability", label: "Observability" },
  { href: "/settings", label: "Settings", divider: true },
];

export function Sidebar() {
  const pathname = usePathname() ?? "/";
  return (
    <aside className="sidebar">
      <h1>Mycelium</h1>
      <nav className="nav">
        {NAV.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Fragment key={item.href}>
              {item.divider ? <div className="nav-divider" /> : null}
              <Link href={item.href} className={active ? "active" : ""}>
                {item.label}
              </Link>
            </Fragment>
          );
        })}
      </nav>
      <div className="sidebar-spacer" />
    </aside>
  );
}
