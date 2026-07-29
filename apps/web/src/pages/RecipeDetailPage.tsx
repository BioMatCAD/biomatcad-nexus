import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { RecipeResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

export function RecipeDetailPage() {
  const { recipeId } = useParams<{ recipeId: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [recipe, setRecipe] = useState<RecipeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token || !recipeId) return;
    client
      .getRecipe(token, recipeId)
      .then(setRecipe)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar receita."));
  }, [token, recipeId]);

  const handleSubmitJob = async () => {
    if (!token || !recipe) return;
    setSubmitting(true);
    try {
      const designRun = await client.createDesignRun(token, {
        project_id: recipe.project_id,
        recipe_id: recipe.id,
        idempotency_key: `ui-${recipe.id}-${Date.now()}`,
      });
      navigate(`/app/jobs/${designRun.latest_job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao enviar job geométrico.");
    } finally {
      setSubmitting(false);
    }
  };

  if (error) return <AuthenticatedLayout><ErrorState message={error} /></AuthenticatedLayout>;
  if (!recipe) return <AuthenticatedLayout><Loading label="Carregando receita…" /></AuthenticatedLayout>;

  const d = recipe.canonical_json;

  return (
    <AuthenticatedLayout>
      <h1>{recipe.name}</h1>
      <table style={{ borderCollapse: "collapse" }}>
        <tbody>
          <tr><td style={styles.td}><strong>Versão</strong></td><td style={styles.td}>{recipe.version}</td></tr>
          <tr><td style={styles.td}><strong>Schema</strong></td><td style={styles.td}>{recipe.schema_version}</td></tr>
          <tr><td style={styles.td}><strong>Checksum</strong></td><td style={styles.td}><code>{recipe.checksum_sha256}</code></td></tr>
          <tr><td style={styles.td}><strong>Domínio</strong></td><td style={styles.td}>{d.domain.shape}</td></tr>
          <tr><td style={styles.td}><strong>Topologia</strong></td><td style={styles.td}>{d.topology.kind} (célula {d.topology.cell_size_mm}mm)</td></tr>
          <tr><td style={styles.td}><strong>Modo</strong></td><td style={styles.td}>{d.mode}</td></tr>
          <tr><td style={styles.td}><strong>Seed</strong></td><td style={styles.td}>{d.seed}</td></tr>
        </tbody>
      </table>

      <button type="button" onClick={handleSubmitJob} disabled={submitting} style={{ marginTop: "var(--space-4)" }}>
        {submitting ? "Enviando…" : "Enviar job geométrico"}
      </button>
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
};
