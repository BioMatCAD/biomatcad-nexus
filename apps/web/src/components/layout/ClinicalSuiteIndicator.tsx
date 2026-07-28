import { useSystemStatus } from "../../context/SystemStatusContext";
import { Loading } from "../feedback/Loading";

// Prompt Mestre / Incremento 1.1: mostrar no cartão de login o estado da suíte clínica
// (CLINICAL_TEST + CLINICAL_PILOT + CLINICAL_PRODUCTION, sempre em conjunto) E,
// separadamente, o modo de autenticação atual (DEV_AUTH). Laboratório é um contexto
// independente e NÃO é somado à suíte clínica — bug corrigido no Incremento 1.1.
// O valor vem sempre do backend (GET /api/v1/system/status), nunca de configuração local.
export function ClinicalSuiteIndicator() {
  const { status, isLoading, error, isDemoMode } = useSystemStatus();

  if (isLoading) return <Loading label="Verificando estado do sistema…" />;
  if (error) {
    return (
      <p role="status" style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem" }}>
        Não foi possível confirmar o estado do sistema com o servidor.
      </p>
    );
  }
  if (!status) return null;

  const laboratory = status.operational_states.find((s) => s.kind === "laboratory")?.enabled ?? false;

  return (
    <div role="status" style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)", display: "flex", flexDirection: "column", gap: 4 }}>
      <p style={{ margin: 0 }}>
        Suíte clínica (teste + piloto + produção):{" "}
        <strong style={{ color: status.clinical_suite_enabled ? "var(--color-success)" : "var(--color-text-secondary)" }}>
          {status.clinical_suite_enabled ? "habilitada" : "desabilitada (padrão)"}
        </strong>
      </p>
      <p style={{ margin: 0 }}>
        Laboratório (contexto independente):{" "}
        <strong style={{ color: laboratory ? "var(--color-success)" : "var(--color-text-secondary)" }}>
          {laboratory ? "habilitado" : "desabilitado (padrão)"}
        </strong>
      </p>
      <p style={{ margin: 0 }}>
        Modo de autenticação: <strong>{status.auth_mode}</strong>
        {status.auth_mode === "DEV_AUTH" && " — desenvolvimento/demonstração, não usar com dados clínicos reais"}
      </p>
      {isDemoMode && <p style={{ margin: 0 }}>Simulação de demonstração — não reflete um backend real.</p>}
    </div>
  );
}
