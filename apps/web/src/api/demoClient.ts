import type { ApiClient } from "./client";
import { ApiError } from "./types";

// Cliente de demonstração usado exclusivamente no build do GitHub Pages (Prompt Mestre §3.3,
// §7.1): não existe backend real no Pages. Todos os dados são sintéticos e claramente
// rotulados. Login "funciona" apenas contra um usuário sintético fixo, sem emitir JWT válido
// de verdade — é uma simulação, nunca deve ser confundida com autenticação real.
const SYNTHETIC_DELAY_MS = 350;

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), SYNTHETIC_DELAY_MS));
}

export const demoApiClient: ApiClient = {
  health: () => delay({ status: "ok" }),
  ready: () => delay({ status: "ok", database: "demo-synthetic" }),
  version: () => delay({ version: "0.1.0-demo", environment: "github-pages-demo" }),
  systemStatus: () =>
    delay({
      environment: "github-pages-demo",
      clinical_suite_enabled: false,
      demo_mode: true,
      operational_states: [
        { kind: "research", enabled: true },
        { kind: "laboratory", enabled: false },
        { kind: "clinical_pilot", enabled: false },
        { kind: "clinical_production", enabled: false },
      ],
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
};
