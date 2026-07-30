import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { ProjectDetailPage } from "../src/pages/ProjectDetailPage";

// Regressão direta pedida no escopo (Seção 2/7): o histórico de execuções do projeto precisa
// oferecer "Repetir" para uma execução failed/cancelled, chamando de verdade
// POST /design-runs/{id}/retry -- nunca um botão decorativo (Prompt Mestre §3.1).

const PROJECT_ID = "proj-1";
const FAILED_RUN_ID = "run-failed-1";

function AutoLogin({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  useEffect(() => {
    login("e2e-playwright@biomatcad.example", "e2e-synthetic-password-123").catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function baseJob(overrides: Record<string, unknown> = {}) {
  return {
    id: "job-failed-1",
    design_run_id: FAILED_RUN_ID,
    attempt_number: 1,
    status: "failed",
    progress_pct: 30,
    created_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:00:02Z",
    error_code: "WORKER_TIMEOUT",
    error_message: "Excedeu o tempo máximo.",
    worker_version: null,
    dotnet_version: null,
    picogk_version: null,
    duration_seconds: 2,
    metrics: null,
    ...overrides,
  };
}

function mockFetch(onRetry: () => void) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/auth/login")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ access_token: "fake-token", token_type: "bearer", expires_in: 3600 }) });
    }
    if (url.endsWith("/api/v1/auth/me")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ id: "u1", email: "e2e-playwright@biomatcad.example", full_name: "Usuário E2E Playwright", role: "researcher", organization_id: "org1" }),
      });
    }
    if (url.endsWith(`/api/v1/projects/${PROJECT_ID}`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ id: PROJECT_ID, organization_id: "org1", owner_user_id: "u1", name: "Projeto Teste", description: null, status: "active", created_at: "2026-01-01T00:00:00Z" }),
      });
    }
    if (url.endsWith(`/api/v1/projects/${PROJECT_ID}/recipes`)) {
      return Promise.resolve({ ok: true, status: 200, json: async () => [] });
    }
    if (url.endsWith(`/api/v1/projects/${PROJECT_ID}/design-runs`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: FAILED_RUN_ID,
            organization_id: "org1",
            project_id: PROJECT_ID,
            recipe_id: "recipe-1",
            material_id: null,
            idempotency_key: "idem-failed-1",
            created_at: "2026-01-01T00:00:00Z",
            created: false,
            latest_job: baseJob(),
          },
        ],
      });
    }
    if (url.endsWith(`/api/v1/design-runs/${FAILED_RUN_ID}/retry`) && init?.method === "POST") {
      onRetry();
      return Promise.resolve({ ok: true, status: 200, json: async () => baseJob({ id: "job-retried-1", attempt_number: 2, status: "queued", progress_pct: 0, error_code: null, error_message: null }) });
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

describe("ProjectDetailPage -- retry no histórico de execuções", () => {
  it("mostra 'Repetir' para uma execução failed e chama o endpoint real de retry ao clicar", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    vi.stubGlobal("fetch", mockFetch(onRetry));

    render(
      <MemoryRouter initialEntries={[`/app/projects/${PROJECT_ID}`]}>
        <ThemeProvider>
          <AuthProvider>
            <AutoLogin>
              <Routes>
                <Route path="/app/projects/:projectId" element={<ProjectDetailPage />} />
                <Route path="/app/jobs/:jobId" element={<div>job criado</div>} />
              </Routes>
            </AutoLogin>
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/falhou/i)).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: /repetir/i });

    await user.click(retryButton);

    await waitFor(() => expect(onRetry).toHaveBeenCalledTimes(1));

    vi.unstubAllGlobals();
  });
});
