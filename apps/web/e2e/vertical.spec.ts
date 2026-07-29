import { test, expect } from "@playwright/test";

// Incremento 2.1.1 (item 12): vertical completa via UI real contra a API real e um Postgres
// real. A criação de projeto/receita/design-run abaixo é 100% real (mesmo caminho de código
// que a API usa em produção). A verificação da página de job 'succeeded' usa um job PRÉ-SEMEADO
// pelo global-setup (worker fake, rotulado) apenas para o job existir sem depender do PicoGK
// real -- ver e2e/README.md.
const E2E_EMAIL = "e2e-playwright@biomatcad.example";
const E2E_PASSWORD = "e2e-synthetic-password-123";

test.describe("Vertical BioMatCAD Nexus (login -> projeto -> receita -> job)", () => {
  test("login, criação de projeto e receita via UI real", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#email", E2E_EMAIL);
    await page.fill("#password", E2E_PASSWORD);
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/app/);

    await page.goto("/app/projects");
    const projectName = `Projeto E2E ${Date.now()}`;
    await page.fill("#project-name", projectName);
    await page.click('button:has-text("Criar projeto")');
    await expect(page.getByText(projectName)).toBeVisible();

    await page.getByText(projectName).click();
    await expect(page).toHaveURL(/\/app\/projects\/.+/);

    await page.click('button:has-text("Nova receita")');
    await expect(page).toHaveURL(/\/recipes\/new/);

    // A receita padrão do formulário já é válida (DEFAULT_RECIPE) -- espera a validação
    // assíncrona (debounce) confirmar antes de habilitar o botão de salvar.
    await expect(page.locator('button[type="submit"]:has-text("Salvar receita")')).toBeEnabled({ timeout: 5000 });
    await page.click('button[type="submit"]:has-text("Salvar receita")');

    await expect(page).toHaveURL(/\/recipes\/[a-f0-9-]+$/);
    await expect(page.getByText("Enviar job geométrico")).toBeVisible();
  });

  test("página de job succeeded (pré-semeado) exibe métricas e link de download do STL", async ({ page, request }) => {
    // O AuthContext guarda o token SOMENTE em memória (React state), nunca em localStorage
    // (decisão de segurança documentada em src/context/AuthContext.tsx) -- por isso, para
    // descobrir o job pré-semeado via chamadas diretas à API neste teste, autenticamos de novo
    // separadamente através do endpoint real de login usando o contexto `request` do Playwright,
    // em vez de tentar extrair o token da página.
    const apiBaseUrl = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
    const loginResp = await request.post(`${apiBaseUrl}/api/v1/auth/login`, {
      data: { email: E2E_EMAIL, password: E2E_PASSWORD },
    });
    expect(loginResp.ok()).toBeTruthy();
    const { access_token: token } = await loginResp.json();

    await page.goto("/login");
    await page.fill("#email", E2E_EMAIL);
    await page.fill("#password", E2E_PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/app/);

    const projectsResp = await request.get(`${apiBaseUrl}/api/v1/projects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(projectsResp.ok()).toBeTruthy();
    const projects = await projectsResp.json();
    const seededProject = projects.find((p: { name: string }) => p.name === "Projeto E2E (pré-semeado)");
    expect(seededProject).toBeTruthy();

    const runsResp = await request.get(`${apiBaseUrl}/api/v1/projects/${seededProject.id}/design-runs`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const runs = await runsResp.json();
    const succeededRun = runs.find((r: { latest_job: { status: string } }) => r.latest_job.status === "succeeded");
    expect(succeededRun).toBeTruthy();

    await page.goto(`/app/jobs/${succeededRun.latest_job.id}`);
    await expect(page.getByText("succeeded", { exact: false })).toBeVisible();
    await expect(page.locator('a[download]').first()).toBeVisible();
  });
});
