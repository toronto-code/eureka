import { OLChatThread } from "../../components/OLChatThread";

export const dynamic = "force-dynamic";

export default function OLPage() {
  return (
    <main className="page ol-page">
      <div className="ol-center">
        <header className="ol-page-header">
          <h1>Orchestrator</h1>
        </header>
        <OLChatThread />
      </div>
    </main>
  );
}
