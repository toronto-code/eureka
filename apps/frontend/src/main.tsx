import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { App } from "./App";
import { Dashboard } from "./views/Dashboard";
import { Chat } from "./views/Chat";
import { AgentsActivity } from "./views/AgentsActivity";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);
root.render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<Dashboard />} />
          <Route path="chat" element={<Chat />} />
          <Route path="agents" element={<AgentsActivity />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
