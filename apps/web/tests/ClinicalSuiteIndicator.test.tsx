import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ClinicalSuiteIndicator } from "../src/components/layout/ClinicalSuiteIndicator";
import { SystemStatusProvider } from "../src/context/SystemStatusContext";

// Regressão do Incremento 1.1: Laboratório e a suíte clínica devem aparecer como indicadores
// SEPARADOS, nunca somados em um único "suíte clínica/laboratorial".
describe("ClinicalSuiteIndicator", () => {
  it("mostra laboratório habilitado e suíte clínica desabilitada como estados independentes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          environment: "test",
          auth_mode: "DEV_AUTH",
          clinical_suite_enabled: false,
          demo_mode: false,
          operational_states: [
            { kind: "research", enabled: true },
            { kind: "laboratory", enabled: true },
            { kind: "clinical_test", enabled: false },
            { kind: "clinical_pilot", enabled: false },
            { kind: "clinical_production", enabled: false },
          ],
        }),
      })
    );

    render(
      <SystemStatusProvider>
        <ClinicalSuiteIndicator />
      </SystemStatusProvider>
    );

    expect(await screen.findByText(/laboratório \(contexto independente\)/i)).toBeInTheDocument();
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/suíte clínica.*desabilitada/i);
    expect(status).toHaveTextContent(/laboratório.*habilitado/i);
    expect(status).toHaveTextContent(/DEV_AUTH/);

    vi.unstubAllGlobals();
  });
});
