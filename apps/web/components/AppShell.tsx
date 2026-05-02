"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { Sidebar } from "./Sidebar";
import { SessionRecorder } from "./SessionRecorder";
import { AuthProvider, useAuth } from "@/lib/auth";

const PUBLIC_PATHS = ["/login"];

function Inner({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const isPublic = PUBLIC_PATHS.includes(pathname);
  const { user, loading } = useAuth();

  if (isPublic) {
    return <>{children}</>;
  }
  if (loading) {
    return (
      <div className="app-shell">
        <main className="main" style={{ padding: 40, color: "#6b7280" }}>
          loading…
        </main>
      </div>
    );
  }
  if (!user) {
    return null; // AuthProvider redirects to /login
  }
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">{children}</main>
      <SessionRecorder />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Inner>{children}</Inner>
    </AuthProvider>
  );
}
