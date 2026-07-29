import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { MaterialsPage } from "../src/pages/MaterialsPage";

describe("MaterialsPage (smoke test)", () => {
  it("renderiza o título e o estado de carregamento sem quebrar", () => {
    render(
      <BrowserRouter>
        <ThemeProvider>
        <AuthProvider>
          <MaterialsPage />
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>,
    );

    expect(screen.getByRole("heading", { name: /catálogo de materiais/i })).toBeInTheDocument();
    // Sem token (usuário não autenticado neste teste), a página fica no estado de carregamento
    // -- nunca dispara a requisição real, o que é o comportamento esperado.
    expect(screen.getByText(/carregando catálogo/i)).toBeInTheDocument();
  });
});
