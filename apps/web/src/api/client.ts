import {
  ApiError,
  type ApiErrorPayload,
  type HealthResponse,
  type LoginRequest,
  type LoginResponse,
  type ReadyResponse,
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
};

export type ApiClient = typeof apiClient;
