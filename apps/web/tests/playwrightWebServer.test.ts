import { describe, expect, it } from "vitest";

// Rodada Windows 20260806-195638 (itens 1-6 do usuário): a validação real reportou
// `net::ERR_CONNECTION_REFUSED` em http://localhost:5173/login porque
// `Run-VoronoiWindowsValidation.ps1` nunca iniciava o frontend antes de chamar
// `npm run test:e2e` -- o Playwright começava a testar contra um servidor que não existia.
//
// A correção usa a opção nativa `webServer` do Playwright (ver playwright.config.ts) em vez de
// reimplementar manualmente start/wait/log/kill em PowerShell -- delegando a uma implementação
// madura e já testada upstream pelo próprio Playwright. Este teste NÃO reimplementa o polling
// HTTP do Playwright (isso pertence ao `@playwright/test` e é testado no próprio projeto
// upstream) -- ele prova que a NOSSA configuração efetivamente ativa essa garantia: comando
// rastreado, URL de health-check antes de qualquer teste rodar, tempo de espera explícito, e
// comportamento correto de reaproveitamento (nunca em CI/validação).
describe("playwright.config.ts -- webServer garante que a suíte não comeca antes do frontend estar saudável", () => {
  it("configura webServer com comando, URL de health-check e timeout explícitos", async () => {
    const { default: config } = await import("../playwright.config");
    const webServer = config.webServer as
      | { command?: string; url?: string; timeout?: number; stdout?: string; stderr?: string }
      | { command?: string; url?: string; timeout?: number; stdout?: string; stderr?: string }[]
      | undefined;

    expect(webServer).toBeDefined();
    const entry = Array.isArray(webServer) ? webServer[0] : webServer;
    expect(entry).toBeDefined();
    // `command`: como o processo do frontend é iniciado -- sempre rastreado pelo Playwright,
    // nunca um processo "solto" gerenciado manualmente por um roteiro externo.
    expect(entry?.command).toBe("npm run dev");
    // `url`: o Playwright faz polling HTTP nesta URL ANTES de rodar qualquer teste -- elimina a
    // corrida "Playwright começou antes do frontend subir" que causou o ERR_CONNECTION_REFUSED
    // real na rodada 20260806-195638.
    expect(typeof entry?.url).toBe("string");
    expect(entry?.url).toMatch(/^https?:\/\//);
    // `timeout`: espera explícita e finita (nunca indefinida) para o frontend ficar pronto.
    expect(entry?.timeout).toBeGreaterThan(0);
    // stdout/stderr capturados (nunca descartados) -- preservados no log de E2E do roteiro
    // PowerShell, que já redireciona todo o stdout/stderr do processo do Playwright.
    expect(entry?.stdout).toBe("pipe");
    expect(entry?.stderr).toBe("pipe");
  });

  it("nunca reaproveita silenciosamente um servidor pré-existente durante CI/validação (CI=true)", async () => {
    const { shouldReuseExistingServer } = await import("../playwright.config");

    // Em execução local de desenvolvimento (sem CI definido), reaproveita um 'npm run dev' que
    // o desenvolvedor já tenha deixado rodando -- produtividade, comportamento padrão do
    // Playwright.
    expect(shouldReuseExistingServer({})).toBe(true);

    // Em CI/validação (Run-VoronoiWindowsValidation.ps1 e Run-E2EOnly.ps1 definem CI=true
    // apenas ao redor da chamada de `npm run test:e2e`), o Playwright deve SEMPRE iniciar um
    // processo novo e rastreado -- nunca reaproveitar silenciosamente algo já ouvindo na porta
    // 5173, que poderia ser um servidor desatualizado ou de uma sessão anterior (rodada
    // 20260806-195638: o roteiro nunca iniciava o frontend, então este comportamento nunca
    // havia sido exercido de verdade).
    expect(shouldReuseExistingServer({ CI: "true" })).toBe(false);
  });
});
