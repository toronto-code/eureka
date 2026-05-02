interface Props {
  payload: Record<string, unknown> | null | undefined;
  title?: string;
}

export function AgentOutputViewer({ payload, title }: Props) {
  return (
    <div className="card">
      {title ? <h3>{title}</h3> : null}
      <pre>{JSON.stringify(payload ?? {}, null, 2)}</pre>
    </div>
  );
}
