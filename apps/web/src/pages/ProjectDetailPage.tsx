import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { DesignRunResponse, ProjectResponse, RecipeResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const STATUS_LABEL: Record<string, string> = {
  queued: "na fila",
  running: "em execução",
  succeeded: "concluído",
  failed: "falhou",
  cancelled: "cancelado",
};

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [recipes, setRecipes] = useState<RecipeResponse[]>([]);
  const [designRuns, setDesignRuns] = useState<DesignRunResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !projectId) return;
    let cancelled = false;
    Promise.all([
      client.getProject(token, projectId),
      client.listRecipes(token, projectId),
      client.listDesignRunsForProject(token, projectId),
    ])
      .then(([p, r, d]) => {
        if (cancelled) return;
        setProject(p);
        setRecipes(r);
        setDesignRuns(d);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao carregar projeto.");
      });
    return () => {
      cancelled = true;
    };
  }, [token, projectId]);

  const handleRetry = async (designRunId: string) => {
    if (!token) return;
    setRetryingRunId(designRunId);
    try {
      const newJob = await client.retryDesignRun(token, designRunId);
      navigate(`/app/jobs/${newJob.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao tentar novamente.");
    } finally {
      setRetryingRunId(null);
    }
  };

  if (error) return <AuthenticatedLayout><ErrorState message={error} /></AuthenticatedLayout>;
  if (!project) return <AuthenticatedLayout><Loading label="Carregando projeto…" /></AuthenticatedLayout>;

  return (
    <AuthenticatedLayout>
      <h1>{project.name}</h1>
      {project.description && <p>{project.description}</p>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>Receitas</h2>
        <Link to={`/app/projects/${project.id}/recipes/new`}>
          <button type="button">Nova receita</button>
        </Link>
      </div>
      {recipes.length === 0 ? (
        <p>Nenhuma receita ainda.</p>
      ) : (
        <ul>
          {recipes.map((r) => (
            <li key={r.id}>
              <Link to={`/app/recipes/${r.id}`}>
                {r.name} (v{r.version})
              </Link>
            </li>
          ))}
        </ul>
      )}

      <h2>Histórico de execuções</h2>
      {designRuns.length === 0 ? (
        <p>Nenhuma execução ainda.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={styles.th}>Chave de idempotência</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Tentativa</th>
              <th style={styles.th}></th>
            </tr>
          </thead>
          <tbody>
            {designRuns.map((run) => (
              <tr key={run.id}>
                <td style={styles.td}>{run.idempotency_key}</td>
                <td style={styles.td}>{STATUS_LABEL[run.latest_job.status] ?? run.latest_job.status}</td>
                <td style={styles.td}>{run.latest_job.attempt_number}</td>
                <td style={styles.td}>
                  <Link to={`/app/jobs/${run.latest_job.id}`}>Ver job</Link>
                  {(run.latest_job.status === "failed" || run.latest_job.status === "cancelled") && (
                    <>
                      {" · "}
                      <button
                        type="button"
                        onClick={() => handleRetry(run.id)}
                        disabled={retryingRunId === run.id}
                        style={{ fontSize: "0.85em" }}
                      >
                        {retryingRunId === run.id ? "Reenviando…" : "Repetir"}
                      </button>
                    </>
                  )}
                </td>
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
};
