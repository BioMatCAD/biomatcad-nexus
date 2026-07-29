import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";

// Modo "demo": build estático para GitHub Pages, sob /<nome-do-repositorio>/ (Prompt Mestre §7.1).
// Ajuste BASE_PATH via variável de ambiente no workflow de deploy quando o nome do repo for
// definido; "/" é o padrão seguro para desenvolvimento local.
const isDemoBuild = process.env.VITE_MODE === "demo" || process.env.npm_lifecycle_event === "build:pages";

export default defineConfig({
  plugins: [react()],
  base: isDemoBuild ? (process.env.BASE_PATH ?? "/biomatcad-nexus/") : "/",
  define: {
    __BIOMATCAD_DEMO_MODE__: JSON.stringify(isDemoBuild),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    css: true,
    // Incremento 2.1.1 (item 12): e2e/ contém specs do Playwright (test.describe do
    // @playwright/test, não do vitest) -- exclui explicitamente para o vitest não tentar
    // coletá-los (vitest e playwright têm runners de teste incompatíveis apesar da sintaxe
    // parecida).
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
