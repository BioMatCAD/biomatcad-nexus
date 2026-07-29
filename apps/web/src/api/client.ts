import {
  ApiError,
  type ApiErrorPayload,
  type ArtifactResponse,
  type DesignRunResponse,
  type GeometryJobResponse,
  type GeometryMetrics,
  type GeometryRecipeBody,
  type HealthResponse,
  type LoginRequest,
  type LoginResponse,
  type ManifestResponse,
  type MaterialCreateRequest,
  type MaterialDetail,
  type MaterialSummary,
  type ProjectCreateRequest,
  type ProjectResponse,
  type ReadyResponse,
  type RecipeResponse,
  type RecipeValidateResponse,
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
};

export type ApiClient = typeof apiClient;
