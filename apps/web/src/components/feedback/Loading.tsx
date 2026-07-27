interface LoadingProps {
  label?: string;
}

export function Loading({ label = "Carregando…" }: LoadingProps) {
  return (
    <div role="status" aria-live="polite" style={{ padding: "var(--space-6)", color: "var(--color-text-secondary)" }}>
      <span>{label}</span>
    </div>
  );
}
