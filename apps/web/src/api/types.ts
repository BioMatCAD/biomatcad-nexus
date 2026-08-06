// Tipos espelhando apps/api/src/biomatcad_api/schemas/*.py (Incremento 1).
// Mantidos manualmente por ora; packages/contracts (geração automática a partir do OpenAPI)
// é backlog — ver IMPLEMENTATION_STATUS.md.

export interface HealthResponse {
  status: string;
}

export interface ReadyResponse {
  status: string;
  database: string;
}

export interface VersionResponse {
  version: string;
  environment: string;
}

// Cinco estados (Incremento 1.1): Pesquisa e Laboratório são contextos independentes;
// clinical_test/clinical_pilot/clinical_production formam a "suíte clínica", sempre
// controlada em conjunto por uma única chave mestra no backend — nunca individualmente.
export type OperationalStateKind =
  | "research"
  | "laboratory"
  | "clinical_test"
  | "clinical_pilot"
  | "clinical_production";

export interface OperationalStateItem {
  kind: OperationalStateKind;
  enabled: boolean;
}

// Classificação explícita do modo de autenticação atual (Incremento 1.1). "DEV_AUTH" = e-mail/
// senha + JWT stateless; NÃO é OIDC/OAuth 2.1 + MFA + WebAuthn + step-up (ainda pendente).
export type AuthMode = "DEV_AUTH";

export interface SystemStatusResponse {
  environment: string;
  auth_mode: AuthMode;
  // True somente quando os TRÊS flags da suíte clínica estão habilitados simultaneamente.
  // Laboratório NUNCA entra neste cálculo.
  clinical_suite_enabled: boolean;
  operational_states: OperationalStateItem[];
  demo_mode: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: string;
  organization_id: string;
}

export interface ApiErrorPayload {
  error: {
    id: string;
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiError extends Error {
  code: string;
  errorId: string;
  status: number;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.error.code;
    this.errorId = payload.error.id;
  }
}

// ---------------------------------------------------------------------------------------
// Incremento 2.1 — materiais, projetos, receitas BioMatCEM, jobs geométricos, artefatos.
// ---------------------------------------------------------------------------------------

export type MaterialSourceType = "synthetic" | "literature";
export type ReviewStatus = "draft" | "reviewed" | "deprecated";

export interface MaterialPropertyResponse {
  id: string;
  property_name: string;
  value: number;
  unit: string;
  source: string;
  reference_id: string | null;
  method: string | null;
  uncertainty_low: number | null;
  uncertainty_high: number | null;
  version: number;
  review_status: ReviewStatus;
  created_at: string;
}

export interface ScientificReferenceResponse {
  id: string;
  citation_text: string;
  doi: string | null;
  url: string | null;
  source_document: string | null;
  page_reference: string | null;
  created_at: string;
}

export interface MaterialSummary {
  id: string;
  name: string;
  category: string;
  source_type: MaterialSourceType;
  review_status: ReviewStatus;
  created_at: string;
}

export interface MaterialDetail extends MaterialSummary {
  description: string | null;
  properties: MaterialPropertyResponse[];
  references: ScientificReferenceResponse[];
}

export interface MaterialCreateRequest {
  name: string;
  category: string;
  source_type: MaterialSourceType;
  description?: string | null;
  properties?: Array<{
    property_name: string;
    value: number;
    unit: string;
    source: string;
    reference_id?: string | null;
    method?: string | null;
    uncertainty_low?: number | null;
    uncertainty_high?: number | null;
    review_status?: ReviewStatus;
  }>;
  references?: Array<{
    citation_text: string;
    doi?: string | null;
    url?: string | null;
    source_document?: string | null;
    page_reference?: string | null;
  }>;
}

export type ProjectStatus = "active" | "archived";

export interface ProjectResponse {
  id: string;
  organization_id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  created_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string | null;
}

// Topologia gyroid (TPMS) -- espelha o ramo oneOf "gyroid" de
// schemas/biomatcem/geometry-recipe-v1.schema.json.
export interface GyroidTopologyBody {
  kind: "gyroid";
  cell_size_mm: number;
  // Incremento 2.1.1 (item 2): obrigatório -- único controlador de espessura.
  wall_thickness_mm: number;
  // Opcional (default 0.0 no schema) -- apenas desloca o centro da banda, NÃO controla espessura.
  isovalue?: number;
  target_porosity_pct?: number;
}

// Topologia Voronoi (Incremento 2.2, rodada Voronoi) -- espelha o ramo oneOf
// "voronoi_cell_edges_v1" do mesmo schema. Struts construídos sobre as ARESTAS REAIS das
// células de uma tesselação de Voronoi 3D (nunca um grafo de adjacência de sítios de
// Delaunay -- ver docs/architecture/voronoi-cell-edges-v1-math-audit.md).
export interface VoronoiTopologyBody {
  kind: "voronoi_cell_edges_v1";
  // Número de sítios (sementes), 4..500.
  site_count: number;
  distribution: "uniform_random" | "jittered_grid";
  // Opcional -- se omitido, o worker deriva um valor conservador a partir do domínio e de
  // site_count e registra o valor efetivamente usado em effective_parameters.
  seed_site_min_separation_mm?: number;
  strut_radius_mm: number;
  // Fator de suavização do blend implícito (smooth-min) nos nós, 0..1, default 0.5 no schema.
  node_smoothing?: number;
  // Raio efetivo do nó = strut_radius_mm * node_radius_factor, 1..3, default 1.3 no schema.
  node_radius_factor?: number;
  // Único valor suportado nesta rodada ("clip") -- mantido como enum para extensão futura.
  boundary_behavior?: "clip";
  target_porosity_pct?: number;
}

// Corpo de receita BioMatCEM -- espelha schemas/biomatcem/geometry-recipe-v1.schema.json.
export interface GeometryRecipeBody {
  schema_version: "1.0.0";
  domain:
    | { shape: "block"; dimensions_mm: { kind: "block"; x_mm: number; y_mm: number; z_mm: number } }
    | { shape: "cylinder"; dimensions_mm: { kind: "cylinder"; radius_mm: number; height_mm: number } };
  topology: GyroidTopologyBody | VoronoiTopologyBody;
  resolution?: { voxel_size_mm?: number };
  mode: "preview" | "final";
  seed: number;
  compute_limits: { max_duration_seconds: number; max_memory_mb: number; max_voxel_count: number };
  output_formats: Array<"stl" | "vdb">;
}

export interface RecipeValidationErrorItem {
  path: string;
  message: string;
  validator: string;
}

export interface RecipeValidateResponse {
  valid: boolean;
  errors: RecipeValidationErrorItem[];
  checksum_sha256: string | null;
  schema_version: string;
}

export type RecipeStatus = "draft" | "validated";

export interface RecipeResponse {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  schema_version: string;
  canonical_json: GeometryRecipeBody;
  checksum_sha256: string;
  version: number;
  parent_recipe_id: string | null;
  status: RecipeStatus;
  created_at: string;
}

export type JobStatusKind = "queued" | "running" | "succeeded" | "failed" | "cancelled";

// Nomes de campo devem bater EXATAMENTE com o JSON emitido pelo worker real
// (apps/geometry-worker/JobEnvelope.cs: porosity_pct_measured, vertex_count_unique) e
// repassado verbatim pela API (worker_client.py: metrics=result_json["metrics"], sem
// renomear nada). Um mismatch aqui (bug real encontrado e corrigido em 2026-07-29 ao preparar
// o gate final do worker PicoGK real) faz a UI mostrar "undefined" silenciosamente para um job
// succeeded de verdade -- nunca renomeie estes campos sem conferir o contrato real do worker.
export interface GeometryMetrics {
  bounding_box_mm: [[number, number, number], [number, number, number]];
  volume_mm3: number;
  porosity_pct_measured: number;
  surface_area_mm2: number;
  vertex_count_unique: number;
  triangle_count: number;
  is_watertight: boolean;

  // Campos EXTRA específicos de voronoi_cell_edges_v1 (Incremento 2.2, rodada Voronoi,
  // Seção 9) -- populados via metrics.Extra ([JsonExtensionData] em
  // apps/geometry-worker/JobEnvelope.cs, preenchidos por
  // VoronoiTopologyProvider.PopulateMetricsExtra) e repassados verbatim pela API
  // (dict[str, Any] em schemas/jobs.py -- nunca renomeados). Ausentes/undefined para jobs
  // Gyroid. Conectividade aqui é sempre TOPOLÓGICA (grafo de nós/arestas) -- nunca
  // conectividade biológica nem validação experimental.
  site_count?: number;
  delaunay_cell_count?: number;
  degenerate_cell_count?: number;
  node_count?: number;
  edge_count?: number;
  internal_edge_count?: number;
  boundary_ray_edge_count?: number;
  discarded_boundary_ray_count?: number;
  discarded_internal_edge_count?: number;
  connected_component_count?: number;
  isolated_node_count?: number;
  total_strut_length_mm?: number;
  mean_strut_length_mm?: number;
  min_strut_length_mm?: number;
  max_strut_length_mm?: number;
  strut_length_stddev_mm?: number;
  mean_node_degree?: number;
  min_node_degree?: number;
  max_node_degree?: number;
  node_degree_stddev?: number;
}

export interface GeometryJobResponse {
  id: string;
  design_run_id: string;
  attempt_number: number;
  status: JobStatusKind;
  progress_pct: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  worker_version: string | null;
  dotnet_version: string | null;
  picogk_version: string | null;
  metrics: GeometryMetrics | null;
  duration_seconds: number | null;
}

export interface DesignRunResponse {
  id: string;
  organization_id: string;
  project_id: string;
  recipe_id: string;
  material_id: string | null;
  idempotency_key: string;
  created_at: string;
  created: boolean;
  latest_job: GeometryJobResponse;
}

export interface ArtifactResponse {
  id: string;
  geometry_job_id: string;
  kind: "stl" | "vdb" | "thumbnail" | "manifest" | "log";
  sha256: string;
  size_bytes: number;
  created_at: string;
}

export interface ManifestResponse {
  id: string;
  geometry_job_id: string;
  manifest_json: Record<string, unknown>;
  manifest_sha256: string;
  created_at: string;
}


// ---- Observabilidade real (Incremento 2.2, Seção 7) ----
// Espelha apps/api/src/biomatcad_api/schemas/observability.py -- cada campo vem de uma
// verificação real feita pelo backend no momento da requisição, nunca um estado inventado.
export type ComponentState = "healthy" | "degraded" | "unavailable" | "stale" | "stopped" | "unknown";

export interface ComponentStatus {
  state: ComponentState;
  detail: string;
}

export interface ApiComponentStatus extends ComponentStatus {
  version: string;
  environment: string;
}

export interface DispatcherComponentStatus extends ComponentStatus {
  dispatcher_id: string | null;
  pid: number | null;
  phase: string | null;
  last_poll_at: string | null;
  jobs_processed_total: number | null;
  current_poll_interval_seconds: number | null;
}

export interface WorkerComponentStatus extends ComponentStatus {
  binary_found: boolean;
  worker_version: string | null;
  dotnet_version: string | null;
  picogk_version: string | null;
}

export interface QueueComponentStatus extends ComponentStatus {
  queued_count: number;
  processing_count: number;
}

export interface StorageComponentStatus extends ComponentStatus {
  path: string;
  writable: boolean;
}

export interface ActiveJobSummary {
  job_id: string;
  design_run_id: string;
  status: string;
  progress_pct: number;
  started_at: string | null;
  heartbeat_at: string | null;
  heartbeat_stale: boolean;
}

export interface FailedJobSummary {
  job_id: string;
  design_run_id: string;
  error_code: string | null;
  error_message: string | null;
  finished_at: string | null;
}

export interface VersionsInfo {
  api: string;
  schema_geometry_recipe: string;
}

export interface ObservabilityStatusResponse {
  generated_at: string;
  api: ApiComponentStatus;
  database: ComponentStatus;
  dispatcher: DispatcherComponentStatus;
  worker: WorkerComponentStatus;
  queue: QueueComponentStatus;
  storage: StorageComponentStatus;
  versions: VersionsInfo;
  jobs_active: ActiveJobSummary[];
  jobs_failed_recent: FailedJobSummary[];
}
