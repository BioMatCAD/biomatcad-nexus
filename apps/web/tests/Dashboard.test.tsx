import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/context/AuthContext";
import { SystemStatusProvider } from "../src/context/SystemStatusContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { DashboardPage } from "../src/pages/DashboardPage";

describe("DashboardPage (smoke test)", () => {
  it("renderiza sem quebrar e mostra os estados de carregamento", async () => {
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
            { kind: "laboratory", enabled: false },
            { kind: "clinical_test", enabled: false },
            { kind: "clinical_pilot", enabled: false },
            { kind: "clinical_production", enabled: false },
          ],
        }),
      })
    );

    render(
      <BrowserRouter>
        <ThemeProvider>
          <AuthProvider>
            <SystemStatusProvider>
              <DashboardPage />
            </SystemStatusProvider>
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    );

    expect(screen.getByRole("heading", { name: /painel inicial/i })).toBeInTheDocument();
    expect(await screen.findByText(/nenhum projeto ainda/i)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
