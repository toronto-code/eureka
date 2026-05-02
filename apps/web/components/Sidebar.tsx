"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";
import { useAuth } from "@/lib/auth";

type NavItem = {
  href: string;
  label: string;
  /** Render a thin divider above this item (used to separate Settings). */
  divider?: boolean;
};

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/team", label: "Team Web" },
  { href: "/ol", label: "Orchestrator" },
  { href: "/ingestion", label: "Ingestion" },
  { href: "/incoming", label: "Incoming Data" },
  { href: "/observability", label: "Observability" },
  { href: "/settings", label: "Settings", divider: true },
];

export function Sidebar() {
  const pathname = usePathname() ?? "/";
  const { user, signOut } = useAuth();
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
      <div
        style={{
          padding: "0 10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          fontSize: 11,
          color: "rgba(255,255,255,0.6)",
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {user?.email ?? "—"}
        </span>
        <button
          onClick={() => signOut()}
          style={{
            background: "transparent",
            border: "1px solid rgba(255,255,255,0.12)",
            color: "rgba(255,255,255,0.6)",
            padding: "5px 8px",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: 11,
            textAlign: "left",
          }}
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
