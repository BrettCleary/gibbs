const COLORS: Record<string, string> = {
  CREATED: "var(--text-dim)",
  RUNNING: "var(--accent)",
  PAUSED: "var(--warn)",
  COMPLETED: "var(--good)",
  FAILED: "var(--bad)",
  QUEUED: "var(--text-dim)",
  SUCCEEDED: "var(--good)",
};

export function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status] ?? "var(--text-dim)";
  return (
    <span
      className="mono inline-flex items-center gap-1.5 rounded-sm border px-1.5 py-0.5 text-[11px]"
      style={{ color, borderColor: color }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: color }}
      />
      {status}
    </span>
  );
}
