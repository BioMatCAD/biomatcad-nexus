import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { MaterialSummary, RecipeResponse } from "../api/types";
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
  const [materials, setMaterials] = useState<MaterialSummary[]>([]);
  const [materialId, setMaterialId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token || !recipeId) return;
    client
      .getRecipe(token, recipeId)
      .then(setRecipe)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar receita."));
  }, [token, recipeId]);

  useEffect(() => {
    // Seleção de material é opcional -- a ausência do catálogo (ou falha ao carregá-lo) nunca
    // deve impedir o envio do job, apenas deixa a associação material x job de fora.
    if (!token) return;
    client
      .listMaterials(token)
      .then(setMaterials)
      .catch(() => setMaterials([]));
  }, [token]);

  const handleSubmitJob = async () => {
    if (!token || !recipe) return;
    setSubmitting(true);
    try {
      const designRun = await client.createDesignRun(token, {
        project_id: recipe.project_id,
        recipe_id: recipe.id,
        material_id: materialId || null,
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
          <tr>
            <td style={styles.td}><strong>Topologia</strong></td>
            <td style={styles.td}>
              {d.topology.kind === "gyroid"
                ? `gyroid (célula ${d.topology.cell_size_mm}mm, parede ${d.topology.wall_thickness_mm}mm)`
                : `voronoi_cell_edges_v1 (${d.topology.site_count} sítios, ${d.topology.distribution}, strut ${d.topology.strut_radius_mm}mm)`}
            </td>
          </tr>
          <tr><td style={styles.td}><strong>Modo</strong></td><td style={styles.td}>{d.mode}</td></tr>
          <tr><td style={styles.td}><strong>Seed</strong></td><td style={styles.td}>{d.seed}</td></tr>
        </tbody>
      </table>

      <label htmlFor="job-material-select" style={{ display: "block", marginTop: "var(--space-4)" }}>
        Material associado ao job (opcional)
        <select
          id="job-material-select"
          value={materialId}
          onChange={(e) => setMaterialId(e.target.value)}
          style={{ display: "block", marginTop: "var(--space-1)" }}
        >
          <option value="">Nenhum material específico</option>
          {materials.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.source_type === "synthetic" ? "sintético" : "literatura"})
            </option>
          ))}
        </select>
      </label>

      <button type="button" onClick={handleSubmitJob} disabled={submitting} style={{ marginTop: "var(--space-3)" }}>
        {submitting ? "Enviando…" : "Enviar job geométrico"}
      </button>
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
};
