import { defineConfig, devices } from "@playwright/test";

// Incremento 2.1.1 (item 12): E2E real do caminho login -> materiais -> projeto -> receita ->
// design-run -> status do job -> visualizador/download -- ver e2e/README.md para o motivo pelo
// qual este teste não pôde ser EXECUTADO neste sandbox de desenvolvimento (bibliotecas nativas
// do Chromium ausentes, sem acesso root para instalá-las) e como rodá-lo de verdade.
//
// `webServer` (rodada Windows 20260806-195638, item 1-6 do usuário): a validação real no
// Windows reportou `net::ERR_CONNECTION_REFUSED` em http://localhost:5173/login porque
// `Run-VoronoiWindowsValidation.ps1` nunca iniciava o frontend antes de chamar
// `npm run test:e2e` -- o comentário antigo do roteiro dizia literalmente "frontend precisa
// estar rodando via 'npm run dev' em outro terminal", ou seja, dependia de um passo manual que
// não tinha sido feito nessa execução. Em vez de reimplementar manualmente (no PowerShell) a
// inicialização rastreada + espera de porta + captura de log + encerramento apenas do processo
// iniciado -- que é exatamente o que o próprio Playwright já faz de forma madura e testada
// nativamente via a opção `webServer` --, delegamos isso ao Playwright:
//   - `command`: como o processo é iniciado (rastreado pelo próprio Playwright, nunca um
//     processo "solto"/não rastreado).
//   - `url`: Playwright faz polling HTTP nesta URL até responder (ou até `timeout`) ANTES de
//     rodar qualquer teste -- elimina a corrida "Playwright começou antes do frontend subir".
//   - `reuseExistingServer: !process.env.CI`: em execução local de desenvolvimento, reaproveita
//     um `npm run dev` que o desenvolvedor já tenha deixado rodando (produtividade); em CI/
//     validação (`CI=true`, definido explicitamente por
//     Run-VoronoiWindowsValidation.ps1/Run-E2EOnly.ps1 só ao redor da chamada de
//     `npm run test:e2e`), SEMPRE inicia um processo novo e rejeita reaproveitar silenciosamente
//     qualquer coisa já ouvindo na porta -- a mesma filosofia de "nunca reutilizar
//     silenciosamente um binário/processo desatualizado ou não rastreado" já aplicada ao build
//     do worker C# em `Run-VoronoiDirectWorkerProbe.ps1`.
//   - `stdout`/`stderr: "pipe"`: a saída do processo do frontend é encaminhada para o stdout/
//     stderr do próprio processo do Playwright -- que os roteiros PowerShell já capturam
//     integralmente via `Tee-Object -FilePath (Join-Path $OutputDir "e2e-output.log")` na etapa
//     de E2E, preservando o log completo sem infraestrutura adicional.
//   - `timeout`: 60s é folgado para o `vite` subir (tipicamente < 2s), com margem para hardware
//     mais lento.
//   - Encerramento: o próprio Playwright mata SOMENTE o processo que ele iniciou ao final da
//     execução (comportamento nativo, testado upstream) -- nunca um `taskkill` global.
// Extraído como função pura testável (mesmo padrão de `resolvePythonBin` em
// e2e/global-setup.ts): recebe `env` explicitamente em vez de ler `process.env` diretamente,
// permitindo que o teste em tests/playwrightWebServer.test.ts prove o comportamento sem
// depender de truques de invalidação de cache de módulo ESM.
export function shouldReuseExistingServer(env: NodeJS.ProcessEnv = process.env): boolean {
  return !env.CI;
}

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
  webServer: {
    command: "npm run dev",
    url: process.env.E2E_WEB_BASE_URL ?? "http://localhost:5173",
    reuseExistingServer: shouldReuseExistingServer(),
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
