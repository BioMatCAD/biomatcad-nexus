# E2E (Playwright) — Incremento 2.1.1, item 12

Este diretório contém um teste E2E real (não simulado) do caminho:
login → materiais → projeto → receita → design-run → status do job → visualização/download.

## APROVADO no Windows (2026-07-29, commit `f7a9614`)

Com as duas correções abaixo aplicadas, o usuário rodou `npm run test:e2e` de verdade no
Windows: API real em `localhost:8000`, frontend real em `localhost:5173`, Chromium real,
ambiente Python isolado, seed `already_seeded`, as duas portas confirmadas
(`TcpTestSucceeded=True`). Resultado literal:

```text
Running 2 tests using 1 worker

ok 1 -- login, criação de projeto e receita via UI real
ok 2 -- página de job succeeded (pré-semeado) exibe status, métricas e link de download do STL

2 passed (8.9s)
PlaywrightExitCode=0
```

**O que isso prova**: a interface (frontend real + API real + Postgres real), a navegação
client-side pós-login e a exibição de status/métricas/download funcionam corretamente ponta-a-
ponta contra uma execução de navegador real, não simulada.

**O que isso NÃO prova** (ressalva importante de escopo): o cenário 2 usa um job succeeded
PRÉ-SEMEADO (`scripts/seed_e2e_user.py`, via `_FakeWorkerClientForE2ESeed` -- nunca PicoGK
real). Este E2E não executa nem prova a execução do worker PicoGK real através do fluxo de
produção completo (API → fila → dispatcher → worker → STL → Artifact/Manifest → download).
Essa é uma prova separada, ainda pendente -- ver `docs/examples/WINDOWS_EXECUTION_KIT.md` e
`apps/api/scripts/verify_full_pipeline_sha256.py` para o kit que prepara exatamente essa verificação.

## Duas falhas reais corrigidas (2026-07-29): navegação via reload perdia a sessão + status testado em inglês

Com o bug do `__dirname` já corrigido, o usuário rodou o E2E completo de verdade no Windows:
API real em `localhost:8000`, frontend real em `localhost:5173`, Chromium funcional, seed
`already_seeded`. Resultado: os dois testes RODARAM (não travaram mais no `globalSetup`), mas
ambos FALHARAM:

- Teste 1 (`vertical.spec.ts:22`): `page.fill("#project-name", ...)` esgotou o timeout de 30s --
  o elemento nunca apareceu.
- Teste 2 (`vertical.spec.ts:76`): `getByText("succeeded")` não encontrou nada em 5s.

Inspecionei os dois traces e `error-context.md` anexados (não apenas os logs) antes de mexer em
qualquer código. Os **page snapshots** dos dois pontos de falha mostram algo revelador: em
AMBOS os casos, a página ainda exibia a tela de LOGIN ("Entrar", campos E-mail/Senha) -- mesmo
depois de `expect(page).toHaveURL(/\/app/)` já ter passado com sucesso antes. Ou seja, o app
JÁ tinha autenticado e navegado para `/app`, mas alguma coisa entre esse ponto e a falha
derrubou a sessão de volta para `/login`.

**Causa raiz real (não é defeito de interface, rota, autenticação, API ou seed):** o teste usava
`page.goto("/app/projects")` e `page.goto(\`/app/jobs/${id}\`)` para navegar depois do login.
`page.goto()` força um RELOAD COMPLETO do navegador -- e `AuthContext.tsx` guarda o token de
sessão SOMENTE em memória (decisão de segurança documentada e proposital: "Não armazene tokens
de longa duração... em localStorage", comentário original no arquivo). Um reload reinicia o
app React do zero, o `AuthContext` volta vazio, e `ProtectedRoute.tsx` redireciona para
`/login` -- exatamente o que os page snapshots mostram. **A causa está no teste**, que usava uma
técnica de navegação incompatível com o próprio design de segurança documentado da aplicação
(nunca foi um bug da interface, das rotas, da API ou do seed -- o seed, aliás, funcionou:
`already_seeded`).

Segunda causa, independente, no segundo teste: mesmo com a navegação corrigida, o teste
esperava o literal `"succeeded"` no DOM. A UI real (`JobDetailPage.tsx`) NUNCA renderiza esse
valor bruto -- ela sempre traduz via `STATUS_LABEL` (`succeeded` → **"Concluído"**). Testar
contra `"succeeded"` era testar uma string que a interface jamais exibe.

**Corrigido, sem alterar a geometria aprovada nem inventar interface inexistente:**

- `vertical.spec.ts` reescrito para nunca mais usar `page.goto()` em rotas protegidas depois do
  login -- toda navegação pós-autenticação agora é feita clicando em links/botões reais da UI
  (`getByRole("link", { name: "Projetos BioMatCAD" })` no Sidebar real, `getByRole("link", {
  name: "Ver job" })` na tabela real de `ProjectDetailPage.tsx`), exatamente como um usuário
  faria -- client-side, sem reload, preservando a sessão em memória.
- O segundo teste foi simplificado para um percurso 100% via UI (login → clicar no projeto
  pré-semeado → clicar em "Ver job"), eliminando as chamadas diretas à API que existiam só para
  descobrir o ID do job -- desnecessárias agora que a navegação em si não quebra mais.
- Verificação do status migrada para `getByTestId("job-status")` (novo `data-testid`
  documentado, adicionado em `JobDetailPage.tsx`, ver comentário no próprio arquivo), afirmando
  o rótulo real (`/Conclu[íi]do/i`) em vez do valor bruto da API.
- Adicionados `data-testid="job-metrics"` (tabela de métricas) e `data-testid="stl-download-link"`
  (especificamente o link do artefato STL, não qualquer artefato) -- o segundo teste agora
  confirma de verdade que a página real do job succeeded mostra status, métricas (volume,
  watertight) e o link de download do STL.
- Seletores em geral trocados por `getByRole`/`getByLabel` (nome acessível) em vez de seletores
  CSS crus, onde havia equivalente acessível real (E-mail/Senha/Entrar/Criar projeto/Nome do
  projeto/etc.) -- todos os elementos-alvo já eram acessíveis (labels e `role` reais), não foi
  necessário inventar nada na interface.

**Guardas de regressão adicionadas** (verificadas de verdade: quebrei cada uma deliberadamente e
confirmei a falha, depois restaurei):

- `apps/web/tests/verticalSpecGuard.test.ts`: guarda textual que falha se `vertical.spec.ts`
  voltar a usar `page.goto()` em rota protegida, ou a afirmar o literal `"succeeded"`.
- `apps/web/tests/JobDetailPage.test.tsx`: renderiza `JobDetailPage` de verdade (autenticação
  real via `AuthContext.login()` com `fetch` mockado) com um job succeeded simulado e confirma
  que a UI real mostra "Concluído" (nunca "succeeded"), a tabela de métricas e o link de
  download do STL -- e que um artefato de thumbnail não ganha o mesmo `data-testid` do STL.

Reexecutei `npm run test:e2e` neste sandbox após a correção: o `globalSetup` conclui (sem o bug
do `__dirname`), os dois testes agora tentam lançar o Chromium real e falham pela MESMA causa
já documentada abaixo (`libXdamage.so.1` ausente) -- não mais pela navegação nem pelo texto de
status. Nenhum resultado de E2E foi declarado aprovado; a prova real de que a navegação e as
asserções agora batem com a interface depende da próxima execução do usuário no Windows.

## Bug real corrigido (2026-07-29): `ReferenceError: __dirname is not defined` no Windows

O usuário instalou o Chromium com sucesso no Windows (via `npx playwright install chromium`) e
conseguiu rodar `npm run test:e2e` pela primeira vez de verdade -- mas o `globalSetup` falhou
ANTES de qualquer teste rodar, com o erro literal:

```
ReferenceError: __dirname is not defined
    at .../apps/web/e2e/global-setup.ts:10
    const apiDir = path.resolve(__dirname, "../../api");
```

Causa raiz real: `apps/web/package.json` declara `"type": "module"`, então este arquivo roda
como módulo ES. Módulos ES não têm as variáveis globais de CommonJS `__dirname`/`__filename` --
isso nunca teria funcionado em NENHUMA plataforma sob ESM, mas só apareceu agora porque esta foi
a primeira execução real (o sandbox Linux nunca chegou a rodar o `globalSetup`, pois o processo
Chromium falhava antes disso por `libXdamage.so.1` ausente).

**Corrigido**: `global-setup.ts` agora deriva o diretório do módulo via
`path.dirname(fileURLToPath(import.meta.url))` (multiplataforma, funciona igual em
Linux/macOS/Windows), extraído na função exportada e testável `currentModuleDir(moduleUrl)`.

Ao mesmo tempo, corrigida a seleção do interpretador Python (`resolvePythonBin`, também
exportada e testável): `E2E_PYTHON_BIN` continua tendo prioridade quando definida; sem ela, usa
`"python"` no Windows (onde `python3` tipicamente não existe no PATH) e `"python3"` nas demais
plataformas (onde `"python"` sem sufixo costuma faltar).

Testes de regressão adicionados em `apps/web/tests/e2eGlobalSetup.test.ts` (fora de `e2e/`
porque o vitest exclui `e2e/**` da coleta -- aquele diretório é só para specs do Playwright):
testes de comportamento real de `resolvePythonBin`/`currentModuleDir` mais uma guarda textual
que falha se `__dirname` for reintroduzido como identificador executável ou se a seleção do
Python voltar a ser um `"python3"` hardcoded sem diferenciar Windows. Verifiquei a guarda de
verdade: reintroduzi deliberadamente as duas regressões e confirmei que os testes realmente
falham (6 falhas), depois restaurei a correção.

Reexecutei `apps/web/e2e/global-setup.ts` de verdade neste sandbox (via `tsx`, chamando a
função diretamente) após a correção: carregou sem `ReferenceError`, `resolvePythonBin`
retornou os valores esperados para "win32"/"linux", e o script de seed
(`apps/api/scripts/seed_e2e_user.py`) rodou até o fim com sucesso. Em seguida rodei
`npm run test:e2e` de verdade neste sandbox: o `globalSetup` completou sem erro (confirmando a
correção) e a suíte avançou até tentar lançar o Chromium real, onde falhou -- pela MESMA causa
já documentada abaixo (`libXdamage.so.1` ausente), não mais pelo bug do `__dirname`. Ou seja: o
bug relatado pelo usuário está corrigido e comprovado; o bloqueio de navegador neste sandbox
Linux é outro problema, pré-existente, sem contorno possível aqui (ver seções abaixo).

## Status neste ambiente de desenvolvimento: BLOQUEADO

Tentei instalar e executar o Playwright de verdade neste sandbox Linux:

```
npx playwright install chromium   # download dos binários teve sucesso
node -e "require('@playwright/test').chromium.launch()"
```

Resultado real (não simulado):

```
[pid=19][err] .../chrome-headless-shell: error while loading shared libraries:
libXdamage.so.1: cannot open shared object file: No such file or directory
```

`npx playwright install --with-deps chromium` (que instalaria as bibliotecas de sistema
faltantes via apt) falha porque este sandbox não tem acesso a `sudo`/root:

```
sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
```

Este é o MESMO tipo de bloqueio documentado para o worker PicoGK (ambiente sem os
privilégios/dependências nativas necessários, sem contorno silencioso possível) -- ver
`apps/geometry-worker/WORKER_STATUS.md`. Não fabriquei um resultado de execução: o teste abaixo
nunca rodou até o fim neste ambiente.

## Re-confirmação real (2026-07-29, Incremento 2.1.1, pós-correção de calibração)

Reexecutei a tentativa de verdade neste mesmo sandbox, para o item 10 do pedido do usuário
("avançar para validação de interface integrada e E2E Playwright"). Resultado, também real e
não fabricado:

- `chromium_headless_shell` (já baixado de uma tentativa anterior): falha idêntica,
  `libXdamage.so.1: cannot open shared object file: No such file or directory`.
- Tentei também o motor **Firefox** (`npx playwright install firefox` + `firefox.launch()`),
  para verificar se um motor diferente escaparia da mesma classe de dependência nativa ausente:
  falhou pelo mesmo motivo -- o próprio Playwright detecta a falta de dependências do host antes
  de lançar (`Host system is missing dependencies to run browsers`), listando `libxdamage1` e
  `libgtk-3-0` como pacotes necessários.
- Tentei baixar o `.deb` de `libxdamage1` diretamente via `apt-get download` (que não exige
  root, apenas rede) para extrair a biblioteca localmente sem precisar de `sudo` -- isso também
  falhou, mas por um motivo diferente e mais fundamental: o próprio acesso de rede a
  `archive.ubuntu.com` está bloqueado neste sandbox (`502 Bad Gateway`), não apenas a instalação
  privilegiada.

Conclusão honesta: o bloqueio é duplo e não contornável dentro deste ambiente -- falta tanto a
biblioteca nativa quanto qualquer caminho de rede ou privilégio para obtê-la. Nenhum resultado
de E2E foi ou será fabricado neste sandbox. A execução real do E2E, assim como a do worker
PicoGK, depende do usuário rodar os comandos abaixo no seu próprio Windows.

## Como executar (Windows, onde o worker também será testado)

```powershell
cd apps/web
npm install
npx playwright install --with-deps chromium
# Backend real rodando em outro terminal (uvicorn) + dispatcher, apontando para um Postgres real
$env:E2E_API_BASE_URL = "http://localhost:8000"
$env:E2E_WEB_BASE_URL = "http://localhost:5173"
npm run test:e2e
```

O `globalSetup` (`e2e/global-setup.ts`) chama um script Python auxiliar
(`apps/api/scripts/seed_e2e_user.py`) para criar um usuário/organização de teste diretamente no
banco -- não há endpoint público de registro nesta versão da API (autenticação é apenas login,
ver `routers/auth.py`).

## O que este E2E cobre e o que NÃO cobre

Cobre com o backend e frontend REAIS: autenticação, CRUD de materiais/projetos/receitas,
criação de design-run, transição de status via um job efetivamente despachado. Para o job
chegar a `succeeded` sem depender do PicoGK (que é o próprio objeto do bloqueio parcial deste
incremento), o script de setup despacha o job de teste com o mesmo `FakeWorkerClient` rotulado
usado nos testes de integração Python (`apps/api/tests/test_geometry_job_orchestration.py`) --
isto é explicitado no próprio teste E2E e NUNCA deve ser confundido com geometria real do
PicoGK. A geometria real do PicoGK continua sendo validada separadamente (worker C#,
`apps/geometry-worker/tests/`) e via execução manual no Windows.

## Incremento 2.2 Alpha Pesquisa -- status após a consolidação do visualizador 3D (2026-07-30)

O visualizador 3D (`StlViewer.tsx`) foi reescrito nesta rodada com download autenticado,
verificação de checksum, e novos controles (wireframe, transparência/opacidade, eixos, grade,
bounding box, clipping, screenshot, fullscreen, cancelamento) -- ver
`docs/architecture/viewer-3d-audit.md`. Verificado que o testid usado pelo teste E2E acima
(`data-testid="stl-download-link"`, linha `vertical.spec.ts:90`) foi preservado no elemento,
mesmo após a mudança de um `<a href download>` estático para um `<button>` com download
autenticado via Blob/ObjectURL -- então o E2E aprovado no Windows (`f7a9614`) continua válido
sem alterações e pode ser re-executado com o mesmo comando acima.

**Não coberto por este E2E, registrado com transparência**: nenhum dos novos controles do
visualizador (wireframe, transparência, eixos, grade, bounding box, clipping, screenshot,
fullscreen, cancelamento) é exercitado em navegador real por `vertical.spec.ts` -- essa
cobertura hoje existe apenas em nível de componente
(`apps/web/tests/StlViewer.test.tsx`, 21 casos, jsdom). Playwright continua bloqueado neste
sandbox de desenvolvimento (mesma limitação de sempre: bibliotecas nativas do Chromium
ausentes, sem `sudo`). Não foi criado um script Windows novo para esta rodada porque o
comando acima (`npm run test:e2e`) já é o roteiro único e continua correto; se no futuro for
necessário provar os novos controles em navegador real, um novo `*.spec.ts` precisará ser
escrito exercitando os `data-testid`s introduzidos em `StlViewer.tsx` (`viewer-wireframe-toggle`,
`viewer-transparency-toggle`, `viewer-axes-toggle`, `viewer-grid-toggle`,
`viewer-bbox-toggle`, `viewer-clipping-toggle`, `viewer-reset-camera`, `viewer-screenshot`,
`viewer-fullscreen`, `viewer-cancel-button`) -- não fabricado como concluído nesta rodada.

## Rodada Voronoi (Incremento 2.2) -- E2E real reexecutado e APROVADO no Windows (2026-08-06, commit `84f46fc`)

Uma execução real da matriz completa (`Run-VoronoiWindowsValidation.ps1`,
`voronoi-validation-staged-20260806-195638`) tinha reportado `net::ERR_CONNECTION_REFUSED` em
`http://localhost:5173/login` na etapa de E2E -- não por regressão da interface, mas porque o
roteiro nunca iniciava o frontend antes de chamar o Playwright. **Esse registro histórico não é
apagado nem reescrito** (ver `TEST_EVIDENCE.md` seção 23 para o detalhamento completo daquela
execução).

A correção aplicada foi delegar a inicialização do frontend ao próprio Playwright, via a opção
nativa `webServer` (ver `playwright.config.ts`): ele agora inicia o `npm run dev` de forma
rastreada, aguarda a URL responder via polling HTTP antes de rodar qualquer teste, encaminha
stdout/stderr para o log do próprio processo, e encerra apenas o processo que ele mesmo
iniciou. `reuseExistingServer` é sempre `false` quando `CI=true` (função pura testável
`shouldReuseExistingServer()`, coberta por `apps/web/tests/playwrightWebServer.test.ts`).

O usuário então reexecutou SOMENTE o E2E, no mesmo ambiente Windows, via o novo
`scripts/Run-E2EOnly.ps1` (que não repete a matriz geométrica completa) -- e obteve **APROVADO**:

```text
2 passed (24.9s)
E2EExitCode=0
```

API disponível em `127.0.0.1:8000`; frontend Vite iniciado automaticamente pelo Playwright em
`localhost:5173`; `global-setup` executado com o Python real do venv; os dois testes
(`vertical.spec.ts`) passaram -- login/criação de projeto/receita, e a página de job `succeeded`
pré-semeado exibindo status/métricas/download; processos encerrados de forma controlada, sem
órfãos. Relatórios em `C:\biomatcad-runs\e2e-only-20260806-222320\E2E_ONLY_REPORT.{json,md}`;
detalhamento completo em `TEST_EVIDENCE.md` seção 24.

**O que isto prova**: o defeito era exclusivamente de infraestrutura do roteiro de validação,
não da interface, autenticação, seed ou geometria -- confirmado por uma reexecução real e
isolada no mesmo ambiente onde a falha original ocorreu.

**O que isto continua NÃO cobrindo** (ressalva preservada das rodadas anteriores): os novos
controles do visualizador 3D (wireframe, transparência, eixos, grade, bounding box, clipping,
screenshot, fullscreen, cancelamento) continuam sem cobertura E2E em navegador real -- essa
cobertura existe apenas em nível de componente (`StlViewer.test.tsx`, jsdom). Nenhum novo
`*.spec.ts` foi escrito nesta rodada para esses controles.

## Rodada "cobertura E2E do visualizador 3D" -- viewer.spec.ts escrito; execução real no Windows AINDA PENDENTE (2026-08-06)

**A ressalva da seção anterior está desatualizada e não é apagada, apenas superada aqui**: um
novo arquivo `apps/web/e2e/viewer.spec.ts` (12 testes) foi escrito nesta rodada, exercitando em
Chromium real todos os controles do visualizador listados naquela ressalva (wireframe,
transparência, eixos, grade, bounding box, clipping, screenshot, fullscreen, cancelamento) mais
o carregamento do STL, a retomada após cancelamento e o descarte de recursos ao sair da página.

**Pré-requisito corrigido nesta mesma rodada**: `scripts/seed_e2e_user.py` gravava um STL vazio
(zero facets) com um `stl_sha256` fake (`"0"*64`) para o job pré-semeado -- o `StlViewer` nunca
chegava a "ready" para esse job (checksum sempre incompatível, e mesmo que fosse compatível, o
STL não tinha nenhum facet). Isso nunca foi percebido porque os testes de `vertical.spec.ts`
acima só verificam o botão de download, nunca o estado do visualizador. Corrigido para um
tetraedro sintético válido (4 facets) com o SHA-256 real dos bytes -- provado por 2 testes novos
em `apps/api/tests/test_e2e_seed_fixture.py` (rodam o script real via subprocesso e verificam a
persistência de fora). Ver `TEST_EVIDENCE.md` seção 25 para o detalhamento completo.

**O que foi verificado neste sandbox**: `tsc --noEmit`, `eslint .` e `npm run build` limpos;
`vitest run` com **124 passed** (121 pré-existentes + 3 novos de regressão em
`StlViewer.test.tsx`, cobrindo o contrato exato de nome/formato do arquivo de screenshot e o
contrato suportado/não-suportado da Fullscreen API); `npx playwright test --list` confirma a
sintaxe e a configuração dos 14 testes totais (2 + 12).

**O que isto NÃO prova**: a suíte `viewer.spec.ts` nunca rodou de fato em um Chromium real neste
sandbox -- a mesma limitação de sempre (`libXdamage.so.1` ausente, sem `sudo`) bloqueia a
execução real do Playwright aqui, exatamente como bloqueava antes. `scripts/Run-E2EOnly.ps1`
(já aprovado nas rodadas anteriores) não precisou de nenhuma alteração: `npm run test:e2e` já
roda todos os `*.spec.ts` de `apps/web/e2e/`, então a próxima execução real deste mesmo roteiro
no Windows exercitará os 14 testes automaticamente, sem repetir a matriz geométrica. **Esta
cobertura E2E do visualizador só pode ser considerada aprovada depois que essa execução real
retornar 0 falhas** -- não antes.

## Execução Windows real `e2e-only-20260807-001756`: 2 aprovados, 12 REPROVADOS -- causa raiz corrigida (2026-08-07)

A primeira execução real do Windows dos 14 testes (`Run-E2EOnly.ps1`, commit `1be54e3`) reprovou
todos os 12 testes de `viewer.spec.ts` -- `viewer-triangle-count` nunca encontrado, o
`StlViewer` nunca chegava a "ready". `global-setup` reportou `status=already_seeded`.

Causa raiz: o Postgres real do usuário já continha o fixture de rodadas anteriores (seções 23-
24 do `TEST_EVIDENCE.md`), semeado ANTES da correção do STL vazio/hash fake. Como
`seed_e2e_user.py` tinha `if existing_user is not None: return`, essa reexecução nunca corrigia
o job/Artifact legado já persistido -- o `StlViewer` rejeitava por checksum incompatível contra
o hash fake antigo, exatamente como nas 12 falhas relatadas.

Corrigido: `seed_e2e_user.py` agora é uma sequência idempotente e reconciliável -- localiza o
fixture exclusivamente pelas âncoras únicas (e-mail do usuário, `idempotency_key` do design_run)
e repara qualquer componente (Artifact STL, ArtifactManifest) cujo conteúdo divirja do esperado,
sem duplicar e sem tocar em dados alheios ao fixture. 7 testes de regressão novos em
`apps/api/tests/test_e2e_seed_fixture.py` provam cada cenário (banco vazio, reexecução,
fixture legado, arquivo ausente, manifesto obsoleto, dados alheios intactos, consistência do
download) -- ver `TEST_EVIDENCE.md` seção 26 para o detalhamento completo.

`scripts/Run-E2EOnly.ps1` não precisou de nenhuma alteração -- a correção está inteiramente no
script de seed consumido por `global-setup.ts`. **Esta cobertura E2E do visualizador continua
NÃO aprovada** até uma nova execução real no Windows (com o mesmo banco Postgres, agora já
contaminado pelo fixture legado da execução anterior) retornar 14/14 e exit code 0.

## Execução Windows real `viewer-e2e-evidence-20260807-012919` (commit `f8490d9`): seed CONFIRMADO reparado, mesmas 12 falhas por causa raiz DIFERENTE -- corrigida (2026-08-07)

A segunda execução real do Windows (`Run-E2EOnly.ps1`, commit `f8490d9`) confirmou, com
evidência bruta literal (`error-context.md`/`trace.zip` dos 12 testes, anexada pelo usuário),
que a correção da rodada anterior funcionou: `global-setup` reportou `status=repaired`,
`stl_artifact: repaired`, `manifest: repaired` -- o fixture legado do Postgres real foi
genuinamente reconciliado. Mesmo assim, as mesmas 12 falhas de `viewer.spec.ts` persistiram.

Lendo os 12 `error-context.md` e os 12 `trace.zip` antes de qualquer edição: todos os 12 mostram
o usuário autenticado, na página correta (`/app/jobs/<id>`, "Concluído"), refutando a hipótese
de perda de sessão via `page.goto()` pós-login. O ponto comum real: todos mostram "Nenhum
artefato disponível" ao lado de uma lista "Artefatos" que lista corretamente o STL. O `trace.zip`
confirmou requisições de rede corretas (`GET .../artifacts` -> 200 OK, `kind: "stl"`, hash/tamanho
certos) e nenhum erro de console.

Causa raiz real: `JobDetailPage.tsx` monta o `<StlViewer artifactUrl={null}>` na primeira
renderização do job "succeeded" (antes do `Promise.all` de artifacts/manifest resolver), e só
recebe um `artifactUrl` válido um instante depois via atualização de props. Em `StlViewer.tsx`,
o estado `"empty"` ainda tinha um `return` antecipado que nunca montava a `<div
ref={containerRef}>` -- quando `artifactUrl` chegava depois, o efeito de carregamento sempre
abortava no guard `!containerRef.current` (a div nunca existia). Deadlock permanente: preso em
"empty" para sempre.

Corrigido removendo o `return` antecipado de `"empty"` em `StlViewer.tsx` (mesmo padrão já usado
para `"loading"`/`"size-warning"`). Novo teste de regressão em `StlViewer.test.tsx` reproduz
exatamente essa sequência (mount sem artefato, `rerender()` com artefato válido) e comprovadamente
falha sem a correção (verificado via `git stash` isolando só a correção). Corrigido também:
`seed_e2e_user.py` não imprime mais a senha sintética no log do `global-setup` -- ver
`TEST_EVIDENCE.md` seção 27 para o detalhamento completo.

`scripts/Run-E2EOnly.ps1` não precisou de nenhuma alteração. **Esta cobertura E2E do
visualizador continua NÃO aprovada** até uma TERCEIRA execução real no Windows retornar 14/14 e
exit code 0.

## Execução Windows real `e2e-only-20260807-110029` (commit `85b58c4`): 11/14 aprovados -- 3 causas diagnosticadas, corrigidas (2 testes com expectativa errada, 1 defeito real de acessibilidade) (2026-08-07)

A terceira execução real do Windows (`Run-E2EOnly.ps1`, commit `85b58c4`) saltou para 11
aprovados (2 de `vertical.spec.ts` + 9 de `viewer.spec.ts`), 3 reprovados. `global-setup`
reportou `status=already_valid` em todos os componentes, sem senha em texto plano -- confirmando
que as correções anteriores seguem funcionando em produção.

As 3 falhas foram auditadas antes de qualquer edição:

1. **"eixos e grade"** -- expectativa INCORRETA do teste. `StlViewer.tsx` sempre teve
   `showAxes`/`showGrid` com `useState(true)` (o teste unitário já existente confirmava isso
   corretamente há rodadas); o spec E2E assumiu, por engano, um estado inicial desmarcado.
   Corrigido dividindo o teste em dois ("eixos" e "grade" separadamente), provando o estado
   inicial real e a alternância nos dois sentidos, sem forçar nada artificial.
2. **"fullscreen"** -- DEFEITO REAL de acessibilidade. `requestFullscreen()` era chamado no
   `containerRef` (só o `<canvas>`), deixando os controles (inclusive o botão "Sair de tela
   cheia") como irmãos fora da "top layer" do navegador -- o canvas passava a interceptar todos
   os cliques sobre a área dos controles em tela cheia real, afetando qualquer usuário real do
   Chrome, não só o Playwright. Corrigido chamando `requestFullscreen()`/`exitFullscreen()` no
   `<div>` mais externo (`viewerRootRef`, que já envolve controles + canvas), sem z-index/
   position manual e sem `click({force:true})`.
3. **"cancelamento"** -- expectativa INCORRETA do teste, mas exigiu um marcador novo. O container
   do canvas é permanentemente montado desde a correção do deadlock "empty" -> URL, e o
   `<canvas>` é criado assim que o carregamento COMEÇA (antes do fetch resolver) -- cancelar
   aborta só o fetch, o `<canvas>` continua no DOM. Corrigido adicionando
   `data-viewer-status={status}` no container (nunca expõe nada sensível) -- o teste agora prova
   o estado real via esse atributo em vez da presença/ausência do `<canvas>`.

Testes de regressão novos/estendidos em `StlViewer.test.tsx`. **Mutation testing real** via `git
stash`: isolando só a correção de `StlViewer.tsx`, os testes novos de fullscreen e cancelamento
falham exatamente como esperado, confirmando que detectam as regressões de verdade. Ver
`TEST_EVIDENCE.md` seção 28 para o detalhamento completo.

`scripts/Run-E2EOnly.ps1` não precisou de nenhuma alteração. A suíte cresceu de 14 para 15 testes
(divisão de "eixos e grade"). **Esta cobertura E2E do visualizador continua NÃO aprovada** até
uma QUARTA execução real no Windows retornar 15/15 e exit code 0.
