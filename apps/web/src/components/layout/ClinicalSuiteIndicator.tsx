import { useSystemStatus } from "../../context/SystemStatusContext";
import { Loading } from "../feedback/Loading";

// Prompt Mestre (incremento 1): "mostrar na tela de login se a suíte clínica está habilitada
// ou desabilitada". O valor vem sempre do backend (system status), nunca de configuração local.
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

  return (
    <p role="status" style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
      Suíte clínica/laboratorial:{" "}
      <strong style={{ color: status.clinical_suite_enabled ? "var(--color-success)" : "var(--color-text-secondary)" }}>
        {status.clinical_suite_enabled ? "habilitada" : "desabilitada (padrão)"}
      </strong>
      {isDemoMode && " — simulação de demonstração, não reflete um backend real"}
    </p>
  );
}
