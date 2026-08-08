import type { CurationState, EvidenceType } from "../../api/types";

// Adendo de Interface Científica Mínima (Fase M/N) -- rótulos SEMPRE explícitos do estado de
// curadoria/importação. Nunca traduzir "calculated" como "validado" (restrição explícita da
// Fase N) -- cada EvidenceType tem um rótulo literal e neutro, nunca uma palavra que implique
// validação além do que o dado realmente é.

export const REVIEW_STATUS_LABEL: Record<CurationState, string> = {
  draft: "não revisado (draft)",
  reviewed: "revisado",
  rejected: "rejeitado",
};

const REVIEW_STATUS_COLOR: Record<CurationState, string> = {
  draft: "var(--color-warning)",
  reviewed: "var(--color-success)",
  rejected: "var(--color-error)",
};

export function ReviewStatusBadge({ status }: { status: CurationState }) {
  return (
    <span
      data-testid="review-status-badge"
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "#fff",
        backgroundColor: REVIEW_STATUS_COLOR[status],
      }}
    >
      {REVIEW_STATUS_LABEL[status]}
    </span>
  );
}

// "imported" é sempre verdadeiro para qualquer entidade com origem em conector externo
// (identificador em um namespace de conector, ex. pubchem_cid) -- rótulo adicional,
// independente do review_status, para nunca deixar implícito que algo "revisado" também já
// foi importado de fora sem checagem humana adicional.
export function ImportedBadge() {
  return (
    <span
      data-testid="imported-badge"
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "var(--color-text-primary)",
        background: "var(--color-border)",
      }}
    >
      importado
    </span>
  );
}

export function NeedsReviewBadge() {
  return (
    <span
      data-testid="needs-review-badge"
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "#fff",
        background: "var(--color-warning)",
      }}
    >
      precisa de revisão
    </span>
  );
}

// Rótulos literais de EvidenceType -- NUNCA "validado"/"comprovado" para "calculated". Cada
// rótulo descreve o TIPO de evidência, não seu grau de confiabilidade.
export const EVIDENCE_TYPE_LABEL: Record<EvidenceType, string> = {
  experimental: "experimental",
  calculated: "calculado (não é medição experimental)",
  supplier_declared: "declarado por fornecedor",
  literature_reported: "reportado em literatura",
  inferred: "inferido",
  synthetic: "sintético de demonstração",
};

export function EvidenceTypeBadge({ evidenceType }: { evidenceType: EvidenceType }) {
  return (
    <span
      data-testid="evidence-type-badge"
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "999px",
        fontSize: "0.75rem",
        background: "var(--color-border)",
        color: "var(--color-text-primary)",
      }}
    >
      {EVIDENCE_TYPE_LABEL[evidenceType]}
    </span>
  );
}
