import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect, type ReactNode } from "react";
import { AuthProvider, useAuth } from "../src/context/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { ScientificEntityDetailPage } from "../src/pages/ScientificEntityDetailPage";

// Adendo de Interface Científica Mínima (Fase Q) -- testes de componente da página de detalhe
// /app/scientific-data/:entityId. Mesmo padrão de AutoLogin + fetch mockado usado em
// MaterialDetailPage.test.tsx e ScientificDataPage.test.tsx.

const RESEARCHER_EMAIL = "researcher@biomatcad.example";
const ENTITY_ID = "sci-entity-detail-1";
const OTHER_ENTITY_ID = "sci-entity-detail-2";

const BASE_ENTITY = {
  id: ENTITY_ID,
  organization_id: null,
  entity_type: "chemical_substance",
  preferred_name: "Ácido acetilsalicílico (detalhe)",
  review_status: "draft",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  description: "Substância de demonstração para os testes de detalhe científico.",
  identifiers: [],
};

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

interface Fixtures {
  entity?: unknown;
  entityError?: { status: number; message: string };
  identifiers?: unknown[];
  observations?: unknown[];
  provenance?: unknown[];
  rawSourceRecords?: unknown[];
  biologicalEvidence?: unknown[];
  supplierProducts?: unknown[];
  crystalStructures?: unknown[];
  conflicts?: unknown[];
  reviewHistory?: unknown[];
}

function mockFetch(fx: Fixtures) {
  return vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/api/v1/auth/login")) {
      return jsonResponse({ access_token: "tok-researcher", token_type: "bearer" });
    }
    if (url.endsWith("/api/v1/auth/me")) {
      return jsonResponse({ id: "user-researcher", email: RESEARCHER_EMAIL, full_name: "Pesquisador", role: "researcher", organization_id: "org-1" });
    }
    if (url.endsWith("/api/v1/scientific-entities/property-definitions")) {
      return jsonResponse(PROPERTY_DEFINITIONS);
    }
    if (url.match(/\/scientific-entities\/[^/]+\/identifiers$/)) return jsonResponse(fx.identifiers ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/property-observations$/)) return jsonResponse(fx.observations ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/provenance$/)) return jsonResponse(fx.provenance ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/raw-source-records$/)) return jsonResponse(fx.rawSourceRecords ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/biological-evidence$/)) return jsonResponse(fx.biologicalEvidence ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/supplier-products$/)) return jsonResponse(fx.supplierProducts ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/crystal-structures$/)) return jsonResponse(fx.crystalStructures ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/conflicts$/)) return jsonResponse(fx.conflicts ?? []);
    if (url.match(/\/scientific-entities\/[^/]+\/review-history$/)) return jsonResponse(fx.reviewHistory ?? []);
    if (url.match(/\/scientific-entities\/[^/]+$/)) {
      if (fx.entityError) return errorResponse(fx.entityError.status, fx.entityError.message);
      return jsonResponse(fx.entity ?? BASE_ENTITY);
    }
    return Promise.reject(new Error(`fetch não mockado neste teste para: ${url}`));
  });
}

function AutoLogin({ children }: { children: ReactNode }) {
  const { login, isAuthenticated } = useAuth();
  useEffect(() => {
    login(RESEARCHER_EMAIL, "e2e-synthetic-password-123").catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!isAuthenticated) return null;
  return <>{children}</>;
}

function renderDetail(entityId = ENTITY_ID) {
  return render(
    <MemoryRouter initialEntries={[`/app/scientific-data/${entityId}`]}>
      <ThemeProvider>
        <AuthProvider>
          <AutoLogin>
            <Routes>
              <Route path="/app/scientific-data/:entityId" element={<ScientificEntityDetailPage />} />
            </Routes>
          </AutoLogin>
        </AuthProvider>
      </ThemeProvider>
    </MemoryRouter>,
  );
}

describe("ScientificEntityDetailPage -- carregamento e visão geral", () => {
  it("mostra carregamento e depois o nome/tipo da entidade com aviso de uso responsável", async () => {
    vi.stubGlobal("fetch", mockFetch({}));
    renderDetail();
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" })).toBeInTheDocument();
    expect(screen.getByText(/Registros importados não equivalem a validação científica/i)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("mostra estado de erro (ex.: 404) sem esconder a falha", async () => {
    vi.stubGlobal("fetch", mockFetch({ entityError: { status: 404, message: "Entidade não encontrada" } }));
    renderDetail(OTHER_ENTITY_ID);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Entidade não encontrada");
    vi.unstubAllGlobals();
  });

  it("propaga 403 (registro privado de outra organização) como erro visível, nunca escondido", async () => {
    vi.stubGlobal("fetch", mockFetch({ entityError: { status: 403, message: "Sem acesso a este registro" } }));
    renderDetail();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sem acesso a este registro");
    vi.unstubAllGlobals();
  });
});

describe("ScientificEntityDetailPage -- propriedades", () => {
  it("propriedade calculada é rotulada como 'calculado', nunca como 'validado'", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        observations: [
          {
            id: "obs-1",
            property_definition_id: "def-mw",
            value_numeric: 180.16,
            value_min: null,
            value_max: null,
            value_text: null,
            unit_original: "g/mol",
            value_normalized: 180.16,
            method: "DFT",
            condition_temperature_k: 298.15,
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
      }),
    );
    renderDetail();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" });
    await user.click(screen.getByRole("button", { name: "Propriedades" }));
    const table = await screen.findByTestId("properties-table");
    expect(within(table).getByText("calculado (não é medição experimental)")).toBeInTheDocument();
    expect(within(table).queryByText(/validado/i)).not.toBeInTheDocument();
    expect(within(table).getByText("298.15 K")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("campo ausente aparece como '—' e valor real zero é distinto (nunca ambos '—')", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        observations: [
          {
            id: "obs-zero",
            property_definition_id: "def-mw",
            value_numeric: 0,
            value_min: null,
            value_max: null,
            value_text: null,
            unit_original: "g/mol",
            value_normalized: null,
            method: null,
            condition_temperature_k: null,
            condition_pressure_kpa: null,
            condition_ph: null,
            condition_medium: null,
            conditions_extra: null,
            uncertainty_low: null,
            uncertainty_high: null,
            evidence_type: "experimental",
            reference_id: null,
            source_id: null,
            source_location: null,
            review_status: "reviewed",
          },
        ],
      }),
    );
    renderDetail();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" });
    await user.click(screen.getByRole("button", { name: "Propriedades" }));
    const table = await screen.findByTestId("properties-table");
    const row = within(table).getByText("0").closest("tr");
    expect(row).not.toBeNull();
    // Linha com value_numeric=0 (valor real, não ausente) mostra literalmente "0" na coluna
    // "Valor original" -- nunca "—" -- enquanto as colunas realmente ausentes (valor
    // normalizado, condições, método, incerteza) mostram "—". As duas coisas nunca podem se
    // confundir: por isso a asserção de "0" acima já prova que o valor real não virou "—", e
    // aqui confirmamos que a mesma linha também tem campos genuinamente ausentes.
    expect(within(row as HTMLElement).getAllByText("—").length).toBeGreaterThanOrEqual(3);
    vi.unstubAllGlobals();
  });
});

describe("ScientificEntityDetailPage -- proveniência, snapshots e rótulos de origem", () => {
  it("aba de proveniência lista entradas com fonte", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        provenance: [
          {
            observation_id: "obs-1",
            reference: null,
            source: { id: "src-1", name: "PubChem PUG REST", source_type: "connector", base_url: null, publisher: null, license: null, version: null, accessed_at: null, redistribution_status: "allowed" },
          },
        ],
      }),
    );
    renderDetail();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" });
    await user.click(screen.getByRole("button", { name: "Proveniência" }));
    const entry = await screen.findByTestId("provenance-entry");
    expect(entry).toHaveTextContent("PubChem PUG REST");
    vi.unstubAllGlobals();
  });

  it("dados de origem PubChem real mostram o aviso de fonte externa importada", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        rawSourceRecords: [
          {
            id: "raw-1",
            source_id: "src-1",
            connector_id: "pubchem_pug_rest",
            connector_version: "1.0.0",
            external_record_id: "2244",
            requested_endpoint: "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/JSON",
            http_status: 200,
            content_type: "application/json",
            fetched_at: "2026-01-01T00:00:00Z",
            payload_sha256: "a".repeat(64),
            payload_size_bytes: 128,
            schema_mapping_version: "1",
            predecessor_record_id: null,
            parsing_status: "parsed",
            retention_policy: "retain",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );
    renderDetail();
    expect(
      await screen.findByText(/Fonte externa importada\. Exige curadoria antes de qualquer uso científico conclusivo\./i),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("dados sintéticos de demonstração mostram o aviso de fixture sintética, nunca atribuído ao PubChem", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        rawSourceRecords: [
          {
            id: "raw-2",
            source_id: "src-1",
            connector_id: "synthetic_demo_connector",
            connector_version: "0.0.0-demo",
            external_record_id: "SYNTH-DEMO-0001",
            requested_endpoint: "synthetic://demo/SYNTH-DEMO-0001",
            http_status: 200,
            content_type: "application/json",
            fetched_at: "2026-01-01T00:00:00Z",
            payload_sha256: "b".repeat(64),
            payload_size_bytes: 64,
            schema_mapping_version: "1",
            predecessor_record_id: null,
            parsing_status: "parsed",
            retention_policy: "demo_synthetic",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );
    renderDetail();
    expect(
      await screen.findByText(/Dado sintético de demonstração — não atribuído ao PubChem\./i),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("aba de snapshots mostra o registro bruto (conector, SHA-256 truncado)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        rawSourceRecords: [
          {
            id: "raw-3",
            source_id: "src-1",
            connector_id: "synthetic_demo_connector",
            connector_version: "0.0.0-demo",
            external_record_id: "SYNTH-DEMO-0002",
            requested_endpoint: "synthetic://demo/SYNTH-DEMO-0002",
            http_status: 200,
            content_type: "application/json",
            fetched_at: "2026-01-01T00:00:00Z",
            payload_sha256: "c".repeat(64),
            payload_size_bytes: 64,
            schema_mapping_version: "1",
            predecessor_record_id: null,
            parsing_status: "parsed",
            retention_policy: "demo_synthetic",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );
    renderDetail();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" });
    await user.click(screen.getByRole("button", { name: "Snapshots" }));
    const table = await screen.findByTestId("snapshots-table");
    expect(within(table).getByText("synthetic_demo_connector")).toBeInTheDocument();
    expect(within(table).getByText("SYNTH-DEMO-0002")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe("ScientificEntityDetailPage -- conflitos", () => {
  it("aba de conflitos mostra um conflito visível (não resolvido)", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        conflicts: [
          {
            id: "conf-1",
            ingestion_request_id: "req-1",
            external_record_id: "9999",
            conflict_type: "inchikey_shared_with_other_entity",
            entity_id: ENTITY_ID,
            other_entity_id: "sci-other-entity",
            details: { nota: "conflito sintético de demonstração" },
            resolved: false,
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );
    renderDetail();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" });
    await user.click(screen.getByRole("button", { name: "Conflitos" }));
    const list = await screen.findByTestId("conflicts-list");
    expect(within(list).getByText(/inchikey_shared_with_other_entity/)).toBeInTheDocument();
    expect(within(list).getByText(/não resolvido/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("sem conflitos mostra estado vazio explícito, nunca lista vazia silenciosa como sucesso ambíguo", async () => {
    vi.stubGlobal("fetch", mockFetch({}));
    renderDetail();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ácido acetilsalicílico (detalhe)" });
    await user.click(screen.getByRole("button", { name: "Conflitos" }));
    expect(await screen.findByText("Nenhum conflito de ingestão registrado para esta entidade")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
