import { defineConfig, devices } from "@playwright/test";

// Incremento 2.1.1 (item 12): E2E real do caminho login -> materiais -> projeto -> receita ->
// design-run -> status do job -> visualizador/download -- ver e2e/README.md para o motivo pelo
// qual este teste não pôde ser EXECUTADO neste sandbox de desenvolvimento (bibliotecas nativas
// do Chromium ausentes, sem acesso root para instalá-las) e como rodá-lo de verdade.
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_WEB_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
