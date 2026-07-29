import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { JobDetailPage } from "../src/pages/JobDetailPage";

// Guarda de regressão para o bug real encontrado em execução E2E real no Windows
// (vertical.spec.ts falhava esperando o literal "succeeded" na página do job): a UI real
// SEMPRE localiza o status em português (ex.: "Concluído", via STATUS_LABEL em
// JobDetailPage.tsx) -- nunca o valor bruto da API. Este teste renderiza JobDetailPage com um
// job succeeded simulado e confirma exatamente o que a interface realmente mostra, para que o
// teste E2E e este componente nunca mais divirjam silenciosamente.

const JOB_ID = "job-succeeded-1";

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
    if (url.endsWith(`/api/v1/jobs/${JOB_ID}`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: JOB_ID,
          design_run_id: "run1",
          attempt_number: 1,
          status: "succeeded",
          progress_pct: 100,
          created_at: "2026-01-01T00:00:00Z",
          started_at: "2026-01-01T00:00:00Z",
          finished_at: "2026-01-01T00:00:05Z",
          error_code: null,
          error_message: null,
          worker_version: "0.1.0-test",
          dotnet_version: "9.0.0",
          picogk_version: "2.2.0",
          duration_seconds: 5,
          metrics: {
            bounding_box_mm: [[0, 0, 0], [10, 10, 10]],
            volume_mm3: 400.0,
            porosity_pct_estimated: 60.0,
            surface_area_mm2: 950.5,
            vertex_count: 168,
            triangle_count: 100,
            is_watertight: true,
          },
        }),
      });
    }
    if (url.endsWith(`/api/v1/jobs/${JOB_ID}/artifacts`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [
          { id: "art-stl", geometry_job_id: JOB_ID, kind: "stl", sha256: "a".repeat(64), size_bytes: 1234, created_at: "2026-01-01T00:00:05Z" },
          { id: "art-thumb", geometry_job_id: JOB_ID, kind: "thumbnail", sha256: "b".repeat(64), size_bytes: 10, created_at: "2026-01-01T00:00:05Z" },
        ],
      });
    }
    if (url.endsWith(`/api/v1/jobs/${JOB_ID}/manifest`)) {
      return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: "not found" }) });
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

describe("JobDetailPage (smoke test) -- status/métricas/download realmente renderizados para um job succeeded", () => {
  it("mostra o status localizado ('Concluído'), a tabela de métricas e o link de download do STL", async () => {
    vi.stubGlobal("fetch", mockFetch());

    render(
      <MemoryRouter initialEntries={[`/app/jobs/${JOB_ID}`]}>
        <ThemeProvider>
          <AuthProvider>
            <AutoLogin>
              <Routes>
                <Route path="/app/jobs/:jobId" element={<JobDetailPage />} />
              </Routes>
            </AutoLogin>
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    );

    const status = await screen.findByTestId("job-status");
    // A UI real nunca renderiza o valor bruto "succeeded" -- só a tradução ("Concluído").
    expect(status).toHaveTextContent(/Conclu[íi]do/i);
    expect(status.textContent).not.toContain("succeeded");

    const metrics = screen.getByTestId("job-metrics");
    expect(metrics).toHaveTextContent("400");
    expect(metrics).toHaveTextContent("sim");

    // Guarda de unicidade: apenas o artefato STL ganha este data-testid -- o de thumbnail
    // (kind !== "stl") não deve ser confundido com o link de download do STL.
    const stlLinks = screen.getAllByTestId("stl-download-link");
    expect(stlLinks).toHaveLength(1);
    expect(stlLinks[0]).toHaveAttribute("download");
    expect(stlLinks[0].textContent).toMatch(/^stl /);

    vi.unstubAllGlobals();
  });
});
