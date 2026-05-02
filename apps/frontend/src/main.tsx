import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { App } from "./App";
import { Dashboard } from "./views/Dashboard";
import { Chat } from "./views/Chat";
import { Observability } from "./views/Observability";
import { Login } from "./views/Login";
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
            <Route path="observability" element={<Observability />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
);
