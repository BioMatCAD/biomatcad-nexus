import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { RecipeDetailPage } from "../src/pages/RecipeDetailPage";

// Regressão direta pedida no escopo (Seção 2): a GUI de pesquisa precisa permitir "seleção de
// material" antes do envio do job, e o material_id escolhido precisa realmente chegar no corpo
// de POST /api/v1/design-runs -- nunca ficar preso apenas no tipo TypeScript sem uso real na UI.

const RECIPE_ID = "recipe-1";

function AutoLogin({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  useEffect(() => {
    login("e2e-playwright@biomatcad.example", "e2e-synthetic-password-123").catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function mockFetch(onCreateDesignRun: (body: unknown) => void) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
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
    if (url.endsWith(`/api/v1/recipes/${RECIPE_ID}`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: RECIPE_ID,
          organization_id: "org1",
          project_id: "proj-1",
          name: "Receita Gyroid Teste",
          schema_version: "1.0.0",
          canonical_json: {
            schema_version: "1.0.0",
            domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
            topology: { kind: "gyroid", cell_size_mm: 2, wall_thickness_mm: 0.4, isovalue: 0, target_porosity_pct: 60 },
            resolution: { voxel_size_mm: 0.2 },
            mode: "preview",
            seed: 1,
            compute_limits: { max_duration_seconds: 60, max_memory_mb: 512, max_voxel_count: 1000000 },
            output_formats: ["stl"],
          },
          checksum_sha256: "c".repeat(64),
          version: 1,
          parent_recipe_id: null,
          status: "validated",
          created_at: "2026-01-01T00:00:00Z",
        }),
      });
    }
    if (url.endsWith("/api/v1/materials")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [
          { id: "mat-1", name: "Hidroxiapatita sintética", category: "cerâmico", source_type: "synthetic", review_status: "draft", created_at: "2026-01-01T00:00:00Z" },
          { id: "mat-2", name: "PLA (literatura)", category: "polímero", source_type: "literature", review_status: "reviewed", created_at: "2026-01-01T00:00:00Z" },
        ],
      });
    }
    if (url.endsWith("/api/v1/design-runs") && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      onCreateDesignRun(body);
      return Promise.resolve({
        ok: true,
        status: 201,
        json: async () => ({
          id: "run-1",
          organization_id: "org1",
          project_id: "proj-1",
          recipe_id: RECIPE_ID,
          material_id: body.material_id ?? null,
          idempotency_key: body.idempotency_key,
          created_at: "2026-01-01T00:10:00Z",
          created: true,
          latest_job: {
            id: "job-new-1",
            design_run_id: "run-1",
            attempt_number: 1,
            status: "queued",
            progress_pct: 0,
            created_at: "2026-01-01T00:10:00Z",
            started_at: null,
            finished_at: null,
            error_code: null,
            error_message: null,
            worker_version: null,
            dotnet_version: null,
            picogk_version: null,
            duration_seconds: null,
            metrics: null,
          },
        }),
      });
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/app/recipes/${RECIPE_ID}`]}>
      <ThemeProvider>
        <AuthProvider>
          <AutoLogin>
            <Routes>
              <Route path="/app/recipes/:recipeId" element={<RecipeDetailPage />} />
              <Route path="/app/jobs/:jobId" element={<div>job criado</div>} />
            </Routes>
          </AutoLogin>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>,
  );
}

describe("RecipeDetailPage -- seleção de material antes do envio do job", () => {
  it("lista os materiais reais do catálogo e envia o material_id escolhido em POST /design-runs", async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", mockFetch((body) => { capturedBody = body as Record<string, unknown>; }));

    renderPage();

    const select = await screen.findByLabelText(/material associado ao job/i);
    // Sem seleção, a opção padrão explícita "nenhum material específico" precisa existir --
    // material_id nunca pode ser assumido, só enviado se o pesquisador escolher de verdade.
    expect(screen.getByText(/nenhum material específico/i)).toBeInTheDocument();
    expect(await screen.findByText(/Hidroxiapatita sintética \(sintético\)/i)).toBeInTheDocument();
    expect(screen.getByText(/PLA \(literatura\) \(literatura\)/i)).toBeInTheDocument();

    await user.selectOptions(select, "mat-2");

    const submitButton = screen.getByRole("button", { name: /enviar job geométrico/i });
    await user.click(submitButton);

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody?.material_id).toBe("mat-2");

    vi.unstubAllGlobals();
  });

  it("envia material_id null quando nenhum material é escolhido", async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | undefined;
    vi.stubGlobal("fetch", mockFetch((body) => { capturedBody = body as Record<string, unknown>; }));

    renderPage();

    await screen.findByLabelText(/material associado ao job/i);
    const submitButton = screen.getByRole("button", { name: /enviar job geométrico/i });
    await user.click(submitButton);

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody?.material_id).toBeNull();

    vi.unstubAllGlobals();
  });
});
