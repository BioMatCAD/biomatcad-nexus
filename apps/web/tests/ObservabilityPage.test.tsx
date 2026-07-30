import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { ObservabilityPage } from "../src/pages/ObservabilityPage";

describe("ObservabilityPage (smoke test)", () => {
  it("renderiza o título e o estado de carregamento sem quebrar", () => {
    render(
      <BrowserRouter>
        <ThemeProvider>
        <AuthProvider>
          <ObservabilityPage />
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>,
    );

    expect(screen.getByRole("heading", { name: /observabilidade/i })).toBeInTheDocument();
    // Sem token (usuário não autenticado neste teste), a página nunca dispara a requisição real
    // e permanece no estado de carregamento -- comportamento esperado, igual ao padrão já usado
    // em MaterialsPage.test.tsx.
    expect(screen.getByText(/consultando/i)).toBeInTheDocument();
  });
});
