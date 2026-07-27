/// <reference types="vitest/config" />
import { defineConfig } from "vite";
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
  },
});
