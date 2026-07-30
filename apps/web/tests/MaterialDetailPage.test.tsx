import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { MaterialDetailPage } from "../src/pages/MaterialDetailPage";

// Regressão direta pedida no escopo (Seção 2): a GUI precisa distinguir claramente dado
// sintético de dado documentado/revisado -- MaterialsPage (lista) já mostrava review_status
// cru; este teste garante que a página de detalhe também mostra o status humanamente legível
// e o aviso de "dado sintético", nunca escondendo essa informação da/o pesquisador(a).

const MATERIAL_ID = "mat-synthetic-1";

function AutoLogin({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  useEffect(() => {
    login("e2e-playwright@biomatcad.example", "e2e-synthetic-password-123").catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function mockFetch() {
  return vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/login")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ access_token: "fake-token", token_type: "bearer", expires_in: 3600 }),
      });
    }
    if (url.endsWith("/api/v1/auth/me")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: "u1",
          email: "e2e-playwright@biomatcad.example",
          full_name: "Usuário E2E Playwright",
          role: "researcher",
          organization_id: "org1",
        }),
      });
    }
    if (url.endsWith(`/api/v1/materials/${MATERIAL_ID}`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: MATERIAL_ID,
          name: "Hidroxiapatita sintética de teste",
          category: "cerâmico",
          source_type: "synthetic",
          review_status: "draft",
          created_at: "2026-01-01T00:00:00Z",
          description: "Registro sintético para fins de desenvolvimento.",
          properties: [],
          references: [],
        }),
      });
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

describe("MaterialDetailPage -- proveniência do dado (sintético/revisado) sempre visível", () => {
  it("mostra o status de revisão legível e o aviso de dado sintético", async () => {
    vi.stubGlobal("fetch", mockFetch());

    render(
      <MemoryRouter initialEntries={[`/app/materials/${MATERIAL_ID}`]}>
        <ThemeProvider>
          <AuthProvider>
            <AutoLogin>
              <Routes>
                <Route path="/app/materials/:materialId" element={<MaterialDetailPage />} />
              </Routes>
            </AutoLogin>
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>,
    );

    const reviewStatus = await screen.findByTestId("material-review-status");
    // Nunca deve mostrar o valor bruto "draft" sem tradução -- a UI real sempre localiza.
    expect(reviewStatus).toHaveTextContent(/não revisado/i);
    expect(reviewStatus.textContent).not.toBe("draft");

    expect(screen.getByText(/dado sintético/i)).toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});
