import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { RecipeEditorPage } from "../src/pages/RecipeEditorPage";

describe("RecipeEditorPage (smoke test)", () => {
  it("renderiza os campos principais do formulário de receita", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ valid: true, errors: [], checksum_sha256: "abc123", schema_version: "1.0.0" }),
      }),
    );

    render(
      <BrowserRouter>
        <ThemeProvider>
        <AuthProvider>
          <RecipeEditorPage />
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>,
    );

    expect(screen.getByRole("heading", { name: /editor de receita biomatcem/i })).toBeInTheDocument();
    expect(screen.getByText(/^bloco$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cilindro$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salvar receita/i })).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  // Regressão direta pedida no escopo (Seção 4, contrato TopologyProvider): a GUI precisa
  // mostrar quais topologias existem e quais estão realmente implementadas -- nunca uma opção
  // selecionável que não tenha execução real por trás (Prompt Mestre §3.1).
  it("lista os providers de topologia e mantém Voronoi desabilitado (ainda não implementado)", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ valid: true, errors: [], checksum_sha256: "abc123", schema_version: "1.0.0" }),
      }),
    );

    render(
      <BrowserRouter>
        <ThemeProvider>
        <AuthProvider>
          <RecipeEditorPage />
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>,
    );

    const select = screen.getByLabelText(/^topologia$/i) as HTMLSelectElement;
    const gyroidOption = screen.getByRole("option", { name: /gyroid \(tpms\) -- implementado/i }) as HTMLOptionElement;
    const voronoiOption = screen.getByRole("option", { name: /voronoi -- em preparação/i }) as HTMLOptionElement;

    expect(select.value).toBe("gyroid");
    expect(gyroidOption.disabled).toBe(false);
    expect(voronoiOption.disabled).toBe(true);

    vi.unstubAllGlobals();
  });
});
