import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { PubChemIngestionPanel } from "../src/components/scientific/PubChemIngestionPanel";

// Adendo de Interface Científica Mínima (Fase Q) -- testes de componente do painel
// administrativo de ingestão PubChem: validação de CIDs, dry-run, submissão, polling
// controlado, cancelamento, encerramento de polling ao desmontar, e erros (403/429/503)
// nunca escondidos.
//
// O polling real usa window.setInterval a cada 2s -- em vez de esperar tempo real ou usar
// fake timers (que colidem com as esperas assíncronas do Testing Library), substituímos
// diretamente window.setInterval/clearInterval por um par controlável: setInterval captura o
// callback e devolve um id sintético; cada "tick" de polling é disparado manualmente chamando
// esse callback dentro de act(). Isso prova o comportamento real do componente (chama a API,
// atualiza estado, para o polling em status terminal) sem depender de tempo relógio.

const ADMIN_EMAIL = "admin@biomatcad.example";

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json: () => Promise.resolve(body),
  });
}

function errorResponse(status: number, message: string) {
  return jsonResponse({ error: { id: "e1", code: "ERR", message } }, status);
}

const SOURCES = [
  { id: "src-1", name: "PubChem (fonte sintética de teste)", source_type: "connector", base_url: null, publisher: null, license: null, version: null, accessed_at: null, redistribution_status: "allowed" },
];

interface RequestFixture {
  id: string;
  organization_id: string | null;
  requested_by_user_id: string;
  connector_id: string;
  source_id: string;
  external_ids: string[];
  dry_run: boolean;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  claimed_by_dispatcher_id: string | null;
  heartbeat_at: string | null;
  attempt_number: number;
  cancel_requested_at: string | null;
  summary: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  ingestion_run_id: string | null;
}

function makeRequest(overrides: Partial<RequestFixture>): RequestFixture {
  return {
    id: "req-1",
    organization_id: null,
    requested_by_user_id: "user-admin",
    connector_id: "pubchem_pug_rest",
    source_id: "src-1",
    external_ids: ["2244"],
    dry_run: false,
    status: "queued",
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    claimed_by_dispatcher_id: null,
    heartbeat_at: null,
    attempt_number: 1,
    cancel_requested_at: null,
    summary: null,
    error: null,
    ingestion_run_id: null,
    ...overrides,
  };
}

interface MockOpts {
  submitStatus?: number;
  submitMessage?: string;
  submitResponse?: RequestFixture;
  statusSequence?: RequestFixture[];
  conflicts?: unknown[];
  cancelResponse?: RequestFixture;
}

function mockFetch(opts: MockOpts) {
  let statusCallIndex = 0;
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/v1/auth/login")) return jsonResponse({ access_token: "tok-admin", token_type: "bearer" });
    if (url.endsWith("/api/v1/auth/me")) {
      return jsonResponse({ id: "user-admin", email: ADMIN_EMAIL, full_name: "Admin", role: "admin", organization_id: "org-1" });
    }
    if (url.endsWith("/api/v1/scientific-entities/sources")) return jsonResponse(SOURCES);
    if (url.endsWith("/api/v1/scientific-ingestion/requests/dry-run") && init?.method === "POST") {
      if (opts.submitStatus) return errorResponse(opts.submitStatus, opts.submitMessage ?? "Falha");
      return jsonResponse(opts.submitResponse ?? makeRequest({ dry_run: true, status: "queued" }));
    }
    if (url.endsWith("/api/v1/scientific-ingestion/requests") && init?.method === "POST") {
      if (opts.submitStatus) return errorResponse(opts.submitStatus, opts.submitMessage ?? "Falha");
      return jsonResponse(opts.submitResponse ?? makeRequest({ status: "queued" }));
    }
    const cancelMatch = url.match(/\/scientific-ingestion\/requests\/([^/]+)\/cancel$/);
    if (cancelMatch && init?.method === "POST") {
      return jsonResponse(opts.cancelResponse ?? makeRequest({ id: cancelMatch[1], status: "cancelled" }));
    }
    const conflictsMatch = url.match(/\/scientific-ingestion\/requests\/([^/]+)\/conflicts$/);
    if (conflictsMatch) return jsonResponse(opts.conflicts ?? []);
    const statusMatch = url.match(/\/scientific-ingestion\/requests\/([^/]+)$/);
    if (statusMatch) {
      const seq = opts.statusSequence ?? [];
      const body = seq[Math.min(statusCallIndex, seq.length - 1)] ?? makeRequest({ status: "succeeded" });
      statusCallIndex += 1;
      return jsonResponse(body);
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

function AutoLogin({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  useEffect(() => {
    login(ADMIN_EMAIL, "e2e-synthetic-password-123").catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function renderPanel() {
  return render(
    <ThemeProvider>
      <AuthProvider>
        <AutoLogin>
          <PubChemIngestionPanel />
        </AutoLogin>
      </AuthProvider>
    </ThemeProvider>,
  );
}

// POLL_INTERVAL_MS do componente (PubChemIngestionPanel.tsx) -- usado para distinguir o
// intervalo de polling real do componente dos intervalos internos que o próprio
// @testing-library/dom usa em waitFor/findBy* (tipicamente 50ms). Se interceptássemos TODO
// setInterval de forma cega, quebraríamos o mecanismo de espera do Testing Library (cada
// chamada a waitFor/findBy* sobrescreveria intervalCallback com sua própria função de
// recheque, nunca com o callback real de polling do componente). Por isso: apenas chamadas
// com delay === POLL_INTERVAL_MS são desviadas para controle manual; qualquer outro delay
// (ex.: o do próprio Testing Library) continua usando o setInterval/clearInterval REAIS.
const POLL_INTERVAL_MS = 2000;

let intervalCallback: (() => void) | null = null;
let intervalCleared = false;
let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
const FAKE_INTERVAL_ID = 4242 as unknown as ReturnType<typeof window.setInterval>;
let realSetInterval: typeof window.setInterval;
let realClearInterval: typeof window.clearInterval;

beforeEach(() => {
  intervalCallback = null;
  intervalCleared = false;
  realSetInterval = window.setInterval.bind(window);
  realClearInterval = window.clearInterval.bind(window);
  setIntervalSpy = vi.fn((cb: () => void, ms?: number, ...args: unknown[]) => {
    if (ms === POLL_INTERVAL_MS) {
      intervalCallback = cb;
      return FAKE_INTERVAL_ID;
    }
    return realSetInterval(cb as TimerHandler, ms, ...args);
  });
  clearIntervalSpy = vi.fn((id?: ReturnType<typeof window.setInterval>) => {
    if (id === FAKE_INTERVAL_ID) {
      intervalCleared = true;
      intervalCallback = null;
      return;
    }
    return realClearInterval(id as unknown as number);
  });
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function tick() {
  if (!intervalCallback) return;
  const cb = intervalCallback;
  await act(async () => {
    cb();
    // Deixa a cadeia real fetch() -> response.json() -> .then(...) do componente resolver
    // (várias microtasks) antes de seguir -- sem isso o estado (activeRequest) ainda não
    // teria sido atualizado quando a asserção seguinte rodar.
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe("PubChemIngestionPanel -- validação de CIDs", () => {
  it("rejeita mais de 10 CIDs com mensagem explícita", async () => {
    vi.stubGlobal("fetch", mockFetch({}));
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, Array.from({ length: 11 }, (_, i) => i + 1).join(","));
    expect(await screen.findByRole("alert")).toHaveTextContent(/No máximo 10 CIDs/i);
  });

  it("rejeita entrada não numérica com mensagem explícita", async () => {
    vi.stubGlobal("fetch", mockFetch({}));
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244, abc, 702");
    expect(await screen.findByRole("alert")).toHaveTextContent(/apenas números são aceitos/i);
  });
});

describe("PubChemIngestionPanel -- regressão de componente que sustenta o E2E (rodada Windows 7/9)", () => {
  it("painel expõe os controles administrativos essenciais: campo de CIDs, Dry-run e Submeter ingestão", async () => {
    // Regressão de componente que sustenta a correção do E2E científico (rodada Windows
    // 7/9, commit 4d24b4a, falha 2). O E2E real mostrou, na produção, o painel administrativo
    // totalmente funcional (campo de CIDs, botão Dry-run, botão Submeter ingestão) -- a falha
    // do E2E era do texto literal esperado, não de um controle ausente. Este teste reproduz o
    // mesmo contrato funcional aqui, em nível de componente, escopado ao próprio painel
    // (data-testid="pubchem-ingestion-panel"), sem depender de nenhuma frase editorial --
    // exatamente como a correção do spec.ts. Uma regressão futura que remova qualquer um
    // desses controles quebra este teste também, não só o E2E manual.
    vi.stubGlobal("fetch", mockFetch({}));
    renderPanel();
    const panel = await screen.findByTestId("pubchem-ingestion-panel");
    expect(within(panel).getByLabelText("Lista de CIDs")).toBeVisible();
    expect(within(panel).getByRole("button", { name: "Dry-run" })).toBeVisible();
    expect(within(panel).getByRole("button", { name: "Submeter ingestão" })).toBeVisible();
  });
});

describe("PubChemIngestionPanel -- dry-run e submissão", () => {
  it("dry-run chama o endpoint de dry-run e mostra status sem persistir (dry_run=true na resposta)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ submitResponse: makeRequest({ dry_run: true, status: "queued" }) }),
    );
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244");
    await user.click(screen.getByRole("button", { name: "Dry-run" }));
    const status = await screen.findByTestId("ingestion-request-status");
    expect(status).toHaveTextContent(/dry-run — nenhuma entidade persistida/i);
    expect(screen.getByTestId("ingestion-status-value")).toHaveTextContent(/na fila/i);
  });

  it("submissão real chama o endpoint de criação (sem dry_run) e acompanha status via polling", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        statusSequence: [
          makeRequest({ status: "running" }),
          makeRequest({ status: "succeeded", summary: { received_count: 1, created_count: 1, updated_count: 0, unchanged_count: 0, rejected_count: 0, conflicts_count: 0 } }),
        ],
      }),
    );
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244");
    await user.click(screen.getByRole("button", { name: "Submeter ingestão" }));
    await screen.findByTestId("ingestion-request-status");
    expect(setIntervalSpy).toHaveBeenCalled();

    await tick();
    await waitFor(() => expect(screen.getByTestId("ingestion-status-value")).toHaveTextContent(/em execução/i));

    await tick();
    await waitFor(() => expect(screen.getByTestId("ingestion-status-value")).toHaveTextContent(/concluído/i));
    expect(screen.getByText(/Criados: 1/)).toBeInTheDocument();
    // Status terminal deve parar o polling.
    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  it("conflito detectado durante a ingestão fica visível (status parcial)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        statusSequence: [
          makeRequest({ status: "partial", summary: { conflicts_count: 1 } }),
        ],
        conflicts: [
          {
            id: "conf-1",
            ingestion_request_id: "req-1",
            external_record_id: "9999",
            conflict_type: "inchikey_shared_with_other_entity",
            entity_id: "sci-a",
            other_entity_id: "sci-b",
            details: null,
            resolved: false,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "9999");
    await user.click(screen.getByRole("button", { name: "Submeter ingestão" }));
    await screen.findByTestId("ingestion-request-status");
    await tick();
    const conflictsBlock = await screen.findByTestId("ingestion-conflicts");
    expect(conflictsBlock).toHaveTextContent("inchikey_shared_with_other_entity");
  });

  it("cancelamento: botão aparece enquanto em execução e chama o endpoint de cancelamento", async () => {
    vi.stubGlobal("fetch", mockFetch({ submitResponse: makeRequest({ status: "running" }) }));
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244");
    await user.click(screen.getByRole("button", { name: "Submeter ingestão" }));
    const cancelButton = await screen.findByRole("button", { name: "Cancelar" });
    await user.click(cancelButton);
    await waitFor(() => expect(screen.getByTestId("ingestion-status-value")).toHaveTextContent(/cancelado/i));
  });

  it("desmontar o componente para o polling (clearInterval chamado, sem intervalo órfão)", async () => {
    vi.stubGlobal("fetch", mockFetch({ submitResponse: makeRequest({ status: "running" }) }));
    const { unmount } = renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244");
    await user.click(screen.getByRole("button", { name: "Submeter ingestão" }));
    await screen.findByTestId("ingestion-request-status");
    expect(setIntervalSpy).toHaveBeenCalled();
    unmount();
    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(intervalCleared).toBe(true);
  });

  it("erro 403 na submissão é exibido, nunca escondido", async () => {
    vi.stubGlobal("fetch", mockFetch({ submitStatus: 403, submitMessage: "Apenas administradores podem submeter ingestões" }));
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244");
    await user.click(screen.getByRole("button", { name: "Submeter ingestão" }));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("Apenas administradores podem submeter ingestões"))).toBe(true);
  });

  it("erro 429 (rate limit) e 503 (indisponível) são exibidos sem esconder a falha", async () => {
    vi.stubGlobal("fetch", mockFetch({ submitStatus: 429, submitMessage: "Limite de requisições excedido" }));
    renderPanel();
    const input = await screen.findByLabelText("Lista de CIDs");
    const user = userEvent.setup();
    await user.type(input, "2244");
    await user.click(screen.getByRole("button", { name: "Dry-run" }));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("Limite de requisições excedido"))).toBe(true);
  });
});
