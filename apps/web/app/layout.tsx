import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/Sidebar";

import "./globals.css";

export const metadata: Metadata = {
  title: "Mycelium",
  description:
    "Agentic company intelligence — orchestrate GPT-4o agents around your Jira board safely.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <Sidebar />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
