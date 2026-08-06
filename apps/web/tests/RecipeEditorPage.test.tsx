import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { RecipeEditorPage } from "../src/pages/RecipeEditorPage";

function renderEditor() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ valid: true, errors: [], checksum_sha256: "abc123", schema_version: "1.0.0" }),
    }),
  );

  return render(
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <RecipeEditorPage />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>,
  );
}

describe("RecipeEditorPage (smoke test)", () => {
  it("renderiza os campos principais do formulário de receita", () => {
    renderEditor();

    expect(screen.getByRole("heading", { name: /editor de receita biomatcem/i })).toBeInTheDocument();
    expect(screen.getByText(/^bloco$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cilindro$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salvar receita/i })).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  // Regressão direta pedida no escopo (Seção 4, contrato TopologyProvider): a GUI precisa
  // mostrar quais topologias existem e quais estão realmente implementadas -- nunca uma opção
  // selecionável que não tenha execução real por trás (Prompt Mestre §3.1). Voronoi
  // (voronoi_cell_edges_v1) passou a status="implemented" nos dois registros reais
  // (apps/api/.../topology_providers.py e apps/geometry-worker/TopologyProviderRegistry.cs) na
  // rodada Voronoi (Incremento 2.2, Seção 8) -- este teste foi atualizado para refletir essa
  // mudança real, nunca "afrouxado" para passar.
  it("lista os providers de topologia e mantém ambos habilitados (Gyroid e Voronoi implementados)", () => {
    renderEditor();

    const select = screen.getByLabelText(/^topologia$/i) as HTMLSelectElement;
    const gyroidOption = screen.getByRole("option", { name: /gyroid \(tpms\) -- implementado/i }) as HTMLOptionElement;
    const voronoiOption = screen.getByRole("option", { name: /voronoi \(voronoi_cell_edges_v1\) -- implementado/i }) as HTMLOptionElement;

    expect(select.value).toBe("gyroid");
    expect(gyroidOption.disabled).toBe(false);
    expect(voronoiOption.disabled).toBe(false);

    vi.unstubAllGlobals();
  });

  it("ao selecionar Voronoi, mostra os campos condicionais e esconde os campos do Gyroid", async () => {
    const user = userEvent.setup();
    renderEditor();

    const select = screen.getByLabelText(/^topologia$/i) as HTMLSelectElement;
    await user.selectOptions(select, "voronoi_cell_edges_v1");

    expect(screen.getByTestId("voronoi-topology-fieldset")).toBeInTheDocument();
    expect(screen.getByLabelText(/número de sítios/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/distribuição dos sítios/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/raio do strut/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/suavização dos nós/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/fator de raio do nó/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/comportamento de fronteira/i)).toBeInTheDocument();
    expect(screen.queryByText(/^topologia \(gyroid\)$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/tamanho da célula/i)).not.toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("comportamento de fronteira fica travado em 'clip' (único suportado nesta rodada)", async () => {
    const user = userEvent.setup();
    renderEditor();

    const select = screen.getByLabelText(/^topologia$/i) as HTMLSelectElement;
    await user.selectOptions(select, "voronoi_cell_edges_v1");

    const boundarySelect = screen.getByLabelText(/comportamento de fronteira/i) as HTMLSelectElement;
    expect(boundarySelect.value).toBe("clip");
    expect(boundarySelect.disabled).toBe(true);

    vi.unstubAllGlobals();
  });

  it("mostra a estimativa de custo computacional e o aviso literal de resultado não validado", () => {
    renderEditor();

    expect(screen.getByTestId("compute-cost-estimate")).toBeInTheDocument();
    expect(screen.getByTestId("compute-cost-estimate").textContent).toMatch(/voxels/i);
    expect(screen.getByTestId("research-result-disclaimer").textContent).toBe(
      "Resultado computacional — não validado experimentalmente.",
    );

    vi.unstubAllGlobals();
  });

  it("mostra aviso de receita pesada quando site_count alto em modo final excede heurística", async () => {
    const user = userEvent.setup();
    renderEditor();

    const select = screen.getByLabelText(/^topologia$/i) as HTMLSelectElement;
    await user.selectOptions(select, "voronoi_cell_edges_v1");

    const modeSelect = screen.getByLabelText(/^modo$/i) as HTMLSelectElement;
    await user.selectOptions(modeSelect, "final");

    const siteCountInput = screen.getByLabelText(/número de sítios/i) as HTMLInputElement;
    await user.clear(siteCountInput);
    await user.type(siteCountInput, "300");

    expect(await screen.findByTestId("heavy-recipe-warning")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("voltar de Voronoi para Gyroid restaura os campos do Gyroid (nenhum campo de Voronoi vaza)", async () => {
    const user = userEvent.setup();
    renderEditor();

    const select = screen.getByLabelText(/^topologia$/i) as HTMLSelectElement;
    await user.selectOptions(select, "voronoi_cell_edges_v1");
    expect(screen.getByTestId("voronoi-topology-fieldset")).toBeInTheDocument();

    await user.selectOptions(select, "gyroid");
    expect(screen.queryByTestId("voronoi-topology-fieldset")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/tamanho da célula/i)).toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});
