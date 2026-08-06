import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { ArtifactResponse, GeometryJobResponse, ManifestResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { StlViewer } from "../components/viewer/StlViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { useAuth } from "../context/AuthContext";
import { downloadArtifactAsFile, sanitizeFilename } from "../lib/artifactDownload";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const STATUS_LABEL: Record<string, string> = {
  queued: "Na fila",
  running: "Em execução",
  succeeded: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

/** Compara duas árvores de métricas numéricas rasas e retorna as chaves cujos valores
 * divergem -- usado para nunca escolher silenciosamente entre a métrica da API (job.metrics)
 * e a do manifesto (manifest.manifest_json.metrics), que deveriam sempre ser idênticas (o
 * manifesto é montado a partir do mesmo job.metrics no momento da conclusão do job). Uma
 * divergência real indicaria um bug de sincronização e deve ser mostrada, não escondida. */
function findMetricsDivergence(
  apiMetrics: Record<string, unknown> | null | undefined,
  manifestMetrics: unknown,
): string[] {
  if (!apiMetrics || typeof manifestMetrics !== "object" || manifestMetrics === null) return [];
  const divergent: string[] = [];
  const manifestObj = manifestMetrics as Record<string, unknown>;
  for (const key of Object.keys(apiMetrics)) {
    if (key in manifestObj && JSON.stringify(manifestObj[key]) !== JSON.stringify(apiMetrics[key])) {
      divergent.push(key);
    }
  }
  return divergent;
}

// data-testid documentados (usados pelo E2E Playwright em e2e/vertical.spec.ts, ver
// e2e/README.md): "job-status" (texto do status localizado, ex.: "Concluído"), "job-metrics"
// (tabela de métricas geométricas quando succeeded) e "stl-download-link" (botão de download do
// artefato STL especificamente, entre os artefatos listados).
export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [job, setJob] = useState<GeometryJobResponse | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactResponse[]>([]);
  const [manifest, setManifest] = useState<ManifestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [downloadingArtifactId, setDownloadingArtifactId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!token || !jobId) return;
    let cancelled = false;

    const stopPolling = () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    const poll = async () => {
      try {
        const current = await client.getJob(token, jobId);
        if (cancelled) return;
        setJob(current);
        if (TERMINAL_STATUSES.has(current.status)) {
          stopPolling();
          if (current.status === "succeeded") {
            const [artifactList, manifestData] = await Promise.all([
              client.listJobArtifacts(token, jobId),
              client.getJobManifest(token, jobId).catch(() => null),
            ]);
            if (!cancelled) {
              setArtifacts(artifactList);
              setManifest(manifestData);
            }
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao consultar job.");
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [token, jobId]);

  const handleCancel = async () => {
    if (!token || !jobId) return;
    setCancelling(true);
    try {
      const updated = await client.cancelJob(token, jobId);
      setJob(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cancelar job.");
    } finally {
      setCancelling(false);
    }
  };

  const handleRetry = async () => {
    if (!token || !job) return;
    setRetrying(true);
    try {
      // Retry controlado (Seção 2 do escopo): não reenvia silenciosamente -- cria uma nova
      // tentativa explícita via /design-runs/{id}/retry (mesma receita, novo attempt_number,
      // ver services/geometry_job_service.retry_job) e navega para o novo job resultante.
      const newJob = await client.retryDesignRun(token, job.design_run_id);
      navigate(`/app/jobs/${newJob.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao tentar novamente.");
    } finally {
      setRetrying(false);
    }
  };

  const handleDownloadArtifact = async (artifact: ArtifactResponse) => {
    setDownloadError(null);
    setDownloadingArtifactId(artifact.id);
    try {
      // Download autenticado real (Blob/ObjectURL) -- corrige o achado da auditoria (ver
      // docs/architecture/viewer-3d-audit.md): antes disto, o link de download era um <a href>
      // estático sem nenhum header de autenticação, que retornaria 401 contra um backend real.
      await downloadArtifactAsFile(
        client.artifactDownloadUrl(artifact.id),
        sanitizeFilename(`biomatcad-${artifact.kind}-${artifact.id.slice(0, 8)}.bin`),
        { token: isDemoMode ? undefined : (token ?? undefined), expectedSha256: artifact.sha256 },
      );
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Falha ao baixar artefato.");
    } finally {
      setDownloadingArtifactId(null);
    }
  };

  if (error) return <AuthenticatedLayout><ErrorState message={error} /></AuthenticatedLayout>;
  if (!job) return <AuthenticatedLayout><Loading label="Carregando job…" /></AuthenticatedLayout>;

  const stlArtifact = artifacts.find((a) => a.kind === "stl");
  const manifestJson = manifest?.manifest_json as Record<string, unknown> | undefined;
  const manifestMetrics = manifestJson?.metrics;
  const topologyProvider = manifestJson?.topology_provider as
    | { kind?: string; provider_class?: string | null; version?: string | null }
    | undefined;
  const recipeCanonical = manifestJson?.recipe_canonical as Record<string, unknown> | undefined;
  const seed = recipeCanonical?.seed;
  const mode = recipeCanonical?.mode;
  const voxelSize = (recipeCanonical?.resolution as Record<string, unknown> | undefined)?.voxel_size_mm;
  const metricsDivergence = findMetricsDivergence(
    job.metrics as unknown as Record<string, unknown> | null,
    manifestMetrics,
  );

  return (
    <AuthenticatedLayout>
      <h1>Job geométrico</h1>
      <p>
        Status: <strong data-testid="job-status">{STATUS_LABEL[job.status] ?? job.status}</strong>
        {job.status === "running" && ` (${job.progress_pct}%)`}
      </p>

      {job.status === "failed" && (
        <ErrorState message={`${job.error_code ?? "Erro"}: ${job.error_message ?? "Falha desconhecida no worker."}`} />
      )}

      {(job.status === "queued" || job.status === "running") && (
        <button type="button" onClick={handleCancel} disabled={cancelling}>
          {cancelling ? "Cancelando…" : "Cancelar job"}
        </button>
      )}

      {(job.status === "failed" || job.status === "cancelled") && (
        <button type="button" data-testid="job-retry-button" onClick={handleRetry} disabled={retrying}>
          {retrying ? "Reenviando…" : "Tentar novamente"}
        </button>
      )}

      {job.status === "succeeded" && job.metrics && (
        <>
          <h2>Métricas geométricas</h2>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.9em" }} data-testid="metrics-provenance-note">
            Resultado <strong>calculado</strong> pelo worker geométrico (PicoGK) a partir da receita enviada -- não
            constitui validação experimental. Nenhum ensaio físico foi realizado sobre esta geometria.
          </p>
          <table data-testid="job-metrics" style={{ borderCollapse: "collapse" }}>
            <tbody>
              <tr><td style={styles.td}><strong>Volume (mm³)</strong></td><td style={styles.td}>{job.metrics.volume_mm3}</td></tr>
              <tr><td style={styles.td}><strong>Porosidade medida (%)</strong></td><td style={styles.td}>{job.metrics.porosity_pct_measured}</td></tr>
              <tr><td style={styles.td}><strong>Área de superfície (mm²)</strong></td><td style={styles.td}>{job.metrics.surface_area_mm2}</td></tr>
              <tr><td style={styles.td}><strong>Vértices únicos (worker)</strong></td><td style={styles.td}>{job.metrics.vertex_count_unique}</td></tr>
              <tr><td style={styles.td}><strong>Triângulos (worker)</strong></td><td style={styles.td}>{job.metrics.triangle_count}</td></tr>
              <tr><td style={styles.td}><strong>Watertight</strong></td><td style={styles.td}>{job.metrics.is_watertight ? "sim" : "não"}</td></tr>
              <tr><td style={styles.td}><strong>Bounding box (mm)</strong></td><td style={styles.td}>{JSON.stringify(job.metrics.bounding_box_mm)}</td></tr>
            </tbody>
          </table>

          {job.metrics.site_count !== undefined && (
            <>
              <h2>Métricas específicas de Voronoi (voronoi_cell_edges_v1)</h2>
              <p style={{ color: "var(--color-text-secondary)", fontSize: "0.9em" }} data-testid="voronoi-metrics-provenance-note">
                Conectividade e contagens abaixo descrevem o grafo TOPOLÓGICO de nós/arestas da
                tesselação de Voronoi -- nunca conectividade biológica nem validação experimental.
              </p>
              <table data-testid="job-voronoi-metrics" style={{ borderCollapse: "collapse" }}>
                <tbody>
                  <tr><td style={styles.td}><strong>Sítios</strong></td><td style={styles.td}>{job.metrics.site_count}</td></tr>
                  <tr><td style={styles.td}><strong>Células de Delaunay</strong></td><td style={styles.td}>{job.metrics.delaunay_cell_count}</td></tr>
                  <tr><td style={styles.td}><strong>Células degeneradas</strong></td><td style={styles.td}>{job.metrics.degenerate_cell_count}</td></tr>
                  <tr><td style={styles.td}><strong>Células válidas</strong></td><td style={styles.td}>{job.metrics.valid_cell_count}</td></tr>
                  <tr><td style={styles.td}><strong>Nós</strong></td><td style={styles.td}>{job.metrics.node_count}</td></tr>
                  <tr><td style={styles.td}><strong>Arestas (total)</strong></td><td style={styles.td}>{job.metrics.edge_count}</td></tr>
                  <tr><td style={styles.td}><strong>Arestas internas</strong></td><td style={styles.td}>{job.metrics.internal_edge_count}</td></tr>
                  <tr><td style={styles.td}><strong>Arestas de raio de fronteira</strong></td><td style={styles.td}>{job.metrics.boundary_ray_edge_count}</td></tr>
                  <tr><td style={styles.td}><strong>Raios de fronteira descartados</strong></td><td style={styles.td}>{job.metrics.discarded_boundary_ray_count}</td></tr>
                  <tr><td style={styles.td}><strong>Arestas internas descartadas</strong></td><td style={styles.td}>{job.metrics.discarded_internal_edge_count}</td></tr>
                  <tr><td style={styles.td}><strong>Componentes conectados</strong></td><td style={styles.td}>{job.metrics.connected_component_count}</td></tr>
                  <tr><td style={styles.td}><strong>Nós isolados</strong></td><td style={styles.td}>{job.metrics.isolated_node_count}</td></tr>
                  <tr><td style={styles.td}><strong>Comprimento total dos struts (mm)</strong></td><td style={styles.td}>{job.metrics.total_strut_length_mm}</td></tr>
                  <tr><td style={styles.td}><strong>Comprimento médio dos struts (mm)</strong></td><td style={styles.td}>{job.metrics.mean_strut_length_mm}</td></tr>
                  <tr><td style={styles.td}><strong>Comprimento mín./máx. dos struts (mm)</strong></td><td style={styles.td}>{job.metrics.min_strut_length_mm} / {job.metrics.max_strut_length_mm}</td></tr>
                  <tr><td style={styles.td}><strong>Desvio-padrão do comprimento (mm)</strong></td><td style={styles.td}>{job.metrics.strut_length_stddev_mm}</td></tr>
                  <tr><td style={styles.td}><strong>Grau médio dos nós</strong></td><td style={styles.td}>{job.metrics.mean_node_degree}</td></tr>
                  <tr><td style={styles.td}><strong>Grau mín./máx. dos nós</strong></td><td style={styles.td}>{job.metrics.min_node_degree} / {job.metrics.max_node_degree}</td></tr>
                  <tr><td style={styles.td}><strong>Desvio-padrão do grau</strong></td><td style={styles.td}>{job.metrics.node_degree_stddev}</td></tr>
                  <tr>
                    <td style={styles.td}><strong>Contenção no domínio</strong></td>
                    <td style={styles.td} data-testid="voronoi-domain-containment">
                      {job.metrics.domain_containment_verified ? "verificada" : "VIOLAÇÃO DETECTADA"} (violação máx.:{" "}
                      {job.metrics.max_node_containment_violation_mm}mm)
                    </td>
                  </tr>
                </tbody>
              </table>
            </>
          )}

          {manifest && (
            <>
              <h2>Proveniência (manifesto de reprodutibilidade)</h2>
              {metricsDivergence.length > 0 ? (
                <p role="alert" data-testid="metrics-divergence-warning" style={styles.divergence}>
                  Inconsistência detectada entre as métricas da API e do manifesto nos campos:{" "}
                  {metricsDivergence.join(", ")}. Nenhum valor foi escolhido automaticamente -- verifique
                  manualmente antes de confiar nesta execução.
                </p>
              ) : (
                <p data-testid="metrics-consistency-ok" style={{ fontSize: "0.8rem", color: "var(--color-text-secondary)" }}>
                  Métricas da API e do manifesto conferem.
                </p>
              )}
              <table data-testid="job-provenance" style={{ borderCollapse: "collapse" }}>
                <tbody>
                  <tr><td style={styles.td}><strong>Provider de topologia</strong></td><td style={styles.td} data-testid="provenance-topology-provider">{topologyProvider?.kind ?? "?"} ({topologyProvider?.provider_class ?? "-"} v{topologyProvider?.version ?? "?"})</td></tr>
                  <tr><td style={styles.td}><strong>Seed</strong></td><td style={styles.td} data-testid="provenance-seed">{String(seed ?? "?")}</td></tr>
                  <tr><td style={styles.td}><strong>Modo</strong></td><td style={styles.td}>{String(mode ?? "?")}</td></tr>
                  <tr><td style={styles.td}><strong>Resolução (voxel, mm)</strong></td><td style={styles.td}>{String(voxelSize ?? "?")}</td></tr>
                  <tr><td style={styles.td}><strong>Versão do worker</strong></td><td style={styles.td}>{job.worker_version ?? "?"}</td></tr>
                  <tr><td style={styles.td}><strong>Versão do .NET</strong></td><td style={styles.td}>{job.dotnet_version ?? "?"}</td></tr>
                  <tr><td style={styles.td}><strong>Versão do PicoGK</strong></td><td style={styles.td}>{job.picogk_version ?? "?"}</td></tr>
                  <tr><td style={styles.td}><strong>SHA-256 do STL</strong></td><td style={styles.td}>{String(manifestJson?.stl_sha256 ?? "?")}</td></tr>
                  <tr><td style={styles.td}><strong>Status de revisão</strong></td><td style={styles.td}>não revisado (protótipo de pesquisa)</td></tr>
                </tbody>
              </table>
            </>
          )}

          <h2>Visualização 3D</h2>
          <StlViewer
            artifactUrl={stlArtifact ? client.artifactDownloadUrl(stlArtifact.id) : null}
            token={isDemoMode ? undefined : token}
            expectedSha256={stlArtifact?.sha256}
            declaredSizeBytes={stlArtifact?.size_bytes}
            demoLabel={isDemoMode ? "Demonstração sintética -- não é o resultado de uma execução real" : undefined}
          />

          <h2>Artefatos</h2>
          {downloadError && <ErrorState message={downloadError} />}
          <ul>
            {artifacts.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  data-testid={a.kind === "stl" ? "stl-download-link" : undefined}
                  onClick={() => handleDownloadArtifact(a)}
                  disabled={downloadingArtifactId === a.id}
                >
                  {downloadingArtifactId === a.id ? "Baixando…" : `${a.kind} (${a.size_bytes} bytes, sha256: ${a.sha256.slice(0, 12)}…)`}
                </button>
              </li>
            ))}
          </ul>

          {manifest && (
            <details>
              <summary>Manifesto de reprodutibilidade (completo)</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.75rem" }}>{JSON.stringify(manifest.manifest_json, null, 2)}</pre>
            </details>
          )}
        </>
      )}
    </AuthenticatedLayout>
  );
}

const styles: Record<string, React.CSSProperties> = {
  td: { padding: "var(--space-2)", borderBottom: "1px solid var(--color-border)" },
  divergence: {
    color: "var(--color-error)",
    border: "1px solid var(--color-error)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2)",
    fontSize: "0.85rem",
  },
};
