import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Guarda textual de regressão para os dois bugs reais encontrados em execução E2E real no
// Windows (2026-07-29, ver e2e/README.md "Falhas reais corrigidas"):
//
// 1) O teste usava page.goto() para navegar para rotas protegidas (/app/projects,
//    /app/jobs/:id) DEPOIS do login. AuthContext.tsx guarda o token só em memória (decisão de
//    segurança documentada, não um defeito) -- um page.goto() força um reload completo, que
//    reinicia o app e derruba a sessão, fazendo ProtectedRoute redirecionar para /login. Por
//    isso os dois testes ficavam presos na tela de login e nunca encontravam #project-name nem
//    o texto de status.
// 2) O segundo teste esperava o literal "succeeded" na página do job, mas a UI real só
//    renderiza o rótulo traduzido ("Concluído", ver STATUS_LABEL em JobDetailPage.tsx) -- a
//    string "succeeded" nunca aparece no DOM.
//
// Este teste fica em apps/web/tests/ (não em e2e/) de propósito -- vitest.config exclui
// "e2e/**" da coleta (specs do Playwright, runner incompatível).
describe("e2e/vertical.spec.ts -- guarda textual contra regressão das duas causas reais de falha", () => {
  const testFileDir = path.dirname(fileURLToPath(import.meta.url));
  const sourcePath = path.resolve(testFileDir, "../e2e/vertical.spec.ts");
  const source = fs.readFileSync(sourcePath, "utf-8");
  // Código executável apenas -- remove linhas de comentário puro (podem legitimamente citar o
  // padrão buggy antigo como exemplo documentado do que NÃO fazer, ver cabeçalho do arquivo).
  const executableSource = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");

  it("NÃO usa page.goto() para rotas protegidas (/app/...) -- só para /login, antes da autenticação", () => {
    const gotoAppMatches = executableSource.match(/page\.goto\(\s*["'`]\/app\b[^"'`]*["'`]\s*\)/g);
    expect(gotoAppMatches).toBeNull();
  });

  it("navega para rotas protegidas via clique em link/botão real da UI (client-side), não via reload", () => {
    expect(source).toMatch(/getByRole\(\s*["'`]link["'`]\s*,\s*\{\s*name:\s*["'`]Projetos BioMatCAD["'`]/);
    expect(source).toMatch(/getByRole\(\s*["'`]link["'`]\s*,\s*\{\s*name:\s*["'`]Ver job["'`]/);
  });

  it("NÃO afirma o literal 'succeeded' como texto exibido pela UI", () => {
    // getByText/toHaveText/toContainText contra o literal "succeeded" seria testar uma string
    // que a interface real nunca renderiza (ela só mostra o rótulo traduzido, ex. "Concluído").
    // Menções a "succeeded" em comentários (documentando o próprio bug corrigido) são
    // aceitáveis -- só a USO como argumento de asserção é que não pode voltar.
    expect(source).not.toMatch(/getByText\(\s*["'`]succeeded["'`]/);
    expect(source).not.toMatch(/toHaveText\(\s*["'`]succeeded["'`]/);
    expect(source).not.toMatch(/toContainText\(\s*["'`]succeeded["'`]/);
  });

  it("verifica o status real via data-testid documentado, aceitando o rótulo localizado", () => {
    expect(source).toContain('getByTestId("job-status")');
    expect(source).toMatch(/Conclu.*[íi]do/);
  });
});
