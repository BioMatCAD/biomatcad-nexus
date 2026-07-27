// Prompt Mestre §3.3: "o modo Pages deve... identificação inequívoca de que o Pages não aceita
// dados clínicos reais". Este banner é renderizado sempre que __BIOMATCAD_DEMO_MODE__ é true.
export function DemoBanner() {
  if (!__BIOMATCAD_DEMO_MODE__) return null;

  return (
    <div
      role="alert"
      style={{
        background: "var(--color-warning)",
        color: "#1f1400",
        padding: "var(--space-2) var(--space-4)",
        textAlign: "center",
        fontSize: "0.875rem",
        fontWeight: 600,
      }}
    >
      Modo demonstração (GitHub Pages) — dados exclusivamente sintéticos. Este ambiente NÃO aceita
      e não deve receber dados de pacientes reais nem informações clínicas reais.
    </div>
  );
}
