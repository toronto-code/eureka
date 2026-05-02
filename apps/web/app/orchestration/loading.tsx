export default function OrchestrationLoading() {
  return (
    <div className="card" style={{ maxWidth: 480 }}>
      <div className="flex" style={{ gap: 14, alignItems: "center" }}>
        <div className="spinner" aria-hidden />
        <div>
          <strong>Loading orchestration</strong>
          <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
            Fetching run details from the API…
          </p>
        </div>
      </div>
    </div>
  );
}
