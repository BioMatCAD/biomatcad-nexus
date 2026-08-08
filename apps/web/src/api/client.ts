import {
  ApiError,
  type ApiErrorPayload,
  type ArtifactResponse,
  type BiologicalEvidenceResponse,
  type ConnectorInfoResponse,
  type CrystalStructureReferenceResponse,
  type DesignRunResponse,
  type GeometryJobResponse,
  type GeometryMetrics,
  type GeometryRecipeBody,
  type HealthResponse,
  type IngestionConflictResponse,
  type IngestionRequestCreate,
  type IngestionRequestResponse,
  type LoginRequest,
  type LoginResponse,
  type ManifestResponse,
  type MaterialCreateRequest,
  type MaterialDetail,
  type MaterialSummary,
  type ObservabilityStatusResponse,
  type ProjectCreateRequest,
  type ProjectResponse,
  type PropertyDefinitionResponse,
  type PropertyObservationResponse,
  type ProvenanceEntry,
  type RawSourceRecordResponse,
  type ReadyResponse,
  type RecipeResponse,
  type RecipeValidateResponse,
  type ReviewDecisionOutcome,
  type ReviewDecisionResponse,
  type ScientificEntityDetail,
  type ScientificEntitySummary,
  type ScientificIdentifierResponse,
  type ScientificSourceResponse,
  type SupplierProductResponse,
  type SystemStatusResponse,
  type UserResponse,
  type VersionResponse,
} from "./types";

// Base URL configurável por ambiente (nunca hardcoded para produção — Prompt Mestre §3.3/§25).
// No modo demo (GitHub Pages) não há backend real: ver DemoApiClient nesta mesma pasta.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    let payload: ApiErrorPayload;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = { error: { id: "unknown", code: "UNKNOWN", message: response.statusText } };
    }
    throw new ApiError(response.status, payload);
  }

  return (await response.json()) as T;
}

export const apiClient = {
  health: () => request<HealthResponse>("/health"),
  ready: () => request<ReadyResponse>("/ready"),
  version: () => request<VersionResponse>("/version"),
  systemStatus: () => request<SystemStatusResponse>("/api/v1/system/status"),
  observabilityStatus: (token: string) =>
    request<ObservabilityStatusResponse>("/api/v1/observability/status", {}, token),
  login: (payload: LoginRequest) =>
    request<LoginResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  me: (token: string) => request<UserResponse>("/api/v1/auth/me", {}, token),

  // ---- Incremento 2.1 ----
  listMaterials: (token: string) => request<MaterialSummary[]>("/api/v1/materials", {}, token),
  getMaterial: (token: string, materialId: string) =>
    request<MaterialDetail>(`/api/v1/materials/${materialId}`, {}, token),
  createMaterial: (token: string, payload: MaterialCreateRequest) =>
    request<MaterialDetail>("/api/v1/materials", { method: "POST", body: JSON.stringify(payload) }, token),

  listProjects: (token: string) => request<ProjectResponse[]>("/api/v1/projects", {}, token),
  getProject: (token: string, projectId: string) =>
    request<ProjectResponse>(`/api/v1/projects/${projectId}`, {}, token),
  createProject: (token: string, payload: ProjectCreateRequest) =>
    request<ProjectResponse>("/api/v1/projects", { method: "POST", body: JSON.stringify(payload) }, token),

  validateRecipe: (recipeBody: GeometryRecipeBody) =>
    request<RecipeValidateResponse>("/api/v1/recipes/validate", {
      method: "POST",
      body: JSON.stringify({ recipe_body: recipeBody }),
    }),
  listRecipes: (token: string, projectId: string) =>
    request<RecipeResponse[]>(`/api/v1/projects/${projectId}/recipes`, {}, token),
  getRecipe: (token: string, recipeId: string) => request<RecipeResponse>(`/api/v1/recipes/${recipeId}`, {}, token),
  createRecipe: (token: string, projectId: string, name: string, recipeBody: GeometryRecipeBody) =>
    request<RecipeResponse>(
      `/api/v1/projects/${projectId}/recipes`,
      { method: "POST", body: JSON.stringify({ name, recipe_body: recipeBody }) },
      token,
    ),
  cloneRecipe: (token: string, recipeId: string) =>
    request<RecipeResponse>(`/api/v1/recipes/${recipeId}/clone`, { method: "POST" }, token),

  listDesignRunsForProject: (token: string, projectId: string) =>
    request<DesignRunResponse[]>(`/api/v1/projects/${projectId}/design-runs`, {}, token),
  createDesignRun: (
    token: string,
    payload: { project_id: string; recipe_id: string; material_id?: string | null; idempotency_key: string },
  ) => request<DesignRunResponse>("/api/v1/design-runs", { method: "POST", body: JSON.stringify(payload) }, token),
  getDesignRun: (token: string, designRunId: string) =>
    request<DesignRunResponse>(`/api/v1/design-runs/${designRunId}`, {}, token),
  retryDesignRun: (token: string, designRunId: string) =>
    request<GeometryJobResponse>(`/api/v1/design-runs/${designRunId}/retry`, { method: "POST" }, token),

  getJob: (token: string, jobId: string) => request<GeometryJobResponse>(`/api/v1/jobs/${jobId}`, {}, token),
  cancelJob: (token: string, jobId: string) =>
    request<GeometryJobResponse>(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" }, token),
  listJobArtifacts: (token: string, jobId: string) =>
    request<ArtifactResponse[]>(`/api/v1/jobs/${jobId}/artifacts`, {}, token),
  getJobManifest: (token: string, jobId: string) =>
    request<ManifestResponse>(`/api/v1/jobs/${jobId}/manifest`, {}, token),
  getJobMetrics: (token: string, jobId: string) =>
    request<GeometryMetrics>(`/api/v1/jobs/${jobId}/metrics`, {}, token),
  artifactDownloadUrl: (artifactId: string) => `${API_BASE_URL}/api/v1/artifacts/${artifactId}/download`,

  // ---- Incremento 2.3 -- Dados científicos (Rodada 1) ----
  listScientificEntities: (token: string) =>
    request<ScientificEntitySummary[]>("/api/v1/scientific-entities", {}, token),
  getScientificEntity: (token: string, entityId: string) =>
    request<ScientificEntityDetail>(`/api/v1/scientific-entities/${entityId}`, {}, token),
  listPropertyDefinitions: (token: string) =>
    request<PropertyDefinitionResponse[]>("/api/v1/scientific-entities/property-definitions", {}, token),
  listScientificSources: (token: string) =>
    request<ScientificSourceResponse[]>("/api/v1/scientific-entities/sources", {}, token),
  listEntityIdentifiers: (token: string, entityId: string) =>
    request<ScientificIdentifierResponse[]>(`/api/v1/scientific-entities/${entityId}/identifiers`, {}, token),
  listEntityPropertyObservations: (token: string, entityId: string) =>
    request<PropertyObservationResponse[]>(
      `/api/v1/scientific-entities/${entityId}/property-observations`,
      {},
      token,
    ),
  listEntityProvenance: (token: string, entityId: string) =>
    request<ProvenanceEntry[]>(`/api/v1/scientific-entities/${entityId}/provenance`, {}, token),
  listEntitySupplierProducts: (token: string, entityId: string) =>
    request<SupplierProductResponse[]>(`/api/v1/scientific-entities/${entityId}/supplier-products`, {}, token),
  listEntityCrystalStructures: (token: string, entityId: string) =>
    request<CrystalStructureReferenceResponse[]>(
      `/api/v1/scientific-entities/${entityId}/crystal-structures`,
      {},
      token,
    ),
  listEntityReviewHistory: (token: string, entityId: string) =>
    request<ReviewDecisionResponse[]>(`/api/v1/scientific-entities/${entityId}/review-history`, {}, token),
  listEntityBiologicalEvidence: (token: string, entityId: string) =>
    request<BiologicalEvidenceResponse[]>(`/api/v1/scientific-entities/${entityId}/biological-evidence`, {}, token),
  listEntityRawSourceRecords: (token: string, entityId: string) =>
    request<RawSourceRecordResponse[]>(`/api/v1/scientific-entities/${entityId}/raw-source-records`, {}, token),
  listEntityConflicts: (token: string, entityId: string) =>
    request<IngestionConflictResponse[]>(`/api/v1/scientific-entities/${entityId}/conflicts`, {}, token),
  createReviewDecision: (
    token: string,
    entityId: string,
    payload: { decision: ReviewDecisionOutcome; justification: string },
  ) =>
    request<ReviewDecisionResponse>(
      `/api/v1/scientific-entities/${entityId}/review-decisions`,
      { method: "POST", body: JSON.stringify(payload) },
      token,
    ),

  // ---- Incremento 2.3 -- Ingestão científica / conector PubChem (Rodada 2) ----
  listIngestionConnectors: (token: string) =>
    request<ConnectorInfoResponse[]>("/api/v1/scientific-ingestion/connectors", {}, token),
  listIngestionRequests: (token: string) =>
    request<IngestionRequestResponse[]>("/api/v1/scientific-ingestion/requests", {}, token),
  getIngestionRequest: (token: string, requestId: string) =>
    request<IngestionRequestResponse>(`/api/v1/scientific-ingestion/requests/${requestId}`, {}, token),
  getIngestionRequestConflicts: (token: string, requestId: string) =>
    request<IngestionConflictResponse[]>(
      `/api/v1/scientific-ingestion/requests/${requestId}/conflicts`,
      {},
      token,
    ),
  submitIngestionRequest: (token: string, payload: IngestionRequestCreate) =>
    request<IngestionRequestResponse>(
      "/api/v1/scientific-ingestion/requests",
      { method: "POST", body: JSON.stringify(payload) },
      token,
    ),
  submitIngestionDryRun: (token: string, payload: IngestionRequestCreate) =>
    request<IngestionRequestResponse>(
      "/api/v1/scientific-ingestion/requests/dry-run",
      { method: "POST", body: JSON.stringify({ ...payload, dry_run: true }) },
      token,
    ),
  cancelIngestionRequest: (token: string, requestId: string) =>
    request<IngestionRequestResponse>(
      `/api/v1/scientific-ingestion/requests/${requestId}/cancel`,
      { method: "POST" },
      token,
    ),
};

export type ApiClient = typeof apiClient;
