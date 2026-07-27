interface EmptyStateProps {
  title: string;
  description?: string;
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div
      style={{
        padding: "var(--space-8)",
        textAlign: "center",
        color: "var(--color-text-secondary)",
        border: "1px dashed var(--color-border)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <p style={{ margin: 0, fontWeight: 600, color: "var(--color-text-primary)" }}>{title}</p>
      {description && <p style={{ margin: "var(--space-2) 0 0" }}>{description}</p>}
    </div>
  );
}
