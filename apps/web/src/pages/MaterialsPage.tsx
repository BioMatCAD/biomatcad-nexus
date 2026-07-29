import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { MaterialSummary } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const SOURCE_LABEL: Record<string, string> = { synthetic: "sintético", literature: "literatura" };

export function MaterialsPage() {
  const { token } = useAuth();
  const [materials, setMaterials] = useState<MaterialSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    client
      .listMaterials(token)
      .then((data) => {
        if (!cancelled) setMaterials(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao carregar materiais.");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthenticatedLayout>
      <h1>Catálogo de materiais</h1>
      <p style={{ color: "var(--color-text-secondary)" }}>
        Todo valor científico registra unidade, fonte e método — nenhuma propriedade é inventada. Ver detalhes de
        cada material para a proveniência completa.
      </p>
      {error && <ErrorState message={error} />}
      {!error && materials === null && <Loading label="Carregando catálogo…" />}
      {!error && materials !== null && materials.length === 0 && (
        <EmptyState title="Nenhum material cadastrado ainda" description="O catálogo começa vazio neste incremento." />
      )}
      {!error && materials !== null && materials.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={styles.th}>Nome</th>
              <th style={styles.th}>Categoria</th>
              <th style={styles.th}>Origem</th>
              <th style={styles.th}>Revisão</th>
            </tr>
          </thead>
          <tbody>
            {materials.map((m) => (
              <tr key={m.id}>
                <td style={styles.td}>
                  <Link to={`/app/materials/${m.id}`}>{m.name}</Link>
                </td>
                <td style={styles.td}>{m.category}</td>
                <td style={styles.td}>
                  <span style={styles.badge}>{SOURCE_LABEL[m.source_type] ?? m.source_type}</span>
                </td>
                <td style={styles.td}>{m.review_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  th: { textAlign: "left", padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  badge: {
    fontSize: "0.75rem",
    background: "var(--color-border)",
    borderRadius: "var(--radius-sm)",
    padding: "2px 8px",
  },
};
