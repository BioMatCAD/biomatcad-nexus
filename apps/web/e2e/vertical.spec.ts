import { test, expect, type Page } from "@playwright/test";

// Incremento 2.1.1 (item 12): vertical completa via UI real contra a API real e um Postgres
// real. A criação de projeto/receita/design-run abaixo é 100% real (mesmo caminho de código
// que a API usa em produção). A verificação da página de job 'succeeded' usa um job PRÉ-SEMEADO
// pelo global-setup (worker fake, rotulado) apenas para o job existir sem depender do PicoGK
// real -- ver e2e/README.md.
//
// Regra de navegação (bug real corrigido em 2026-07-29, ver e2e/README.md "Falhas reais
// corrigidas"): NUNCA usar page.goto() para uma rota protegida (/app/**) depois do login.
// AuthContext.tsx guarda o token de sessão SOMENTE em memória (decisão de segurança
// documentada, não um defeito) -- um page.goto() força um reload completo do navegador, que
// reinicia o app do zero, apaga o token em memória e faz ProtectedRoute redirecionar para
// /login. A navegação real, pós-login, precisa sempre ser feita clicando em links/botões reais
// da UI (navegação client-side do React Router), exatamente como um usuário faria.
const E2E_EMAIL = "e2e-playwright@biomatcad.example";
const E2E_PASSWORD = "e2e-synthetic-password-123";

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test.describe("Vertical BioMatCAD Nexus (login -> projeto -> receita -> job)", () => {
  test("login, criação de projeto e receita via UI real", async ({ page }) => {
    await login(page);

    // Navegação real via UI (link do Sidebar, ver components/layout/Sidebar.tsx) -- não
    // page.goto("/app/projects").
    await page.getByRole("link", { name: "Projetos BioMatCAD" }).click();
    await expect(page).toHaveURL(/\/app\/projects$/);

    const projectName = `Projeto E2E ${Date.now()}`;
    await page.getByLabel("Nome do projeto").fill(projectName);
    await page.getByRole("button", { name: "Criar projeto" }).click();

    const projectLink = page.getByRole("link", { name: projectName });
    await expect(projectLink).toBeVisible();
    await projectLink.click();
    await expect(page).toHaveURL(/\/app\/projects\/.+/);

    await page.getByRole("button", { name: "Nova receita" }).click();
    await expect(page).toHaveURL(/\/recipes\/new/);

    // A receita padrão do formulário já é válida (DEFAULT_RECIPE) -- espera a validação
    // assíncrona (debounce) confirmar antes de habilitar o botão de salvar.
    const saveButton = page.getByRole("button", { name: "Salvar receita" });
    await expect(saveButton).toBeEnabled({ timeout: 5000 });
    await saveButton.click();

    await expect(page).toHaveURL(/\/recipes\/[a-f0-9-]+$/);
    await expect(page.getByRole("button", { name: "Enviar job geométrico" })).toBeVisible();
  });

  test("página de job succeeded (pré-semeado) exibe status, métricas e link de download do STL", async ({
    page,
  }) => {
    await login(page);

    // Percurso 100% real via UI (nenhuma chamada direta à API neste teste): Sidebar ->
    // projeto pré-semeado -> linha da execução na tabela "Histórico de execuções" -> job. O
    // projeto/receita/job pré-semeados são criados uma única vez pelo global-setup
    // (scripts/seed_e2e_user.py, idempotente) e nunca duplicados entre execuções da suíte.
    await page.getByRole("link", { name: "Projetos BioMatCAD" }).click();
    await expect(page).toHaveURL(/\/app\/projects$/);

    await page.getByRole("link", { name: "Projeto E2E (pré-semeado)" }).click();
    await expect(page).toHaveURL(/\/app\/projects\/.+/);

    await page.getByRole("link", { name: "Ver job" }).click();
    await expect(page).toHaveURL(/\/app\/jobs\/.+/);

    // A UI real localiza o status em português ("Concluído", ver STATUS_LABEL em
    // JobDetailPage.tsx) -- nunca o valor bruto da API ("succeeded"). Testar contra o literal
    // "succeeded" testaria uma string que a interface nunca renderiza; esse era o bug real do
    // teste (não da interface). Seletor por data-testid documentado (ver comentário em
    // JobDetailPage.tsx), estável independente do texto exato/idioma.
    await expect(page.getByTestId("job-status")).toHaveText(/Conclu[íi]do/i);

    // Métricas geométricas realmente renderizadas -- valores vêm do seed determinístico
    // (scripts/seed_e2e_user.py: volume_mm3=400.0, is_watertight=true).
    const metrics = page.getByTestId("job-metrics");
    await expect(metrics).toBeVisible();
    await expect(metrics).toContainText("400");
    await expect(metrics).toContainText("sim");

    await expect(page.getByTestId("stl-download-link")).toBeVisible();
  });
});
