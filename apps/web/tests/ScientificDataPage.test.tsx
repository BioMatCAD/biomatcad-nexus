import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { ScientificDataPage } from "../src/pages/ScientificDataPage";
import { Sidebar } from "../src/components/layout/Sidebar";

// Adendo de Interface Científica Mínima (Fase Q) -- testes de componente da listagem
// /app/scientific-data. Segue o padrão estabelecido em MaterialDetailPage.test.tsx: login real
// via AuthContext (mockando apenas fetch), nunca acesso de rede real.

const RESEARCHER_EMAIL = "researcher@biomatcad.example";
const ADMIN_EMAIL = "admin@biomatcad.example";

const BIOMATERIAL_ID = "sci-bio-1";
const CHEMICAL_ID = "sci-chem-1";

function makeUser(role: string) {
  return {
    id: `user-${role}`,
    email: role === "admin" ? ADMIN_EMAIL : RESEARCHER_EMAIL,
    full_name: role === "admin" ? "Admin Sintético" : "Pesquisador Sintético",
    role,
    organization_id: "org-1",
  };
}

const SAMPLE_ENTITIES = [
  {
    id: BIOMATERIAL_ID,
    organization_id: null,
    entity_type: "biomaterial",
    preferred_name: "Hidroxiapatita sintética",
    review_status: "reviewed",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: CHEMICAL_ID,
    organization_id: null,
    entity_type: "chemical_substance",
    preferred_name: "Ibuprofeno (importado)",
    review_status: "draft",
    is_active: true,
    created_at: "2026-02-01T00:00:00Z",
  },
];

const PROPERTY_DEFINITIONS = [
  {
    id: "def-mw",
    canonical_key: "molecular_weight",
    name: "Massa molecular",
    dimension: "mass",
    canonical_unit: "g/mol",
    value_type: "numeric",
    applicable_domain: "chemical_substance",
  },
];

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

interface MockFetchOptions {
  role: string;
  entities?: unknown[];
  identifiersById?: Record<string, unknown[]>;
  observationsById?: Record<string, unknown[]>;
  entitiesError?: { status: number; message: string };
}

function mockFetch(opts: MockFetchOptions) {
  return vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/login")) {
      return jsonResponse({ access_token: `tok-${opts.role}`, token_type: "bearer" });
    }
    if (url.endsWith("/api/v1/auth/me")) {
      return jsonResponse(makeUser(opts.role));
    }
    if (url.endsWith("/api/v1/scientific-entities/property-definitions")) {
      return jsonResponse(PROPERTY_DEFINITIONS);
    }
    if (url.endsWith("/api/v1/scientific-entities/sources")) {
      return jsonResponse([{ id: "src-1", name: "Fonte sintética", source_type: "database", base_url: null, publisher: null, license: null, version: null, accessed_at: null, redistribution_status: "allowed" }]);
    }
    if (url.endsWith("/api/v1/scientific-entities")) {
      if (opts.entitiesError) return errorResponse(opts.entitiesError.status, opts.entitiesError.message);
      return jsonResponse(opts.entities ?? SAMPLE_ENTITIES);
    }
    const identifiersMatch = url.match(/\/scientific-entities\/([^/]+)\/identifiers$/);
    if (identifiersMatch) {
      return jsonResponse(opts.identifiersById?.[identifiersMatch[1]] ?? []);
    }
    const obsMatch = url.match(/\/scientific-entities\/([^/]+)\/property-observations$/);
    if (obsMatch) {
      return jsonResponse(opts.observationsById?.[obsMatch[1]] ?? []);
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

function AutoLogin({ role, children }: { role: string; children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  useEffect(() => {
    const email = role === "admin" ? ADMIN_EMAIL : RESEARCHER_EMAIL;
    login(email, "e2e-synthetic-password-123").catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function renderPage(role: string) {
  return render(
    <MemoryRouter initialEntries={["/app/scientific-data"]}>
      <ThemeProvider>
        <AuthProvider>
          <AutoLogin role={role}>
            <Routes>
              <Route path="/app/scientific-data" element={<ScientificDataPage />} />
            </Routes>
          </AutoLogin>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>,
  );
}

describe("Sidebar -- navegação para Dados científicos", () => {
  it("inclui o link 'Dados científicos' apontando para /app/scientific-data", () => {
    render(
      <MemoryRouter>
        <ThemeProvider>
          <Sidebar />
        </ThemeProvider>
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Dados científicos" });
    expect(link).toHaveAttribute("href", "/app/scientific-data");
  });
});

describe("ScientificDataPage -- listagem", () => {
  it("mostra estado de carregamento e depois a tabela de entidades", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher" }));
    renderPage("researcher");
    expect(await screen.findByRole("status")).toBeInTheDocument();
    const table = await screen.findByTestId("scientific-entities-table");
    expect(within(table).getByText("Hidroxiapatita sintética")).toBeInTheDocument();
    expect(within(table).getByText("Ibuprofeno (importado)")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("mostra estado vazio quando não há entidades cadastradas", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher", entities: [] }));
    renderPage("researcher");
    expect(await screen.findByText("Nenhuma entidade científica cadastrada ainda")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("mostra estado de erro sem esconder a falha (ex.: 503)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ role: "researcher", entitiesError: { status: 503, message: "Serviço indisponível" } }),
    );
    renderPage("researcher");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Serviço indisponível");
    vi.unstubAllGlobals();
  });

  it("filtra por texto de busca (nome)", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher" }));
    renderPage("researcher");
    const table = await screen.findByTestId("scientific-entities-table");
    expect(within(table).getByText("Hidroxiapatita sintética")).toBeInTheDocument();
    const search = screen.getByLabelText("Buscar por nome");
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    await user.type(search, "ibuprofeno");
    await waitFor(() => {
      expect(screen.queryByText("Hidroxiapatita sintética")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Ibuprofeno (importado)")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("filtra por estado de revisão e mostra estado vazio de filtro sem resultado", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher" }));
    renderPage("researcher");
    await screen.findByTestId("scientific-entities-table");
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Filtrar por estado de revisão"), "rejected");
    expect(await screen.findByText("Nenhum resultado para os filtros aplicados")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("campos ausentes (CID/InChIKey/massa) aparecem como '—', nunca como vazio/zero fabricado", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher" }));
    renderPage("researcher");
    await screen.findByTestId("scientific-entities-table");
    await waitFor(() => {
      expect(screen.getByTestId(`cid-${BIOMATERIAL_ID}`)).toHaveTextContent("—");
    });
    expect(screen.getByTestId(`inchikey-${BIOMATERIAL_ID}`)).toHaveTextContent("—");
    expect(screen.getByTestId(`mw-${BIOMATERIAL_ID}`)).toHaveTextContent("—");
    vi.unstubAllGlobals();
  });

  it("um valor real de massa molecular igual a 0 é distinto de campo ausente ('0', nunca '—')", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        role: "researcher",
        identifiersById: { [CHEMICAL_ID]: [{ id: "id-1", namespace: "pubchem_cid", identifier: "2244", identifier_normalized: "2244", verification_status: "verified", created_at: "2026-01-01T00:00:00Z" }] },
        observationsById: {
          [CHEMICAL_ID]: [
            {
              id: "obs-1",
              property_definition_id: "def-mw",
              value_numeric: 0,
              value_min: null,
              value_max: null,
              value_text: null,
              unit_original: "g/mol",
              value_normalized: 0,
              method: "calculated",
              condition_temperature_k: null,
              condition_pressure_kpa: null,
              condition_ph: null,
              condition_medium: null,
              conditions_extra: null,
              uncertainty_low: null,
              uncertainty_high: null,
              evidence_type: "calculated",
              reference_id: null,
              source_id: null,
              source_location: null,
              review_status: "draft",
            },
          ],
        },
      }),
    );
    renderPage("researcher");
    await screen.findByTestId("scientific-entities-table");
    await waitFor(() => {
      expect(screen.getByTestId(`mw-${CHEMICAL_ID}`)).toHaveTextContent("0 g/mol");
    });
    expect(screen.getByTestId(`cid-${CHEMICAL_ID}`)).toHaveTextContent("2244");
    vi.unstubAllGlobals();
  });

  it("painel administrativo PubChem NÃO aparece para usuário pesquisador comum", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher" }));
    renderPage("researcher");
    await screen.findByTestId("scientific-entities-table");
    expect(screen.queryByTestId("pubchem-ingestion-panel")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("painel administrativo PubChem aparece para usuário admin", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "admin" }));
    renderPage("admin");
    await screen.findByTestId("scientific-entities-table");
    expect(await screen.findByTestId("pubchem-ingestion-panel")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("exibe o aviso de uso responsável permanentemente", async () => {
    vi.stubGlobal("fetch", mockFetch({ role: "researcher" }));
    renderPage("researcher");
    expect(
      await screen.findByText(/Registros importados não equivalem a validação científica/i),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
