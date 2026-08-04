export function PlotViewer({ plots }: { plots: string[] }) {
  if (plots.length === 0) {
    return <p className="p-4 text-sm text-[var(--muted)]">실행하면 그래프가 여기에 표시됩니다.</p>;
  }
  return (
    <div className="flex flex-col gap-3 p-3">
      {plots.map((b64, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img key={i} src={`data:image/png;base64,${b64}`} alt={`plot-${i}`} className="max-w-full rounded-lg border border-[var(--border)] bg-white" />
      ))}
    </div>
  );
}
