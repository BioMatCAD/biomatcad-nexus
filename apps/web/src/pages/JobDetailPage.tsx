import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { ArtifactResponse, GeometryJobResponse, ManifestResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { StlViewer } from "../components/viewer/StlViewer";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { useAuth } from "../context/AuthContext";

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

// data-testid documentados (usados pelo E2E Playwright em e2e/vertical.spec.ts, ver
// e2e/README.md): "job-status" (texto do status localizado, ex.: "Concluído"), "job-metrics"
// (tabela de métricas geométricas quando succeeded) e "stl-download-link" (link de download do
// artefato STL especificamente, entre os artefatos listados).
export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { token } = useAuth();
  const [job, setJob] = useState<GeometryJobResponse | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactResponse[]>([]);
  const [manifest, setManifest] = useState<ManifestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

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

  if (error) return <AuthenticatedLayout><ErrorState message={error} /></AuthenticatedLayout>;
  if (!job) return <AuthenticatedLayout><Loading label="Carregando job…" /></AuthenticatedLayout>;

  const stlArtifact = artifacts.find((a) => a.kind === "stl");

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

      {job.status === "succeeded" && job.metrics && (
        <>
          <h2>Métricas geométricas</h2>
          <table data-testid="job-metrics" style={{ borderCollapse: "collapse" }}>
            <tbody>
              <tr><td style={styles.td}><strong>Volume (mm³)</strong></td><td style={styles.td}>{job.metrics.volume_mm3}</td></tr>
              <tr><td style={styles.td}><strong>Porosidade medida (%)</strong></td><td style={styles.td}>{job.metrics.porosity_pct_measured}</td></tr>
              <tr><td style={styles.td}><strong>Área de superfície (mm²)</strong></td><td style={styles.td}>{job.metrics.surface_area_mm2}</td></tr>
              <tr><td style={styles.td}><strong>Vértices únicos</strong></td><td style={styles.td}>{job.metrics.vertex_count_unique}</td></tr>
              <tr><td style={styles.td}><strong>Triângulos</strong></td><td style={styles.td}>{job.metrics.triangle_count}</td></tr>
              <tr><td style={styles.td}><strong>Watertight</strong></td><td style={styles.td}>{job.metrics.is_watertight ? "sim" : "não"}</td></tr>
            </tbody>
          </table>

          <h2>Visualização 3D</h2>
          <StlViewer stlUrl={stlArtifact ? client.artifactDownloadUrl(stlArtifact.id) : null} />

          <h2>Artefatos</h2>
          <ul>
            {artifacts.map((a) => (
              <li key={a.id}>
                <a
                  href={client.artifactDownloadUrl(a.id)}
                  download
                  data-testid={a.kind === "stl" ? "stl-download-link" : undefined}
                >
                  {a.kind} ({a.size_bytes} bytes, sha256: {a.sha256.slice(0, 12)}…)
                </a>
              </li>
            ))}
          </ul>

          {manifest && (
            <details>
              <summary>Manifesto de reprodutibilidade</summary>
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
};
