import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { App } from "./App";
import { Dashboard } from "./views/Dashboard";
import { Chat } from "./views/Chat";
import { Observability } from "./views/Observability";
import { AgentsActivity } from "./views/AgentsActivity";
import { Login } from "./views/Login";
import { Orchestrator, Tasks, Ingestion, OrchestrationLegacy, Settings } from "./views/StubView";
import { AuthProvider, useAuth } from "./lib/auth";
import "./styles.css";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ padding: 40, color: "#6b7280", background: "#0a0a0a", height: "100vh" }}>loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><App /></Protected>}>
            <Route index element={<Dashboard />} />
            <Route path="chat" element={<Chat />} />
            <Route path="ol" element={<Orchestrator />} />
            <Route path="tasks" element={<Tasks />} />
            <Route path="ingestion" element={<Ingestion />} />
            <Route path="orchestration" element={<OrchestrationLegacy />} />
            <Route path="agents" element={<AgentsActivity />} />
            <Route path="observability" element={<Observability />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
);
