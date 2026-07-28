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
