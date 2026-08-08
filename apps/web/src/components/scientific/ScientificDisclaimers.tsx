// Adendo de Interface Científica Mínima (Incremento 2.3, Rodada 2, Fase P) -- avisos de uso
// responsável exibidos permanentemente na interface científica. Nunca usa linguagem de
// recomendação clínica ou farmacêutica; nunca omitido condicionalmente.

export function ResearchOnlyDisclaimer() {
  return (
    <p role="note" style={styles.disclaimer}>
      Dados para pesquisa. Registros importados não equivalem a validação científica,
      farmacêutica ou clínica.
    </p>
  );
}

export function PubChemImportedDisclaimer() {
  return (
    <p role="note" style={styles.disclaimer}>
      Fonte externa importada. Exige curadoria antes de qualquer uso científico conclusivo.
    </p>
  );
}

export function SyntheticFixtureDisclaimer() {
  return (
    <p role="note" style={{ ...styles.disclaimer, ...styles.syntheticDisclaimer }}>
      Dado sintético de demonstração — não atribuído ao PubChem.
    </p>
  );
}

const styles: Record<string, React.CSSProperties> = {
  disclaimer: {
    margin: "var(--space-2) 0",
    padding: "var(--space-2) var(--space-3)",
    fontSize: "0.8rem",
    color: "var(--color-text-secondary)",
    background: "color-mix(in srgb, var(--color-warning) 10%, transparent)",
    border: "1px solid var(--color-warning)",
    borderRadius: "var(--radius-sm)",
  },
  syntheticDisclaimer: {
    background: "color-mix(in srgb, var(--color-text-secondary) 10%, transparent)",
    border: "1px dashed var(--color-border)",
  },
};
