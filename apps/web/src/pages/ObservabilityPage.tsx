import { useCallback, useEffect, useState } from "react";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { ComponentState, ObservabilityStatusResponse } from "../api/types";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

// Intervalo de atualização automática do painel -- não é um SLA nem uma promessa de tempo
// real, apenas uma frequência razoável de polling para uma tela de observabilidade local.
const REFRESH_INTERVAL_MS = 10_000;

const STATE_LABEL: Record<ComponentState, string> = {
  healthy: "saudável",
  degraded: "degradado",
  unavailable: "indisponível",
  stale: "atrasado",
  stopped: "parado",
  unknown: "desconhecido",
};

const STATE_COLOR: Record<ComponentState, string> = {
  healthy: "var(--color-success, #1a7f37)",
  degraded: "var(--color-warning, #9a6700)",
  unavailable: "var(--color-danger, #cf222e)",
  stale: "var(--color-warning, #9a6700)",
  stopped: "var(--color-danger, #cf222e)",
  unknown: "var(--color-text-secondary, #6e7781)",
};

function StateBadge({ state }: { state: ComponentState }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: "999px",
        fontSize: "0.85em",
        fontWeight: 600,
        color: "#fff",
        backgroundColor: STATE_COLOR[state],
      }}
    >
      {STATE_LABEL[state]}
    </span>
  );
}

function ComponentCard({
  title,
  state,
  detail,
  children,
}: {
  title: string;
  state: ComponentState;
  detail: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      style={{
        border: "1px solid var(--color-border, #d0d7de)",
        borderRadius: "var(--radius-md, 8px)",
        padding: "var(--space-4, 16px)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <strong>{title}</strong>
        <StateBadge state={state} />
      </div>
      <p style={{ margin: 0, color: "var(--color-text-secondary)", fontSize: "0.9em" }}>{detail}</p>
      {children}
    </div>
  );
}

export function ObservabilityPage() {
  const { token } = useAuth();
  const [data, setData] = useState<ObservabilityStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(() => {
    if (!token) return;
    client
      .observabilityStatus(token)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Falha ao consultar observabilidade.");
      })
      .finally(() => setIsLoading(false));
  }, [token]);

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [refresh]);

  return (
    <AuthenticatedLayout>
      <h1>Observabilidade</h1>
      <p style={{ color: "var(--color-text-secondary)" }}>
        Estado real dos componentes do BioMatCAD Nexus, atualizado a cada {REFRESH_INTERVAL_MS / 1000}s. Cada
        indicador vem de uma verificação real feita pela API no momento da consulta -- nenhum estado é
        assumido ou otimista. Ambiente de pesquisa: nenhuma prontidão clínica é alegada aqui.
      </p>

      {isLoading && <Loading label="Consultando /api/v1/observability/status…" />}
      {error && <ErrorState message={error} />}

      {data && (
        <>
          <p style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
            Última atualização: {new Date(data.generated_at).toLocaleString()}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: "var(--space-4, 16px)",
              marginTop: "var(--space-4, 16px)",
            }}
          >
            <ComponentCard title="API" state={data.api.state} detail={data.api.detail}>
              <p style={{ margin: "4px 0 0", fontSize: "0.85em" }}>
                versão {data.api.version} · ambiente {data.api.environment}
              </p>
            </ComponentCard>

            <ComponentCard title="Banco de dados (PostgreSQL)" state={data.database.state} detail={data.database.detail} />

            <ComponentCard title="Dispatcher" state={data.dispatcher.state} detail={data.dispatcher.detail}>
              {data.dispatcher.phase && (
                <p style={{ margin: "4px 0 0", fontSize: "0.85em" }}>
                  fase: {data.dispatcher.phase} · jobs processados: {data.dispatcher.jobs_processed_total ?? "—"}
                </p>
              )}
            </ComponentCard>

            <ComponentCard title="Worker PicoGK" state={data.worker.state} detail={data.worker.detail}>
              <p style={{ margin: "4px 0 0", fontSize: "0.85em" }}>
                binário compilado: {data.worker.binary_found ? "sim" : "não"}
                {data.worker.worker_version && ` · versão ${data.worker.worker_version}`}
              </p>
            </ComponentCard>

            <ComponentCard title="Fila" state={data.queue.state} detail={data.queue.detail}>
              <p style={{ margin: "4px 0 0", fontSize: "0.85em" }}>
                {data.queue.queued_count} na fila · {data.queue.processing_count} em execução
              </p>
            </ComponentCard>

            <ComponentCard title="Armazenamento de artefatos" state={data.storage.state} detail={data.storage.detail}>
              <p style={{ margin: "4px 0 0", fontSize: "0.85em", wordBreak: "break-all" }}>{data.storage.path}</p>
            </ComponentCard>
          </div>

          <section aria-label="Jobs ativos" style={{ marginTop: "var(--space-6, 24px)" }}>
            <h2>Jobs ativos (sua organização)</h2>
            {data.jobs_active.length === 0 ? (
              <p style={{ color: "var(--color-text-secondary)" }}>Nenhum job ativo no momento.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Job</th>
                    <th style={{ textAlign: "left" }}>Status</th>
                    <th style={{ textAlign: "left" }}>Progresso</th>
                    <th style={{ textAlign: "left" }}>Heartbeat</th>
                  </tr>
                </thead>
                <tbody>
                  {data.jobs_active.map((job) => (
                    <tr key={job.job_id}>
                      <td>{job.job_id}</td>
                      <td>{job.status}</td>
                      <td>{job.progress_pct}%</td>
                      <td>
                        {job.heartbeat_stale ? (
                          <span style={{ color: STATE_COLOR.stale }}>atrasado</span>
                        ) : (
                          job.heartbeat_at ?? "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section aria-label="Jobs falhos recentes" style={{ marginTop: "var(--space-6, 24px)" }}>
            <h2>Jobs falhos recentes (sua organização)</h2>
            {data.jobs_failed_recent.length === 0 ? (
              <p style={{ color: "var(--color-text-secondary)" }}>Nenhuma falha recente.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Job</th>
                    <th style={{ textAlign: "left" }}>Código</th>
                    <th style={{ textAlign: "left" }}>Mensagem (sanitizada)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.jobs_failed_recent.map((job) => (
                    <tr key={job.job_id}>
                      <td>{job.job_id}</td>
                      <td>{job.error_code ?? "—"}</td>
                      <td>{job.error_message ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </AuthenticatedLayout>
  );
}
