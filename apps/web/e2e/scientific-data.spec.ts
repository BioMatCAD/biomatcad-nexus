import { test, expect, type Page } from "@playwright/test";

// Adendo de Interface Científica Mínima (Incremento 2.3, Rodada 2, Fase R) -- E2E real da
// interface /app/scientific-data contra a API real e um Postgres real, usando EXCLUSIVAMENTE o
// seed sintético (python -m biomatcad_api.seed + biomatcad_api.seed_scientific_data, ver
// e2e/global-setup.ts). Nenhuma chamada real à rede PubChem acontece neste arquivo -- os testes
// de dry-run/submissão/cancelamento abaixo criam uma ScientificIngestionRequest REAL no banco
// (via a API real), mas NENHUM dispatcher de ingestão é iniciado nesta suíte, então nenhuma
// dessas solicitações é efetivamente processada (permanecem em "queued" até serem canceladas
// ou até o teste terminar) -- é exatamente esse estado ("queued", nunca processado) que é
// verificado, nunca um resultado fabricado de "sucesso" que a API não produziu de verdade. O
// cenário de conflito e o de status terminal (partial) usam o registro já semeado por
// seed_scientific_data.py (Fase C/E), que documenta o CONTRATO de uma ingestão sintética, não
// uma execução real contra PubChem/ChEBI (ver docstring do próprio seed).
//
// Regra de navegação (ver e2e/README.md e vertical.spec.ts): nunca page.goto() para uma rota
// protegida (/app/**) após o login -- AuthContext guarda o token somente em memória; um reload
// completo apagaria a sessão. Toda navegação pós-login é feita clicando em links/botões reais.

const RESEARCHER_EMAIL = "demo@biomatcad.example";
const RESEARCHER_PASSWORD = "demo-synthetic-password-123";
const ADMIN_EMAIL = "admin@biomatcad.example";
const ADMIN_PASSWORD = "admin-synthetic-password-456";

const BIOMATERIAL_NAME = "Hidroxiapatita Sintética de Demonstração (fictícia)";
const CHEMICAL_NAME = "Ácido Poliláctico Fictício de Demonstração";
const DRUG_NAME = "Fármaco Fictício de Demonstração X-100";

async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

async function goToScientificData(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Dados científicos" }).click();
  await expect(page).toHaveURL(/\/app\/scientific-data$/);
  await expect(page.getByTestId("scientific-entities-table")).toBeVisible();
}

test.describe("Interface científica -- pesquisador (leitura)", () => {
  test("1-2. login e acesso à listagem de dados científicos", async ({ page }) => {
    await login(page, RESEARCHER_EMAIL, RESEARCHER_PASSWORD);
    await goToScientificData(page);
    await expect(page.getByRole("link", { name: BIOMATERIAL_NAME })).toBeVisible();
    // Aviso de uso responsável sempre visível, nunca condicional.
    await expect(page.getByText(/Registros importados não equivalem a validação científica/i)).toBeVisible();
  });

  test("3-4. detalhe de entidade sintética mostra propriedades e proveniência reais", async ({ page }) => {
    await login(page, RESEARCHER_EMAIL, RESEARCHER_PASSWORD);
    await goToScientificData(page);

    await page.getByRole("link", { name: BIOMATERIAL_NAME }).click();
    await expect(page).toHaveURL(/\/app\/scientific-data\/.+/);
    await expect(page.getByRole("heading", { name: BIOMATERIAL_NAME })).toBeVisible();

    await page.getByRole("button", { name: "Propriedades" }).click();
    const propertiesTable = page.getByTestId("properties-table");
    await expect(propertiesTable).toBeVisible();
    await expect(propertiesTable).toContainText("Módulo de Young (demonstração)");
    // As duas observações conflitantes (fontes Alfa/Beta, valores 12.3/15.7 GPa) coexistem --
    // nenhuma sobrescreve a outra silenciosamente (contrato do domínio, Rodada 1).
    await expect(propertiesTable).toContainText("12.3");
    await expect(propertiesTable).toContainText("15.7");

    await page.getByRole("button", { name: "Proveniência" }).click();
    const provenanceEntries = page.getByTestId("provenance-entry");
    await expect(provenanceEntries.first()).toBeVisible();
    // Correção pós-execução Windows real (rodada 7/9, ver TEST_EVIDENCE.md): a 1a execução real
    // provou que a produção está correta -- as DUAS fontes conflitantes (Alfa/Beta, mesma
    // propriedade, valores divergentes 12.3/15.7 GPa, nunca fundidas) aparecem como entradas de
    // proveniência SEPARADAS, exatamente como o domínio exige (Rodada 1). O defeito era do
    // seletor do teste: um `getByText()` solto com alternância (Alfa|Beta) casava as DUAS
    // entradas ao mesmo tempo, violando o strict mode do Playwright. A correção usa o
    // data-testid estável já existente + `.filter({ hasText })`, provando explicitamente que
    // Alfa e Beta aparecem cada uma exatamente uma vez -- nunca com `.first()` cego, que
    // esconderia a ausência de uma das duas fontes.
    const alphaProvenanceEntry = provenanceEntries.filter({ hasText: "Fonte Sintética Alfa de Demonstração" });
    const betaProvenanceEntry = provenanceEntries.filter({ hasText: "Fonte Sintética Beta de Demonstração" });
    await expect(alphaProvenanceEntry).toHaveCount(1);
    await expect(betaProvenanceEntry).toHaveCount(1);
    await expect(alphaProvenanceEntry).toBeVisible();
    await expect(betaProvenanceEntry).toBeVisible();
  });

  test("5. painel administrativo de ingestão PubChem NÃO aparece para pesquisador", async ({ page }) => {
    await login(page, RESEARCHER_EMAIL, RESEARCHER_PASSWORD);
    await goToScientificData(page);
    await expect(page.getByTestId("pubchem-ingestion-panel")).toHaveCount(0);
  });

  test("11. conflito de ingestão sintético fica visível na aba de conflitos", async ({ page }) => {
    await login(page, RESEARCHER_EMAIL, RESEARCHER_PASSWORD);
    await goToScientificData(page);
    await page.getByRole("link", { name: CHEMICAL_NAME }).click();
    await expect(page.getByRole("heading", { name: CHEMICAL_NAME })).toBeVisible();

    await page.getByRole("button", { name: "Conflitos" }).click();
    const conflictsList = page.getByTestId("conflicts-list");
    await expect(conflictsList).toBeVisible();
    await expect(conflictsList).toContainText("inchikey_shared_with_other_entity");
    await expect(conflictsList).toContainText(/não resolvido/i);

    // O mesmo conflito também deve aparecer do outro lado (other_entity_id) -- nunca visível
    // apenas de um dos dois lados do relacionamento.
    await goToScientificData(page);
    await page.getByRole("link", { name: DRUG_NAME }).click();
    await page.getByRole("button", { name: "Conflitos" }).click();
    await expect(page.getByTestId("conflicts-list")).toContainText("inchikey_shared_with_other_entity");
  });
});

test.describe("Interface científica -- administrador (painel de ingestão PubChem)", () => {
  test("6-7. login administrativo mostra o painel de ingestão na listagem", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await goToScientificData(page);
    const panel = page.getByTestId("pubchem-ingestion-panel");
    await expect(panel).toBeVisible();
    // Correção pós-execução Windows real (rodada 7/9, ver TEST_EVIDENCE.md): o painel, o campo
    // de CIDs e os botões de dry-run/submissão estavam TODOS presentes e funcionais na
    // execução real (confirmado pelos testes 8-12, que dependem exatamente destes elementos) --
    // a falha era só uma frase editorial (`/No máximo 10 CIDs? por solicitação/i`) que assumia
    // um texto exato ("No máximo... CIDs...") não garantido pelo contrato; a produção mostra
    // literalmente "máximo 10 por solicitação", sem o prefixo "No" nem a palavra "CIDs" logo
    // após o número -- uma mudança de redação válida que nunca deveria quebrar o teste. Em vez
    // de fixar a frase, provamos os elementos FUNCIONAIS estáveis (nunca texto editorial), sem
    // duplicar a validação de limite/entrada não numérica já coberta pelo teste dedicado abaixo.
    await expect(panel.getByLabel("Lista de CIDs")).toBeVisible();
    await expect(panel.getByRole("button", { name: "Dry-run" })).toBeVisible();
    await expect(panel.getByRole("button", { name: "Submeter ingestão" })).toBeVisible();
  });

  test("8. dry-run cria uma solicitação real (queued), nunca persiste entidade nenhuma", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await goToScientificData(page);

    await page.getByLabel("Lista de CIDs").fill("2244");
    await page.getByRole("button", { name: "Dry-run" }).click();

    const status = page.getByTestId("ingestion-request-status");
    await expect(status).toBeVisible();
    await expect(status).toContainText(/dry-run — nenhuma entidade persistida/i);
    await expect(page.getByTestId("ingestion-status-value")).toHaveText(/na fila/i);
  });

  test("9-10. submissão real cria e acompanha uma ScientificIngestionRequest (queued)", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await goToScientificData(page);

    await page.getByLabel("Lista de CIDs").fill("702");
    await page.getByRole("button", { name: "Submeter ingestão" }).click();

    const status = page.getByTestId("ingestion-request-status");
    await expect(status).toBeVisible();
    // Sem dispatcher rodando nesta suíte, a solicitação permanece "na fila" -- é exatamente
    // esse estado real (nunca fabricado) que a UI deve mostrar, com um correlation ID real.
    await expect(page.getByTestId("ingestion-status-value")).toHaveText(/na fila/i);
    await expect(status).toContainText("Correlation ID");
  });

  test("12. cancelamento controlado transiciona a solicitação de queued para cancelled", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await goToScientificData(page);

    await page.getByLabel("Lista de CIDs").fill("5090");
    await page.getByRole("button", { name: "Submeter ingestão" }).click();
    await expect(page.getByTestId("ingestion-status-value")).toHaveText(/na fila/i);

    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByTestId("ingestion-status-value")).toHaveText(/cancelado/i);
    // Botão de cancelar desaparece assim que a solicitação atinge um estado terminal.
    await expect(page.getByRole("button", { name: "Cancelar" })).toHaveCount(0);
  });

  test("validação local rejeita mais de 10 CIDs e entrada não numérica antes de qualquer chamada à API", async ({
    page,
  }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await goToScientificData(page);

    await page.getByLabel("Lista de CIDs").fill(Array.from({ length: 11 }, (_, i) => i + 1).join(","));
    await expect(page.getByRole("alert")).toContainText(/No máximo 10 CIDs/i);

    await page.getByLabel("Lista de CIDs").fill("2244, abc");
    await expect(page.getByRole("alert")).toContainText(/apenas números são aceitos/i);
  });
});
