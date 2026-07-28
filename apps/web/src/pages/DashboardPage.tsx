import { useEffect, useState } from "react";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { Loading } from "../components/feedback/Loading";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { VersionResponse } from "../api/types";
import { useSystemStatus } from "../context/SystemStatusContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

export function DashboardPage() {
  const { status, isLoading: statusLoading, error: statusError } = useSystemStatus();
  const [version, setVersion] = useState<VersionResponse | null>(null);
  const [versionError, setVersionError] = useState<string | null>(null);
  const [versionLoading, setVersionLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    client
      .version()
      .then((v) => {
        if (!cancelled) setVersion(v);
      })
      .catch((err) => {
        if (!cancelled) setVersionError(err instanceof Error ? err.message : "Falha ao consultar versão da API.");
      })
      .finally(() => {
        if (!cancelled) setVersionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AuthenticatedLayout>
      <h1>Painel inicial</h1>
      <p style={{ color: "var(--color-text-secondary)" }}>
        Este dashboard mostra apenas o que está de fato implementado: estado operacional e
        versão da API. Projetos, jobs de cálculo e alertas de qualidade (Prompt Mestre §8.2) são
        planejados para as próximas fases.
      </p>

      <section aria-label="Estado do sistema" style={{ marginTop: "var(--space-6)" }}>
        <h2>Estado do sistema</h2>
        {statusLoading && <Loading label="Consultando /api/v1/system/status…" />}
        {statusError && <ErrorState message={statusError} />}
        {!statusLoading && !statusError && status && (
          <ul>
            <li>Ambiente: {status.environment}</li>
            <li>Modo de autenticação: {status.auth_mode}</li>
            <li>Suíte clínica (teste + piloto + produção) habilitada: {status.clinical_suite_enabled ? "sim" : "não"}</li>
            <li>
              Laboratório (contexto independente) habilitado:{" "}
              {status.operational_states.find((s) => s.kind === "laboratory")?.enabled ? "sim" : "não"}
            </li>
            <li>Modo demonstração: {status.demo_mode ? "sim" : "não"}</li>
          </ul>
        )}
      </section>

      <section aria-label="Versão da API" style={{ marginTop: "var(--space-6)" }}>
        <h2>Versão da API</h2>
        {versionLoading && <Loading label="Consultando /version…" />}
        {versionError && <ErrorState message={versionError} />}
        {!versionLoading && !versionError && version && (
          <p>
            {version.version} ({version.environment})
          </p>
        )}
      </section>

      <section aria-label="Projetos" style={{ marginTop: "var(--space-6)" }}>
        <h2>Projetos BioMatCAD</h2>
        <EmptyState
          title="Nenhum projeto ainda"
          description="O módulo de projetos (CAD/FEM/Materiais/ML) é planejado para a Fase 2 — ver REQUIREMENTS_MATRIX.md."
        />
      </section>
    </AuthenticatedLayout>
  );
}
