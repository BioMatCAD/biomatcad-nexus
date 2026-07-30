import type { ApiClient } from "./client";
import { offlineValidateResponse } from "./recipeValidationOffline";
import {
  ApiError,
  type ArtifactResponse,
  type DesignRunResponse,
  type GeometryJobResponse,
  type GeometryRecipeBody,
  type ManifestResponse,
  type MaterialCreateRequest,
  type MaterialDetail,
  type MaterialSummary,
  type ProjectCreateRequest,
  type ProjectResponse,
  type RecipeResponse,
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
 * Simula queued -> running -> succeeded via setTimeout, populando métricas fixas e apontando
 * o artefato STL para um arquivo sintético pré-calculado versionado em
 * public/demo-assets/ -- NUNCA saída real do worker PicoGK (bloqueado neste sandbox, ver
 * apps/geometry-worker/WORKER_STATUS.md). Usado exclusivamente pelo modo demo (GitHub Pages).
 */
function simulateJobProgress(jobId: string): void {
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
    simulateJobProgress(jobId);
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
    simulateJobProgress(jobId);
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
};
