"use client";

import { useState, type ReactNode } from "react";

type Tab = "run" | "history";

interface Props {
  runPanel: ReactNode;
  historyPanel: ReactNode;
}

export function OLPageTabs({ runPanel, historyPanel }: Props) {
  const [tab, setTab] = useState<Tab>("run");
  return (
    <div className="ol-tabs">
      <div className="ol-tabs-bar">
        <button
          type="button"
          className={`ol-tab ${tab === "run" ? "active" : ""}`}
          onClick={() => setTab("run")}
        >
          Run
        </button>
        <button
          type="button"
          className={`ol-tab ${tab === "history" ? "active" : ""}`}
          onClick={() => setTab("history")}
        >
          History
        </button>
      </div>
      <div className="ol-tab-panel">
        {tab === "run" ? runPanel : historyPanel}
      </div>
    </div>
  );
}
