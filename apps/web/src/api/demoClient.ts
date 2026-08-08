import type { ApiClient } from "./client";
import { offlineValidateResponse } from "./recipeValidationOffline";
import {
  ApiError,
  type ArtifactResponse,
  type BiologicalEvidenceResponse,
  type ConnectorInfoResponse,
  type CrystalStructureReferenceResponse,
  type DesignRunResponse,
  type GeometryJobResponse,
  type GeometryRecipeBody,
  type IngestionConflictResponse,
  type IngestionRequestResponse,
  type ManifestResponse,
  type MaterialCreateRequest,
  type MaterialDetail,
  type MaterialSummary,
  type ProjectCreateRequest,
  type ProjectResponse,
  type PropertyDefinitionResponse,
  type PropertyObservationResponse,
  type ProvenanceEntry,
  type RawSourceRecordResponse,
  type RecipeResponse,
  type ReviewDecisionOutcome,
  type ReviewDecisionResponse,
  type ScientificEntityDetail,
  type ScientificEntitySummary,
  type SupplierProductResponse,
} from "./types";

// Cliente de demonstração usado exclusivamente no build do GitHub Pages (Prompt Mestre §3.3,
// §7.1): não existe backend real no Pages. Todos os dados são sintéticos e claramente
// rotulados. Login "funciona" apenas contra um usuário sintético fixo, sem emitir JWT válido
// de verdade — é uma simulação, nunca deve ser confundida com autenticação real.
const SYNTHETIC_DELAY_MS = 350;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), SYNTHETIC_DELAY_MS));
}

const SAMPLE_STL_FILENAME = "sample-scaffold-block-gyroid.stl";

const SAMPLE_MATERIAL: MaterialDetail = {
  id: "demo-material-1",
  name: "beta-TCP (exemplo sintético de demonstração)",
  category: "ceramic",
  source_type: "synthetic",
  review_status: "draft",
  created_at: new Date().toISOString(),
  description: "Material sintético de demonstração para o modo GitHub Pages -- não é um dado científico real.",
  properties: [
    {
      id: "demo-prop-1",
      property_name: "compressive_strength",
      value: 12.5,
      unit: "MPa",
      source: "valor sintético de demonstração, não medido experimentalmente",
      reference_id: null,
      method: "sintético (demo)",
      uncertainty_low: 10.0,
      uncertainty_high: 15.0,
      version: 1,
      review_status: "draft",
      created_at: new Date().toISOString(),
    },
  ],
  references: [
    {
      id: "demo-ref-1",
      citation_text: "Referência sintética de demonstração, sem DOI real.",
      doi: null,
      url: null,
      source_document: null,
      page_reference: null,
      created_at: new Date().toISOString(),
    },
  ],
};

const SAMPLE_PROJECT: ProjectResponse = {
  id: "demo-project-1",
  organization_id: "demo-org",
  owner_user_id: "demo-user",
  name: "Projeto de demonstração",
  description: "Projeto sintético pré-carregado no modo GitHub Pages.",
  status: "active",
  created_at: new Date().toISOString(),
};

const SAMPLE_RECIPE_BODY: GeometryRecipeBody = {
  schema_version: "1.0.0",
  domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
  topology: { kind: "gyroid", cell_size_mm: 2, wall_thickness_mm: 0.4, isovalue: 0, target_porosity_pct: 60 },
  resolution: { voxel_size_mm: 0.2 },
  mode: "preview",
  seed: 42,
  compute_limits: { max_duration_seconds: 60, max_memory_mb: 512, max_voxel_count: 1000000 },
  output_formats: ["stl"],
};

const SAMPLE_RECIPE: RecipeResponse = {
  id: "demo-recipe-1",
  organization_id: "demo-org",
  project_id: SAMPLE_PROJECT.id,
  name: "Receita de exemplo (bloco gyroid)",
  schema_version: "1.0.0",
  canonical_json: SAMPLE_RECIPE_BODY,
  checksum_sha256: "demo-fingerprint-preloaded",
  version: 1,
  parent_recipe_id: null,
  status: "validated",
  created_at: new Date().toISOString(),
};

// ---------------------------------------------------------------------------------------
// Incremento 2.3 -- dados científicos + ingestão PubChem (Adendo de Interface Científica
// Mínima). Espelha o MESMO conteúdo do seed sintético real (seed_scientific_data.py) na
// medida do possível -- nomes/rótulos claramente fictícios, nunca um CID/InChIKey real do
// PubChem. O modo demo (GitHub Pages) não tem backend real, então TODA a ingestão aqui é
// simulada via setTimeout, exatamente como `simulateJobProgress` já faz para jobs geométricos.
const DEMO_BIOMATERIAL_ID = "demo-sci-entity-biomaterial";
const DEMO_CHEMICAL_ID = "demo-sci-entity-chemical";
const DEMO_DRUG_ID = "demo-sci-entity-drug";
// CID reservado (fictício) que, se incluído numa submissão de demonstração, simula uma
// solicitação "partial" com um conflito -- nunca um CID real do PubChem.
const DEMO_CONFLICT_CID = "9999";

const SAMPLE_SCI_ENTITIES: ScientificEntityDetail[] = [
  {
    id: DEMO_BIOMATERIAL_ID,
    organization_id: null,
    entity_type: "biomaterial",
    preferred_name: "Hidroxiapatita Sintética de Demonstração (fictícia)",
    review_status: "reviewed",
    is_active: true,
    created_at: new Date().toISOString(),
    description: "Biomaterial fictício usado apenas para demonstrar o domínio científico. Sem dado real.",
    updated_at: new Date().toISOString(),
    identifiers: [
      {
        id: "demo-sci-identifier-1",
        namespace: "SYNTHETIC_DEMO_ID",
        identifier: "SYNTH-BIOMAT-0001",
        identifier_normalized: "SYNTH-BIOMAT-0001",
        verification_status: "unverified",
        created_at: new Date().toISOString(),
      },
    ],
  },
  {
    id: DEMO_CHEMICAL_ID,
    organization_id: null,
    entity_type: "chemical_substance",
    preferred_name: "Ácido Poliláctico Fictício de Demonstração",
    review_status: "draft",
    is_active: true,
    created_at: new Date().toISOString(),
    description: "Substância química fictícia de demonstração. Sem dado real -- não importada do PubChem.",
    updated_at: new Date().toISOString(),
    identifiers: [],
  },
  {
    id: DEMO_DRUG_ID,
    organization_id: null,
    entity_type: "drug",
    preferred_name: "Fármaco Fictício de Demonstração X-100",
    review_status: "rejected",
    is_active: true,
    created_at: new Date().toISOString(),
    description: "Fármaco inteiramente fictício, criado apenas para teste do domínio. Não existe na realidade.",
    updated_at: new Date().toISOString(),
    identifiers: [],
  },
];

const SAMPLE_PROPERTY_DEFINITIONS: PropertyDefinitionResponse[] = [
  {
    id: "demo-propdef-young-modulus",
    canonical_key: "young_modulus_demo",
    name: "Módulo de Young (demonstração)",
    dimension: "mechanical",
    canonical_unit: "GPa",
    value_type: "numeric",
    applicable_domain: "generic",
  },
];

const SAMPLE_PROPERTY_OBSERVATIONS: Record<string, PropertyObservationResponse[]> = {
  [DEMO_BIOMATERIAL_ID]: [
    {
      id: "demo-sci-obs-alpha",
      property_definition_id: "demo-propdef-young-modulus",
      value_numeric: 12.3,
      value_min: null,
      value_max: null,
      value_text: null,
      unit_original: "GPa",
      value_normalized: null,
      method: "Ensaio de compressão fictício (fonte Alfa)",
      condition_temperature_k: null,
      condition_pressure_kpa: null,
      condition_ph: null,
      condition_medium: null,
      conditions_extra: null,
      uncertainty_low: null,
      uncertainty_high: null,
      evidence_type: "experimental",
      reference_id: null,
      source_id: "demo-sci-source-alpha",
      source_location: null,
      related_supplier_product_id: null,
      review_status: "reviewed",
      notes: "Observação sintética de demonstração -- fonte Alfa.",
      created_at: new Date().toISOString(),
    },
    {
      id: "demo-sci-obs-beta",
      property_definition_id: "demo-propdef-young-modulus",
      value_numeric: 15.7,
      value_min: null,
      value_max: null,
      value_text: null,
      unit_original: "GPa",
      value_normalized: null,
      method: "Ensaio de compressão fictício (fonte Beta)",
      condition_temperature_k: null,
      condition_pressure_kpa: null,
      condition_ph: null,
      condition_medium: null,
      conditions_extra: null,
      uncertainty_low: null,
      uncertainty_high: null,
      evidence_type: "experimental",
      reference_id: null,
      source_id: "demo-sci-source-beta",
      source_location: null,
      related_supplier_product_id: null,
      review_status: "draft",
      notes:
        "Observação sintética de demonstração -- fonte Beta. Valor DIVERGENTE da observação " +
        "da fonte Alfa, mantido como linha separada (nunca sobrescrita silenciosa).",
      created_at: new Date().toISOString(),
    },
  ],
};

const SAMPLE_PROVENANCE: Record<string, ProvenanceEntry[]> = {
  [DEMO_BIOMATERIAL_ID]: [
    {
      observation_id: "demo-sci-obs-alpha",
      reference: null,
      source: {
        id: "demo-sci-source-alpha",
        name: "Fonte Sintética Alfa de Demonstração",
        source_type: "database",
        base_url: null,
        publisher: "Fonte fictícia de demonstração -- não corresponde a nenhuma editora/banco real.",
        license: "Uso interno de demonstração apenas -- não redistribuir.",
        version: "demo-1",
        accessed_at: new Date().toISOString(),
        redistribution_status: "unknown",
      },
    },
  ],
};

const SAMPLE_BIOLOGICAL_EVIDENCE: Record<string, BiologicalEvidenceResponse[]> = {
  [DEMO_DRUG_ID]: [
    {
      id: "demo-sci-bioevidence-1",
      entity_id: DEMO_DRUG_ID,
      assay_type: "ensaio_fictício_demo",
      biological_model: "in_vitro_fictício",
      species: null,
      cell_line: "Linhagem celular fictícia de demonstração",
      organism: null,
      endpoint: "viabilidade_celular_fictícia",
      result_value: 72.5,
      result_text: "Resultado fictício de demonstração -- classificação apenas de pesquisa.",
      dose_value: 10.0,
      dose_unit: "ug_mL_fictício",
      duration_value: 24.0,
      duration_unit: "h",
      conditions: { nota: "Dado inteiramente sintético, não é validação clínica." },
      reference_id: null,
      source_id: null,
      research_classification_only: true,
      created_at: new Date().toISOString(),
    },
  ],
};

const SAMPLE_RAW_SOURCE_RECORDS: Record<string, RawSourceRecordResponse[]> = {
  [DEMO_BIOMATERIAL_ID]: [
    {
      id: "demo-sci-raw-record-1",
      source_id: "demo-sci-source-alpha",
      connector_id: "synthetic_demo_connector",
      connector_version: "0.0.0-demo",
      external_record_id: "SYNTH-DEMO-0001",
      requested_endpoint: "synthetic://demo/SYNTH-DEMO-0001",
      http_status: 200,
      content_type: "application/json",
      fetched_at: new Date().toISOString(),
      payload_sha256: "0".repeat(64),
      payload_size_bytes: 128,
      schema_mapping_version: "synthetic_demo_v1",
      predecessor_record_id: null,
      parsing_status: "parsed",
      retention_policy: "demo_synthetic",
      created_at: new Date().toISOString(),
    },
  ],
};

const demoConflict: IngestionConflictResponse = {
  id: "demo-sci-conflict-1",
  ingestion_request_id: "demo-ingestion-preseeded",
  external_record_id: DEMO_CONFLICT_CID,
  conflict_type: "inchikey_shared_with_other_entity",
  entity_id: DEMO_CHEMICAL_ID,
  other_entity_id: DEMO_DRUG_ID,
  details: {
    nota:
      "Conflito inteiramente sintético de demonstração -- nunca uma colisão real de InChIKey " +
      "do PubChem.",
  },
  resolved: false,
  created_at: new Date().toISOString(),
};

const SAMPLE_CONFLICTS: Record<string, IngestionConflictResponse[]> = {
  [DEMO_CHEMICAL_ID]: [demoConflict],
  [DEMO_DRUG_ID]: [demoConflict],
};

const SAMPLE_CONNECTORS: ConnectorInfoResponse[] = [
  {
    connector_id: "pubchem_pug_rest",
    version: "1",
    status: "implemented",
    description: "Conector PubChem PUG REST (piloto) -- simulado no modo demonstração (GitHub Pages).",
  },
];

const demoIngestionRequests: IngestionRequestResponse[] = [];
let demoIngestionRequestCounter = 0;

function simulateIngestionProgress(requestId: string, externalIds: string[], dryRun: boolean): void {
  setTimeout(() => {
    const req = demoIngestionRequests.find((r) => r.id === requestId);
    if (!req || req.status !== "queued") return;
    req.status = "running";
    req.started_at = new Date().toISOString();
  }, 350);

  setTimeout(() => {
    const req = demoIngestionRequests.find((r) => r.id === requestId);
    if (!req || req.status !== "running") return;
    const hasConflict = externalIds.includes(DEMO_CONFLICT_CID);
    req.status = hasConflict ? "partial" : "succeeded";
    req.finished_at = new Date().toISOString();
    req.summary = {
      received_count: externalIds.length,
      created_count: dryRun ? 0 : hasConflict ? externalIds.length - 1 : externalIds.length,
      updated_count: 0,
      unchanged_count: 0,
      rejected_count: 0,
      conflicts_count: hasConflict ? 1 : 0,
    };
  }, 1100);
}

const demoStore: {
  materials: MaterialDetail[];
  projects: ProjectResponse[];
  recipes: RecipeResponse[];
  designRuns: DesignRunResponse[];
  jobs: GeometryJobResponse[];
  artifacts: ArtifactResponse[];
  manifests: Record<string, ManifestResponse>;
} = {
  materials: [SAMPLE_MATERIAL],
  projects: [SAMPLE_PROJECT],
  recipes: [SAMPLE_RECIPE],
  designRuns: [],
  jobs: [],
  artifacts: [],
  manifests: {},
};

function toMaterialSummary(material: MaterialDetail): MaterialSummary {
  const { id, name, category, source_type, review_status, created_at } = material;
  return { id, name, category, source_type, review_status, created_at };
}

/**
 * Simula queued -> running -> succeeded/failed via setTimeout. Usado exclusivamente pelo modo
 * demo (GitHub Pages, sem backend real).
 *
 * Para topology.kind === "gyroid": populando métricas fixas e apontando o artefato STL para
 * um arquivo sintético pré-calculado versionado em public/demo-assets/ -- NUNCA saída real do
 * worker PicoGK (bloqueado neste sandbox, ver apps/geometry-worker/WORKER_STATUS.md).
 *
 * Para topology.kind === "voronoi_cell_edges_v1" (Incremento 2.2, rodada Voronoi, Seção 10):
 * NÃO existe nenhum artefato STL/métrica pré-calculada real para Voronoi nesta demonstração
 * estática (nenhuma execução do PicoGK real ocorreu neste sandbox -- ver
 * schemas/biomatcem/golden-recipes/METADATA.json). Fabricar uma geometria/métrica "de sucesso"
 * aqui seria exatamente o tipo de simulação enganosa que este projeto proíbe explicitamente.
 * Em vez disso, o job termina honestamente em "failed" com um erro estruturado explicando a
 * limitação -- o editor/validação/schema continuam funcionando normalmente em modo demo para
 * Voronoi, apenas a EXECUÇÃO simulada de um job é que não finge sucesso.
 */
function simulateJobProgress(jobId: string, topologyKind: string): void {
  setTimeout(() => {
    const job = demoStore.jobs.find((j) => j.id === jobId);
    if (!job || job.status !== "queued") return;
    job.status = "running";
    job.started_at = new Date().toISOString();
    job.progress_pct = 40;
  }, 400);

  setTimeout(() => {
    const job = demoStore.jobs.find((j) => j.id === jobId);
    if (!job || job.status !== "running") return;

    if (topologyKind !== "gyroid") {
      job.status = "failed";
      job.finished_at = new Date().toISOString();
      job.error_code = "DEMO_EXECUTION_UNAVAILABLE";
      job.error_message =
        `A demonstração estática do GitHub Pages não executa o worker PicoGK real. Apenas o ` +
        `exemplo pré-calculado Gyroid está disponível como demonstração completa nesta rodada ` +
        `(ver METADATA.json das golden recipes). A receita '${topologyKind}' foi validada e ` +
        `salva corretamente, mas a execução real requer o backend completo com PicoGK (ver ` +
        `roteiro de validação Windows / ADR-0007).`;
      return;
    }

    job.status = "succeeded";
    job.progress_pct = 100;
    job.finished_at = new Date().toISOString();
    job.worker_version = "0.1.0-demo-simulated";
    job.dotnet_version = "9.0.0-demo-simulated";
    job.picogk_version = "2.2.0-demo-simulated";
    job.duration_seconds = 1.2;
    job.metrics = {
      bounding_box_mm: [
        [-5, -5, -5],
        [5, 5, 5],
      ],
      volume_mm3: 400.0,
      porosity_pct_measured: 60.0,
      surface_area_mm2: 950.5,
      vertex_count_unique: 168,
      triangle_count: 336,
      is_watertight: true,
    };

    const stlArtifact: ArtifactResponse = {
      id: `demo-artifact-stl-${jobId}`,
      geometry_job_id: jobId,
      kind: "stl",
      // SHA-256 REAL de public/demo-assets/sample-scaffold-block-gyroid.stl (verificado via
      // sha256sum -- não é um placeholder). Precisa bater com o arquivo de verdade porque o
      // StlViewer agora verifica o checksum do lado do cliente (Seção 2/6 da auditoria do
      // visualizador); um placeholder aqui faria a demonstração do GitHub Pages falhar sempre
      // com "checksum divergente", em vez de carregar a malha sintética.
      sha256: "a1dffcd02a49df8dc514b63781ebed3028db7797a4d61cdb92c4f083d460fafc",
      size_bytes: 16884,
      created_at: new Date().toISOString(),
    };
    const manifestArtifact: ArtifactResponse = {
      id: `demo-artifact-manifest-${jobId}`,
      geometry_job_id: jobId,
      kind: "manifest",
      // O endpoint de download de demonstração serve o MESMO arquivo estático para stl e
      // manifest (ver artifactDownloadUrl abaixo) -- por isso o checksum aqui também precisa
      // ser o do arquivo real servido, não um placeholder, senão o botão de download do
      // manifesto falharia a verificação de checksum do lado do cliente.
      sha256: "a1dffcd02a49df8dc514b63781ebed3028db7797a4d61cdb92c4f083d460fafc",
      size_bytes: 16884,
      created_at: new Date().toISOString(),
    };
    demoStore.artifacts.push(stlArtifact, manifestArtifact);

    demoStore.manifests[jobId] = {
      id: `demo-manifest-${jobId}`,
      geometry_job_id: jobId,
      manifest_json: {
        job_id: jobId,
        note: "Manifesto SINTÉTICO de demonstração -- não gerado pelo worker PicoGK real (bloqueado neste sandbox).",
        recipe_canonical: SAMPLE_RECIPE_BODY,
        schema_version: "1.0.0",
        seed: SAMPLE_RECIPE_BODY.seed,
        worker_version: "0.1.0-demo-simulated",
        dotnet_version: "9.0.0-demo-simulated",
        picogk_version: "2.2.0-demo-simulated",
        duration_seconds: 1.2,
        metrics: job.metrics,
        generated_at: new Date().toISOString(),
      },
      manifest_sha256: "0".repeat(64),
      created_at: new Date().toISOString(),
    };
  }, 1200);
}

export const demoApiClient: ApiClient = {
  health: () => delay({ status: "ok" }),
  ready: () => delay({ status: "ok", database: "demo-synthetic" }),
  version: () => delay({ version: "0.1.0-demo", environment: "github-pages-demo" }),
  systemStatus: () =>
    delay({
      environment: "github-pages-demo",
      auth_mode: "DEV_AUTH" as const,
      clinical_suite_enabled: false,
      demo_mode: true,
      operational_states: [
        { kind: "research" as const, enabled: true },
        { kind: "laboratory" as const, enabled: false },
        { kind: "clinical_test" as const, enabled: false },
        { kind: "clinical_pilot" as const, enabled: false },
        { kind: "clinical_production" as const, enabled: false },
      ],
    }),
  // Dados SINTÉTICOS fixos -- o modo demo (GitHub Pages) não tem backend real, então não há
  // nenhuma verificação real a fazer. Nunca deve ser confundido com o painel real (que só
  // aparece quando VITE_API_BASE_URL aponta para uma API de verdade).
  observabilityStatus: () =>
    delay({
      generated_at: new Date().toISOString(),
      api: {
        state: "healthy" as const,
        detail: "Demonstração estática (GitHub Pages) -- sem backend real.",
        version: "0.1.0-demo",
        environment: "github-pages-demo",
      },
      database: { state: "healthy" as const, detail: "Simulado -- modo demonstração." },
      dispatcher: {
        state: "healthy" as const,
        detail: "Simulado -- modo demonstração.",
        dispatcher_id: "demo-dispatcher",
        pid: null,
        phase: "idle",
        last_poll_at: new Date().toISOString(),
        jobs_processed_total: 3,
        current_poll_interval_seconds: 3,
      },
      worker: {
        state: "unavailable" as const,
        detail: "Worker PicoGK real não roda no modo demonstração estática.",
        binary_found: false,
        worker_version: null,
        dotnet_version: null,
        picogk_version: null,
      },
      queue: { state: "healthy" as const, detail: "Simulado -- modo demonstração.", queued_count: 0, processing_count: 0 },
      storage: { state: "healthy" as const, detail: "Simulado -- modo demonstração.", path: "demo://artifacts", writable: false },
      versions: { api: "0.1.0-demo", schema_geometry_recipe: "1.0.0" },
      jobs_active: [],
      jobs_failed_recent: [],
    }),
  login: async ({ email, password }) => {
    if (email === "demo@biomatcad.example" && password === "demo-synthetic-password-123") {
      return delay({ access_token: "demo-simulated-token-not-a-real-jwt", token_type: "bearer", expires_in: 1800 });
    }
    await delay(null);
    throw new ApiError(401, { error: { id: "demo", code: "HTTP_401", message: "Credenciais inválidas (modo demonstração)." } });
  },
  me: () =>
    delay({
      id: "demo-user",
      email: "demo@biomatcad.example",
      full_name: "Usuário Sintético de Demonstração",
      role: "researcher",
      organization_id: "demo-org",
    }),

  // ---- Incremento 2.1 ----
  listMaterials: () => delay(demoStore.materials.map(toMaterialSummary)),
  getMaterial: (_token, materialId) => {
    const material = demoStore.materials.find((m) => m.id === materialId);
    if (!material) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Material não encontrado (demo)." } }));
    return delay(material);
  },
  createMaterial: (_token, payload: MaterialCreateRequest) => {
    const material: MaterialDetail = {
      id: `demo-material-${demoStore.materials.length + 1}`,
      name: payload.name,
      category: payload.category,
      source_type: payload.source_type,
      review_status: "draft",
      created_at: new Date().toISOString(),
      description: payload.description ?? null,
      properties: (payload.properties ?? []).map((p, i) => ({
        id: `demo-prop-${i}`,
        property_name: p.property_name,
        value: p.value,
        unit: p.unit,
        source: p.source,
        reference_id: p.reference_id ?? null,
        method: p.method ?? null,
        uncertainty_low: p.uncertainty_low ?? null,
        uncertainty_high: p.uncertainty_high ?? null,
        version: 1,
        review_status: p.review_status ?? "draft",
        created_at: new Date().toISOString(),
      })),
      references: (payload.references ?? []).map((r, i) => ({
        id: `demo-ref-${i}`,
        citation_text: r.citation_text,
        doi: r.doi ?? null,
        url: r.url ?? null,
        source_document: r.source_document ?? null,
        page_reference: r.page_reference ?? null,
        created_at: new Date().toISOString(),
      })),
    };
    demoStore.materials.push(material);
    return delay(material);
  },

  listProjects: () => delay(demoStore.projects),
  getProject: (_token, projectId) => {
    const project = demoStore.projects.find((p) => p.id === projectId);
    if (!project) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Projeto não encontrado (demo)." } }));
    return delay(project);
  },
  createProject: (_token, payload: ProjectCreateRequest) => {
    const project: ProjectResponse = {
      id: `demo-project-${demoStore.projects.length + 1}`,
      organization_id: "demo-org",
      owner_user_id: "demo-user",
      name: payload.name,
      description: payload.description ?? null,
      status: "active",
      created_at: new Date().toISOString(),
    };
    demoStore.projects.push(project);
    return delay(project);
  },

  validateRecipe: (recipeBody: GeometryRecipeBody) => delay(offlineValidateResponse(recipeBody)),
  listRecipes: (_token, projectId) => delay(demoStore.recipes.filter((r) => r.project_id === projectId)),
  getRecipe: (_token, recipeId) => {
    const recipe = demoStore.recipes.find((r) => r.id === recipeId);
    if (!recipe) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Receita não encontrada (demo)." } }));
    return delay(recipe);
  },
  createRecipe: (_token, projectId, name, recipeBody) => {
    const validation = offlineValidateResponse(recipeBody);
    const recipe: RecipeResponse = {
      id: `demo-recipe-${demoStore.recipes.length + 1}`,
      organization_id: "demo-org",
      project_id: projectId,
      name,
      schema_version: recipeBody.schema_version,
      canonical_json: recipeBody,
      checksum_sha256: validation.checksum_sha256 ?? "demo-fingerprint-unknown",
      version: 1,
      parent_recipe_id: null,
      status: "validated",
      created_at: new Date().toISOString(),
    };
    demoStore.recipes.push(recipe);
    return delay(recipe);
  },
  cloneRecipe: (_token, recipeId) => {
    const original = demoStore.recipes.find((r) => r.id === recipeId);
    if (!original) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Receita não encontrada (demo)." } }));
    const clone: RecipeResponse = {
      ...original,
      id: `demo-recipe-${demoStore.recipes.length + 1}`,
      version: original.version + 1,
      parent_recipe_id: original.id,
      created_at: new Date().toISOString(),
    };
    demoStore.recipes.push(clone);
    return delay(clone);
  },

  listDesignRunsForProject: (_token, projectId) => delay(demoStore.designRuns.filter((r) => r.project_id === projectId)),
  createDesignRun: (_token, payload) => {
    const existing = demoStore.designRuns.find((r) => r.idempotency_key === payload.idempotency_key);
    if (existing) return delay({ ...existing, created: false });

    const jobId = `demo-job-${demoStore.jobs.length + 1}`;
    const job: GeometryJobResponse = {
      id: jobId,
      design_run_id: `demo-run-${demoStore.designRuns.length + 1}`,
      attempt_number: 1,
      status: "queued",
      progress_pct: 0,
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: null,
      error_code: null,
      error_message: null,
      worker_version: null,
      dotnet_version: null,
      picogk_version: null,
      metrics: null,
      duration_seconds: null,
    };
    demoStore.jobs.push(job);

    const designRun: DesignRunResponse = {
      id: job.design_run_id,
      organization_id: "demo-org",
      project_id: payload.project_id,
      recipe_id: payload.recipe_id,
      material_id: payload.material_id ?? null,
      idempotency_key: payload.idempotency_key,
      created_at: new Date().toISOString(),
      created: true,
      latest_job: job,
    };
    demoStore.designRuns.push(designRun);
    const submittedRecipe = demoStore.recipes.find((r) => r.id === payload.recipe_id);
    simulateJobProgress(jobId, submittedRecipe?.canonical_json.topology.kind ?? "gyroid");
    return delay(designRun);
  },
  getDesignRun: (_token, designRunId) => {
    const run = demoStore.designRuns.find((r) => r.id === designRunId);
    if (!run) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Design run não encontrado (demo)." } }));
    const latestJob = demoStore.jobs.find((j) => j.id === run.latest_job.id) ?? run.latest_job;
    return delay({ ...run, latest_job: latestJob, created: false });
  },
  retryDesignRun: (_token, designRunId) => {
    const run = demoStore.designRuns.find((r) => r.id === designRunId);
    if (!run) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Design run não encontrado (demo)." } }));
    const jobId = `demo-job-${demoStore.jobs.length + 1}`;
    const newJob: GeometryJobResponse = {
      ...run.latest_job,
      id: jobId,
      attempt_number: run.latest_job.attempt_number + 1,
      status: "queued",
      progress_pct: 0,
      started_at: null,
      finished_at: null,
      error_code: null,
      error_message: null,
      metrics: null,
    };
    demoStore.jobs.push(newJob);
    run.latest_job = newJob;
    const retriedRecipe = demoStore.recipes.find((r) => r.id === run.recipe_id);
    simulateJobProgress(jobId, retriedRecipe?.canonical_json.topology.kind ?? "gyroid");
    return delay(newJob);
  },

  getJob: (_token, jobId) => {
    const job = demoStore.jobs.find((j) => j.id === jobId);
    if (!job) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Job não encontrado (demo)." } }));
    return delay(job);
  },
  cancelJob: (_token, jobId) => {
    const job = demoStore.jobs.find((j) => j.id === jobId);
    if (!job) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Job não encontrado (demo)." } }));
    if (job.status !== "queued" && job.status !== "running") {
      return Promise.reject(new ApiError(409, { error: { id: "demo", code: "HTTP_409", message: "Job já finalizado (demo)." } }));
    }
    job.status = "cancelled";
    job.finished_at = new Date().toISOString();
    return delay(job);
  },
  listJobArtifacts: (_token, jobId) => delay(demoStore.artifacts.filter((a) => a.geometry_job_id === jobId)),
  getJobManifest: (_token, jobId) => {
    const manifest = demoStore.manifests[jobId];
    if (!manifest) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Manifesto ainda não disponível (demo)." } }));
    return delay(manifest);
  },
  getJobMetrics: (_token, jobId) => {
    const job = demoStore.jobs.find((j) => j.id === jobId);
    if (!job?.metrics) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Métricas ainda não disponíveis (demo)." } }));
    return delay(job.metrics);
  },
  artifactDownloadUrl: (artifactId: string) => {
    const artifact = demoStore.artifacts.find((a) => a.id === artifactId);
    if (artifact?.kind === "stl") {
      return `${import.meta.env.BASE_URL}demo-assets/${SAMPLE_STL_FILENAME}`;
    }
    return `${import.meta.env.BASE_URL}demo-assets/${SAMPLE_STL_FILENAME}`;
  },

  // ---- Incremento 2.3 -- Dados científicos (simulado, sem backend real) ----
  listScientificEntities: () => delay(SAMPLE_SCI_ENTITIES.map(({ identifiers: _identifiers, description: _description, updated_at: _updated_at, ...rest }) => rest as ScientificEntitySummary)),
  getScientificEntity: (_token, entityId) => {
    const entity = SAMPLE_SCI_ENTITIES.find((e) => e.id === entityId);
    if (!entity) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Entidade científica não encontrada (demo)." } }));
    return delay(entity);
  },
  listPropertyDefinitions: () => delay(SAMPLE_PROPERTY_DEFINITIONS),
  listScientificSources: () =>
    delay([
      {
        id: "demo-sci-source-alpha",
        name: "Fonte Sintética Alfa de Demonstração",
        source_type: "database",
        base_url: null,
        publisher: "Fonte fictícia de demonstração -- não corresponde a nenhuma editora/banco real.",
        license: "Uso interno de demonstração apenas -- não redistribuir.",
        version: "demo-1",
        accessed_at: new Date().toISOString(),
        redistribution_status: "unknown",
      },
    ]),
  listEntityIdentifiers: (_token, entityId) => {
    const entity = SAMPLE_SCI_ENTITIES.find((e) => e.id === entityId);
    return delay(entity?.identifiers ?? []);
  },
  listEntityPropertyObservations: (_token, entityId) => delay(SAMPLE_PROPERTY_OBSERVATIONS[entityId] ?? []),
  listEntityProvenance: (_token, entityId) => delay(SAMPLE_PROVENANCE[entityId] ?? []),
  listEntitySupplierProducts: (): Promise<SupplierProductResponse[]> => delay([]),
  listEntityCrystalStructures: (): Promise<CrystalStructureReferenceResponse[]> => delay([]),
  listEntityReviewHistory: (): Promise<ReviewDecisionResponse[]> => delay([]),
  listEntityBiologicalEvidence: (_token, entityId) => delay(SAMPLE_BIOLOGICAL_EVIDENCE[entityId] ?? []),
  listEntityRawSourceRecords: (_token, entityId) => delay(SAMPLE_RAW_SOURCE_RECORDS[entityId] ?? []),
  listEntityConflicts: (_token, entityId) => delay(SAMPLE_CONFLICTS[entityId] ?? []),
  createReviewDecision: (_token, entityId, payload) => {
    const entity = SAMPLE_SCI_ENTITIES.find((e) => e.id === entityId);
    if (!entity) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Entidade científica não encontrada (demo)." } }));
    const newState: ReviewDecisionOutcome extends string ? string : never =
      payload.decision === "approved" ? "reviewed" : payload.decision === "rejected" ? "rejected" : entity.review_status;
    const decision: ReviewDecisionResponse = {
      id: `demo-sci-review-${Date.now()}`,
      subject_type: "ScientificEntity",
      subject_id: entityId,
      decision: payload.decision,
      reviewer_user_id: "demo-user",
      justification: payload.justification,
      previous_state: entity.review_status,
      new_state: newState,
      created_at: new Date().toISOString(),
    };
    entity.review_status = newState as ScientificEntityDetail["review_status"];
    return delay(decision);
  },

  // ---- Incremento 2.3 -- Ingestão científica / conector PubChem (simulado, GitHub Pages) ----
  listIngestionConnectors: () => delay(SAMPLE_CONNECTORS),
  listIngestionRequests: () => delay([...demoIngestionRequests]),
  getIngestionRequest: (_token, requestId) => {
    const req = demoIngestionRequests.find((r) => r.id === requestId);
    if (!req) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Solicitação de ingestão não encontrada (demo)." } }));
    return delay(req);
  },
  getIngestionRequestConflicts: (_token, requestId) => {
    const req = demoIngestionRequests.find((r) => r.id === requestId);
    if (!req) return delay([]);
    return delay(req.external_ids.includes(DEMO_CONFLICT_CID) ? [demoConflict] : []);
  },
  submitIngestionRequest: (_token, payload) => {
    demoIngestionRequestCounter += 1;
    const req: IngestionRequestResponse = {
      id: `demo-ingestion-${demoIngestionRequestCounter}`,
      organization_id: "demo-org",
      requested_by_user_id: "demo-user",
      connector_id: payload.connector_id,
      source_id: payload.source_id,
      external_ids: payload.external_ids,
      dry_run: Boolean(payload.dry_run),
      status: "queued",
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: null,
      claimed_by_dispatcher_id: "demo-dispatcher",
      heartbeat_at: null,
      attempt_number: 1,
      cancel_requested_at: null,
      summary: null,
      error: null,
      ingestion_run_id: null,
    };
    demoIngestionRequests.push(req);
    simulateIngestionProgress(req.id, payload.external_ids, Boolean(payload.dry_run));
    return delay(req);
  },
  submitIngestionDryRun: (_token, payload) => {
    demoIngestionRequestCounter += 1;
    const req: IngestionRequestResponse = {
      id: `demo-ingestion-${demoIngestionRequestCounter}`,
      organization_id: "demo-org",
      requested_by_user_id: "demo-user",
      connector_id: payload.connector_id,
      source_id: payload.source_id,
      external_ids: payload.external_ids,
      dry_run: true,
      status: "queued",
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: null,
      claimed_by_dispatcher_id: "demo-dispatcher",
      heartbeat_at: null,
      attempt_number: 1,
      cancel_requested_at: null,
      summary: null,
      error: null,
      ingestion_run_id: null,
    };
    demoIngestionRequests.push(req);
    simulateIngestionProgress(req.id, payload.external_ids, true);
    return delay(req);
  },
  cancelIngestionRequest: (_token, requestId) => {
    const req = demoIngestionRequests.find((r) => r.id === requestId);
    if (!req) return Promise.reject(new ApiError(404, { error: { id: "demo", code: "HTTP_404", message: "Solicitação de ingestão não encontrada (demo)." } }));
    if (req.status !== "queued" && req.status !== "running") {
      return Promise.reject(new ApiError(409, { error: { id: "demo", code: "HTTP_409", message: "Solicitação já finalizada (demo)." } }));
    }
    req.status = "cancelled";
    req.cancel_requested_at = new Date().toISOString();
    req.finished_at = new Date().toISOString();
    return delay(req);
  },
};
