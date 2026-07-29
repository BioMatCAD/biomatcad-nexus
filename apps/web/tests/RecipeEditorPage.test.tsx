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
});
