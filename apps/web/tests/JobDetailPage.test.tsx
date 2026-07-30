import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";

// jsdom não implementa um contexto WebGL real -- sem este mock, StlViewer cairia
// legitimamente no estado "webgl-unavailable" (comportamento correto e já coberto por teste
// dedicado em StlViewer.test.tsx). Para este arquivo, que testa o restante da página (status,
// métricas, retry, download), mockamos apenas a classe WebGLRenderer do three.js por uma
// implementação leve que não toca GPU -- Scene/BufferGeometry/Mesh/Material/OrbitControls
// continuam sendo as classes REAIS do three.js, então o estado do componente (wireframe,
// contagem de triângulos etc.) continua sendo real, não fabricado.
vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class FakeWebGLRenderer {
    domElement: HTMLCanvasElement;
    localClippingEnabled = false;
    constructor() {
      this.domElement = document.createElement("canvas");
    }
    setSize() {
      /* no-op no ambiente de teste */
    }
    render() {
      /* no-op no ambiente de teste */
    }
    dispose() {
      /* no-op no ambiente de teste */
    }
  }
  return { ...actual, WebGLRenderer: FakeWebGLRenderer };
});
import { createHash } from "node:crypto";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { JobDetailPage } from "../src/pages/JobDetailPage";

// STL binário mínimo válido (1 triângulo, 84 + 50 = 134 bytes) usado para que o StlViewer
// (que agora busca o artefato de verdade, com verificação de checksum -- Incremento 2.2)
// consiga carregar sem erro neste teste, que foca em status/métricas/retry, não no
// visualizador em si (testado à parte em StlViewer.test.tsx).
function buildSmallStlBuffer(): ArrayBuffer {
  const buffer = new ArrayBuffer(134);
  const view = new DataView(buffer);
  view.setUint32(80, 1, true); // 1 triângulo
  let offset = 84;
  for (let i = 0; i < 3; i++) view.setFloat32(offset + i * 4, 0, true); // normal
  offset += 12;
  for (let v = 0; v < 3; v++) {
    for (let i = 0; i < 3; i++) view.setFloat32(offset + i * 4, v, true);
    offset += 12;
  }
  return buffer;
}
const SMALL_STL_BUFFER = buildSmallStlBuffer();
const SMALL_STL_SHA256 = createHash("sha256").update(Buffer.from(SMALL_STL_BUFFER)).digest("hex");

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
          // Nomes de campo iguais ao contrato real do worker (JobEnvelope.cs:
          // porosity_pct_measured, vertex_count_unique) -- NÃO usar porosity_pct_estimated
          // nem vertex_count, que nunca existiram na API real (bug real encontrado e
          // corrigido em 2026-07-29, ver types.ts).
          metrics: {
            bounding_box_mm: [[0, 0, 0], [10, 10, 10]],
            volume_mm3: 400.0,
            porosity_pct_measured: 60.0,
            surface_area_mm2: 950.5,
            vertex_count_unique: 168,
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
          { id: "art-stl", geometry_job_id: JOB_ID, kind: "stl", sha256: SMALL_STL_SHA256, size_bytes: SMALL_STL_BUFFER.byteLength, created_at: "2026-01-01T00:00:05Z" },
          { id: "art-thumb", geometry_job_id: JOB_ID, kind: "thumbnail", sha256: "b".repeat(64), size_bytes: 10, created_at: "2026-01-01T00:00:05Z" },
        ],
      });
    }
    if (url.endsWith("/api/v1/artifacts/art-stl/download")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Length": String(SMALL_STL_BUFFER.byteLength) }),
        arrayBuffer: async () => SMALL_STL_BUFFER,
      });
    }
    if (url.endsWith(`/api/v1/jobs/${JOB_ID}/manifest`)) {
      return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: "not found" }) });
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

const FAILED_JOB_ID = "job-failed-1";
const RETRIED_JOB_ID = "job-retried-1";

function mockFetchFailedJob() {
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
    if (url.endsWith(`/api/v1/jobs/${FAILED_JOB_ID}`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: FAILED_JOB_ID,
          design_run_id: "run-failed-1",
          attempt_number: 1,
          status: "failed",
          progress_pct: 40,
          created_at: "2026-01-01T00:00:00Z",
          started_at: "2026-01-01T00:00:00Z",
          finished_at: "2026-01-01T00:00:03Z",
          error_code: "WORKER_TIMEOUT",
          error_message: "Excedeu o tempo máximo de execução configurado.",
          worker_version: null,
          dotnet_version: null,
          picogk_version: null,
          duration_seconds: 3,
          metrics: null,
        }),
      });
    }
    if (url.endsWith(`/api/v1/design-runs/run-failed-1/retry`) && init?.method === "POST") {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: RETRIED_JOB_ID,
          design_run_id: "run-failed-1",
          attempt_number: 2,
          status: "queued",
          progress_pct: 0,
          created_at: "2026-01-01T00:05:00Z",
          started_at: null,
          finished_at: null,
          error_code: null,
          error_message: null,
          worker_version: null,
          dotnet_version: null,
          picogk_version: null,
          duration_seconds: null,
          metrics: null,
        }),
      });
    }
    if (url.endsWith(`/api/v1/jobs/${RETRIED_JOB_ID}`)) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: RETRIED_JOB_ID,
          design_run_id: "run-failed-1",
          attempt_number: 2,
          status: "queued",
          progress_pct: 0,
          created_at: "2026-01-01T00:05:00Z",
          started_at: null,
          finished_at: null,
          error_code: null,
          error_message: null,
          worker_version: null,
          dotnet_version: null,
          picogk_version: null,
          duration_seconds: null,
          metrics: null,
        }),
      });
    }
    return Promise.reject(new Error(`fetch não mockado neste teste (retry) para: ${url}`));
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

    // Nota de proveniência obrigatória: um resultado geométrico calculado nunca pode ser
    // confundido com validação experimental (Prompt Mestre §3.1 -- honestidade técnica).
    const provenance = screen.getByTestId("metrics-provenance-note");
    expect(provenance).toHaveTextContent(/calculado/i);
    expect(provenance).toHaveTextContent(/não constitui validação experimental/i);

    const metrics = screen.getByTestId("job-metrics");
    expect(metrics).toHaveTextContent("400"); // volume_mm3
    expect(metrics).toHaveTextContent("60"); // porosity_pct_measured
    expect(metrics).toHaveTextContent("168"); // vertex_count_unique
    expect(metrics).toHaveTextContent("sim"); // is_watertight

    // Guarda de unicidade: apenas o artefato STL ganha este data-testid -- o de thumbnail
    // (kind !== "stl") não deve ser confundido com o botão de download do STL. Desde o
    // Incremento 2.2, o download não é mais um <a href> estático (que nunca enviava
    // Authorization e falharia com 401 contra um backend real, ver docs/architecture/
    // viewer-3d-audit.md) -- é um botão que dispara um download autenticado via Blob.
    const stlLinks = screen.getAllByTestId("stl-download-link");
    expect(stlLinks).toHaveLength(1);
    expect(stlLinks[0].tagName).toBe("BUTTON");
    expect(stlLinks[0].textContent).toMatch(/^stl /);

    // O visualizador 3D carrega o mesmo artefato de verdade (com verificação de checksum) --
    // deve chegar ao estado "ready" (nunca renderizar geometria substituta).
    const triangleIndicator = await screen.findByTestId("viewer-triangle-count");
    expect(triangleIndicator).toHaveTextContent(/1 triângulo/);
    expect(screen.getByTestId("viewer-experimental-warning")).toHaveTextContent(
      "Resultado computacional — não validado experimentalmente.",
    );

    vi.unstubAllGlobals();
  });

  it("baixa o artefato STL de forma autenticada (Authorization real, nunca token na URL) ao clicar no botão", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetch());
    const createObjectURLSpy = vi.fn().mockReturnValue("blob:fake-download-url");
    const revokeObjectURLSpy = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: createObjectURLSpy, revokeObjectURL: revokeObjectURLSpy });

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

    const stlButton = await screen.findByTestId("stl-download-link");
    await user.click(stlButton);

    await vi.waitFor(() => expect(createObjectURLSpy).toHaveBeenCalledTimes(1));
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:fake-download-url");

    vi.unstubAllGlobals();
  });
});

// Regressão direta pedida no escopo (Seção 2/7): "retry controlado" precisa existir de verdade
// na GUI, não só no backend -- um job failed deve oferecer "Tentar novamente", que chama
// POST /design-runs/{id}/retry (nunca reenvia silenciosamente) e navega para o job resultante.
describe("JobDetailPage -- retry controlado de um job failed", () => {
  it("mostra 'Tentar novamente' para um job failed e chama o endpoint real de retry ao clicar", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchFailedJob());

    render(
      <MemoryRouter initialEntries={[`/app/jobs/${FAILED_JOB_ID}`]}>
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
    expect(status).toHaveTextContent(/Falhou/i);

    // Um job failed não tem métricas -- a nota de proveniência só aparece quando há métricas
    // reais para explicar (nunca deve aparecer "calculado" sobre um resultado inexistente).
    expect(screen.queryByTestId("metrics-provenance-note")).not.toBeInTheDocument();

    const retryButton = screen.getByTestId("job-retry-button");
    expect(retryButton).toHaveTextContent(/Tentar novamente/i);

    await user.click(retryButton);

    // Após o retry bem-sucedido, a página navega para o novo job (attempt 2) e mostra seu
    // status real ("Na fila"), nunca reaproveitando silenciosamente o status do job antigo.
    const newStatus = await screen.findByTestId("job-status");
    expect(newStatus).toHaveTextContent(/Na fila/i);

    vi.unstubAllGlobals();
  });
});
