import fs from "node:fs";
import path from "node:path";
import { test, expect, type Page } from "@playwright/test";

// Cobertura E2E real (navegador Chromium via Playwright) dos controles do visualizador 3D
// (StlViewer.tsx) contra o job pré-semeado (ver e2e/global-setup.ts / scripts/seed_e2e_user.py).
//
// Escopo desta rodada (pedido do usuário, "fechar exclusivamente a cobertura E2E real do
// visualizador 3D"): carregamento do STL, wireframe, transparência, eixos, grade, bounding box,
// clipping, screenshot, fullscreen, cancelamento e descarte de recursos. NÃO altera geometria,
// receitas, TopologyProviders nem contratos científicos -- só exercita controles de UI
// já implementados em StlViewer.tsx (ver auditoria completa em docs/architecture/viewer-3d-audit.md
// e no comentário de e2e/README.md que documentava esta lacuna).
//
// Pré-requisito corrigido nesta MESMA rodada (ver apps/api/scripts/seed_e2e_user.py e
// apps/api/tests/test_e2e_seed_fixture.py): o job pré-semeado antes gravava um STL ASCII vazio
// (zero facets) com um stl_sha256 fake ("0"*64) -- o StlViewer NUNCA chegava ao estado "ready"
// para esse job (ArtifactChecksumMismatchError, e mesmo sem isso, "nenhum facet encontrado").
// Isso nunca foi percebido porque vertical.spec.ts só verifica o botão de download, nunca o
// estado do visualizador. Corrigido para um tetraedro sintético válido (4 facets) com o SHA-256
// real dos bytes -- este spec é a primeira cobertura E2E que de fato depende do visualizador
// chegar a "ready".
//
// Regra de navegação (mesma de vertical.spec.ts): NUNCA page.goto() para rota protegida
// (/app/**) depois do login -- AuthContext guarda o token só em memória; um reload completo
// apagaria a sessão. Toda navegação pós-login é via clique em link/botão real da UI.
const E2E_EMAIL = "e2e-playwright@biomatcad.example";
const E2E_PASSWORD = "e2e-synthetic-password-123";

// Contrato conhecido do fixture (seed_e2e_user.py): tetraedro sintético ASCII, 4 facets, 4*3=12
// vértices não-indexados (StlViewer renderiza malha não-indexada, ver comentário em
// uniqueVertexCount/StlViewer.tsx -- o nome é histórico, o valor exibido NÃO é deduplicado).
const EXPECTED_TRIANGLE_COUNT = "4";
const EXPECTED_VERTEX_COUNT = "12";
const EXPECTED_FORMAT_LABEL = "STL ASCII";

async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(E2E_EMAIL);
  await page.getByLabel("Senha").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

/** Navegação 100% via UI real (mesmo percurso do teste 2 de vertical.spec.ts) até a página do
 * job pré-semeado, cujo StlViewer é o alvo de todos os testes deste arquivo. */
async function gotoPreseededJobPage(page: Page): Promise<void> {
  await login(page);
  await page.getByRole("link", { name: "Projetos BioMatCAD" }).click();
  await expect(page).toHaveURL(/\/app\/projects$/);
  await page.getByRole("link", { name: "Projeto E2E (pré-semeado)" }).click();
  await expect(page).toHaveURL(/\/app\/projects\/.+/);
  await page.getByRole("link", { name: "Ver job" }).click();
  await expect(page).toHaveURL(/\/app\/jobs\/.+/);
}

/** Espera o StlViewer sair de "loading" e chegar a "ready" -- usa o testid
 * "viewer-triangle-count", que só é renderizado no estado "ready" (ver StlViewer.tsx), em vez
 * de um sleep arbitrário. */
async function waitForViewerReady(page: Page) {
  const indicator = page.getByTestId("viewer-triangle-count");
  await expect(indicator).toBeVisible({ timeout: 15_000 });
  return indicator;
}

test.describe("Visualizador 3D (StlViewer) -- cobertura E2E real (Chromium)", () => {
  test("carregamento do STL: chega a 'ready' com formato/contagens reais do fixture", async ({ page }) => {
    await gotoPreseededJobPage(page);

    const indicator = await waitForViewerReady(page);
    await expect(indicator).toContainText(EXPECTED_FORMAT_LABEL);
    await expect(indicator).toContainText(EXPECTED_TRIANGLE_COUNT);
    await expect(indicator).toContainText(EXPECTED_VERTEX_COUNT);

    // Prova de efeito observável, não só presença de testid: o <canvas> real do WebGLRenderer
    // existe e tem dimensões (não é um elemento oculto/de tamanho zero).
    const canvas = page.locator("canvas");
    await expect(canvas).toHaveCount(1);
    const box = await canvas.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(0);
    expect(box?.height ?? 0).toBeGreaterThan(0);

    await expect(page.getByTestId("viewer-experimental-warning")).toBeVisible();
  });

  test("wireframe: alterna o estado do checkbox e mantém a malha renderizada", async ({ page }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const toggle = page.getByTestId("viewer-wireframe-toggle");
    await expect(toggle).not.toBeChecked();
    await toggle.click();
    // Mudança de estado observável real (não só "o botão existe"): o checkbox reflete o novo
    // estado, e a malha continua renderizada (canvas não desaparece / não lança erro).
    await expect(toggle).toBeChecked();
    await expect(page.locator("canvas")).toHaveCount(1);

    await toggle.click();
    await expect(toggle).not.toBeChecked();
  });

  test("transparência: opacidade só aparece quando a transparência está ativa, e o slider é funcional", async ({
    page,
  }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const transparencyToggle = page.getByTestId("viewer-transparency-toggle");
    const opacitySlider = page.getByTestId("viewer-opacity-slider");

    // Efeito observável condicional: o slider de opacidade não existe no DOM até a
    // transparência ser ativada (renderização condicional real de StlViewer.tsx).
    await expect(opacitySlider).toHaveCount(0);
    await transparencyToggle.click();
    await expect(opacitySlider).toBeVisible();

    await opacitySlider.fill("40");
    await expect(opacitySlider).toHaveValue("40");

    await transparencyToggle.click();
    await expect(opacitySlider).toHaveCount(0);
  });

  test("eixos e grade: alternam estado real do checkbox", async ({ page }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const axesToggle = page.getByTestId("viewer-axes-toggle");
    const gridToggle = page.getByTestId("viewer-grid-toggle");

    await expect(axesToggle).not.toBeChecked();
    await axesToggle.click();
    await expect(axesToggle).toBeChecked();

    await expect(gridToggle).not.toBeChecked();
    await gridToggle.click();
    await expect(gridToggle).toBeChecked();

    // Ambos ativos simultaneamente não quebram a renderização (canvas continua presente).
    await expect(page.locator("canvas")).toHaveCount(1);
  });

  test("bounding box: alterna estado real do checkbox", async ({ page }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const bboxToggle = page.getByTestId("viewer-bbox-toggle");
    await expect(bboxToggle).not.toBeChecked();
    await bboxToggle.click();
    await expect(bboxToggle).toBeChecked();
    await expect(page.locator("canvas")).toHaveCount(1);
  });

  test("clipping: o controle de posição só aparece quando o corte está ativo", async ({ page }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const clippingToggle = page.getByTestId("viewer-clipping-toggle");
    const clippingPosition = page.getByTestId("viewer-clipping-position");

    await expect(clippingPosition).toHaveCount(0);
    await clippingToggle.click();
    await expect(clippingPosition).toBeVisible();

    await clippingPosition.fill("25");
    await expect(clippingPosition).toHaveValue("25");

    await clippingToggle.click();
    await expect(clippingPosition).toHaveCount(0);
  });

  test("screenshot: dispara um download real de PNG (sem comparação de pixels)", async ({ page }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("viewer-screenshot").click();
    const download = await downloadPromise;

    // Prova o EVENTO e o FORMATO real do arquivo -- não uma comparação visual pixel a pixel
    // (proibida pela regra 5): nome sugerido, e assinatura binária (magic bytes) PNG real.
    expect(download.suggestedFilename()).toBe("biomatcad-scaffold-screenshot.png");

    const savePath = path.join(test.info().outputDir, "viewer-screenshot-download.png");
    await download.saveAs(savePath);
    const bytes = fs.readFileSync(savePath);
    const pngMagic = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    expect(bytes.subarray(0, 8).equals(pngMagic)).toBe(true);
    expect(bytes.length).toBeGreaterThan(8);
  });

  test("fullscreen: exercita o contrato real da Fullscreen API sob Chromium (com ou sem suporte headless)", async ({
    page,
  }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const fullscreenButton = page.getByTestId("viewer-fullscreen");
    // O próprio componente só renderiza este botão quando `fullscreenSupported` é verdadeiro
    // (ver StlViewer.tsx) -- se o Chromium headless não expuser a API, o testid nem existe, e
    // isso já é, por si só, o contrato honesto documentado pela regra 6. Só prosseguimos com a
    // interação se o botão estiver presente.
    const isRendered = (await fullscreenButton.count()) > 0;
    test.skip(!isRendered, "fullscreenSupported=false neste Chromium -- StlViewer não renderiza o botão (contrato esperado, não uma falha).");

    await expect(fullscreenButton).toHaveText("Tela cheia");
    await fullscreenButton.click();

    // Chromium headless pode ou não conceder Fullscreen real sem interação de usuário "de
    // verdade" (limitação documentada da regra 6). handleToggleFullscreen() engole a rejeição
    // via .catch(() => undefined) -- então o único jeito honesto de provar o contrato é
    // observar QUAL dos dois desfechos realmente ocorreu, sem forçar um resultado específico.
    await page.waitForTimeout(300);
    const fullscreenElementExists = await page.evaluate(() => Boolean(document.fullscreenElement));
    const buttonLabel = await fullscreenButton.textContent();

    if (fullscreenElementExists) {
      expect(buttonLabel).toBe("Sair de tela cheia");
      await fullscreenButton.click();
      await expect(page.evaluate(() => Boolean(document.fullscreenElement))).resolves.toBe(false);
    } else {
      // Chromium headless recusou (comportamento observado sem gesto de usuário "de verdade"
      // via CDP) -- o componente NÃO deve travar em um estado inconsistente: o rótulo do botão
      // permanece "Tela cheia" (isFullscreen nunca virou true sem o navegador confirmar).
      expect(buttonLabel).toBe("Tela cheia");
    }
  });

  test("cancelamento: aborta um download real interceptado (sem sleep arbitrário)", async ({ page }) => {
    const failedDownloadRequests: string[] = [];
    page.on("requestfailed", (request) => {
      if (/\/api\/v1\/artifacts\/.+\/download/.test(request.url())) {
        failedDownloadRequests.push(request.failure()?.errorText ?? "sem-detalhe");
      }
    });

    let releaseRoute: () => void = () => undefined;
    const routeGate = new Promise<void>((resolve) => {
      releaseRoute = resolve;
    });
    await page.route("**/api/v1/artifacts/*/download", async (route) => {
      // Segura a resposta indefinidamente (nunca resolve por sleep) -- só o cancelamento real
      // do AbortController do StlViewer (handleCancelLoad -> abortControllerRef.abort()) pode
      // encerrar esta requisição antes do teste terminar.
      await routeGate;
      await route.continue();
    });

    try {
      await gotoPreseededJobPage(page);

      const cancelButton = page.getByTestId("viewer-cancel-button");
      await expect(cancelButton).toBeVisible({ timeout: 10_000 });
      await cancelButton.click();

      // Efeito observável de estado: UI transiciona para "cancelled" (EmptyState + botão de
      // retry), nunca chega a "ready".
      await expect(page.getByText("Carregamento cancelado")).toBeVisible();
      await expect(page.getByTestId("viewer-retry-button")).toBeVisible();
      await expect(page.getByTestId("viewer-triangle-count")).toHaveCount(0);
      await expect(page.locator("canvas")).toHaveCount(0);

      // Prova de que o carregamento foi REALMENTE abortado no nível de rede (não só que a UI
      // mudou de estado): o Chromium reporta a requisição como falha por abort
      // (net::ERR_ABORTED), gerado pelo AbortController.abort() do próprio componente.
      await expect.poll(() => failedDownloadRequests.length, { timeout: 5_000 }).toBeGreaterThan(0);
      expect(failedDownloadRequests.some((reason) => /abort/i.test(reason))).toBe(true);
    } finally {
      releaseRoute();
    }
  });

  test("retomada após cancelamento: 'Carregar novamente' consegue chegar a 'ready'", async ({ page }) => {
    let firstAttemptBlocked = false;
    let releaseFirstAttempt: () => void = () => undefined;
    const firstAttemptGate = new Promise<void>((resolve) => {
      releaseFirstAttempt = resolve;
    });

    await page.route("**/api/v1/artifacts/*/download", async (route) => {
      if (!firstAttemptBlocked) {
        firstAttemptBlocked = true;
        await firstAttemptGate;
        // A primeira tentativa é abortada pelo cliente antes de chegarmos aqui (o cancelamento
        // interrompe o fetch) -- route.continue() após o gate é inofensivo mesmo assim.
        await route.continue();
        return;
      }
      await route.continue();
    });

    await gotoPreseededJobPage(page);
    await expect(page.getByTestId("viewer-cancel-button")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("viewer-cancel-button").click();
    await expect(page.getByTestId("viewer-retry-button")).toBeVisible();

    releaseFirstAttempt();
    await page.getByTestId("viewer-retry-button").click();

    const indicator = await waitForViewerReady(page);
    await expect(indicator).toContainText(EXPECTED_TRIANGLE_COUNT);
  });

  test("descarte de recursos ao sair da página: canvas é removido e nenhum erro de console ocorre", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(String(err)));
    page.on("console", (msg) => {
      if (msg.type() === "error") pageErrors.push(msg.text());
    });

    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);
    await expect(page.locator("canvas")).toHaveCount(1);

    // Navegação real via UI (nunca page.goto(), ver comentário no topo do arquivo) -- prova que
    // o cleanup do useEffect de carregamento (StlViewer.tsx) roda de verdade ao desmontar:
    // container.innerHTML é limpo, o WebGLRenderer é disposed, e nenhum acesso a ref nulo
    // dispara erro (bug documentado e corrigido em rodada anterior).
    await page.getByRole("link", { name: "Projetos BioMatCAD" }).click();
    await expect(page).toHaveURL(/\/app\/projects$/);

    await expect(page.locator("canvas")).toHaveCount(0);
    expect(pageErrors, `Erros de console/página durante a navegação: ${pageErrors.join("; ")}`).toEqual([]);
  });

  test("reset de câmera: clique não gera erro e mantém a malha renderizada", async ({ page }) => {
    await gotoPreseededJobPage(page);
    await waitForViewerReady(page);

    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(String(err)));

    await page.getByTestId("viewer-reset-camera").click();
    await expect(page.locator("canvas")).toHaveCount(1);
    expect(pageErrors).toEqual([]);
  });
});
