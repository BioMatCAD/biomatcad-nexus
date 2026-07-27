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
          clinical_suite_enabled: false,
          demo_mode: false,
          operational_states: [],
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
