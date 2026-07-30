import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { MaterialDetail } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

// Rótulos de proveniência -- nunca deixar o usuário sem saber se um dado é sintético,
// documentado ou ainda não revisado (Prompt Mestre §3.1: honestidade técnica).
const REVIEW_STATUS_LABEL: Record<string, string> = {
  draft: "não revisado (rascunho)",
  reviewed: "revisado",
  deprecated: "obsoleto",
};

export function MaterialDetailPage() {
  const { materialId } = useParams<{ materialId: string }>();
  const { token } = useAuth();
  const [material, setMaterial] = useState<MaterialDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !materialId) return;
    let cancelled = false;
    client
      .getMaterial(token, materialId)
      .then((data) => {
        if (!cancelled) setMaterial(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao carregar material.");
      });
    return () => {
      cancelled = true;
    };
  }, [token, materialId]);

  if (error) return <AuthenticatedLayout><ErrorState message={error} /></AuthenticatedLayout>;
  if (!material) return <AuthenticatedLayout><Loading label="Carregando material…" /></AuthenticatedLayout>;

  return (
    <AuthenticatedLayout>
      <h1>{material.name}</h1>
      <p style={{ color: "var(--color-text-secondary)" }}>
        {material.category} — origem: {material.source_type === "synthetic" ? "sintética" : "literatura"} —{" "}
        <span data-testid="material-review-status">{REVIEW_STATUS_LABEL[material.review_status] ?? material.review_status}</span>
      </p>
      {material.source_type === "synthetic" && (
        <p style={{ color: "var(--color-warning, #9a6700)", fontSize: "0.9em" }}>
          Dado sintético: gerado para fins de desenvolvimento/demonstração, não extraído de uma fonte documentada.
        </p>
      )}
      {material.description && <p>{material.description}</p>}

      <h2>Propriedades</h2>
      {material.properties.length === 0 ? (
        <p>Nenhuma propriedade registrada.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={styles.th}>Propriedade</th>
              <th style={styles.th}>Valor</th>
              <th style={styles.th}>Unidade</th>
              <th style={styles.th}>Incerteza</th>
              <th style={styles.th}>Fonte</th>
              <th style={styles.th}>Método</th>
            </tr>
          </thead>
          <tbody>
            {material.properties.map((p) => (
              <tr key={p.id}>
                <td style={styles.td}>{p.property_name}</td>
                <td style={styles.td}>{p.value}</td>
                <td style={styles.td}>{p.unit}</td>
                <td style={styles.td}>
                  {p.uncertainty_low !== null && p.uncertainty_high !== null
                    ? `${p.uncertainty_low} – ${p.uncertainty_high}`
                    : "—"}
                </td>
                <td style={styles.td}>{p.source}</td>
                <td style={styles.td}>{p.method ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Referências</h2>
      {material.references.length === 0 ? (
        <p>Nenhuma referência registrada.</p>
      ) : (
        <ul>
          {material.references.map((r) => (
            <li key={r.id}>
              {r.citation_text}
              {r.doi && ` — DOI: ${r.doi}`}
            </li>
          ))}
        </ul>
      )}
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  th: { textAlign: "left", padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
};
