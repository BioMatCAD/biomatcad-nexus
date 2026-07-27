interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      style={{
        padding: "var(--space-4)",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-error)",
        color: "var(--color-error)",
        background: "color-mix(in srgb, var(--color-error) 8%, transparent)",
      }}
    >
      <p style={{ margin: 0 }}>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} style={{ marginTop: "var(--space-2)" }}>
          Tentar novamente
        </button>
      )}
    </div>
  );
}
