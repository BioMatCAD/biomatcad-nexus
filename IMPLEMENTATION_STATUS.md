# Status de Implementação — BioMatCAD Nexus

Última atualização: 2026-08-06 (rodada Voronoi do Incremento 2.2, branch
`incremento-2.2-alpha-pesquisa` — pesquisa apenas; launcher Windows formalmente DEFERIDO, não
retomado; nenhum dado clínico/paciente real neste incremento). A seção "Rodada Voronoi
(Incremento 2.2)", logo abaixo, é a mais atual e deve ser lida primeiro, seguida da seção
"Incremento 2.2 Alpha Pesquisa" (rodada anterior, GUI/observabilidade/contrato TopologyProvider).
**Bloqueio de runtime nativo do PicoGK em linux-x64 (ADR-0007/ADR-0008) permanece verdadeiro
apenas para ESTE sandbox de desenvolvimento Linux** — o worker PicoGK real foi executado com
sucesso no Windows do usuário em incrementos anteriores (Gyroid). A execução real do Voronoi no
PicoGK **ainda não foi confirmada por nenhuma execução Windows nesta rodada** — ver seção
dedicada abaixo. Este documento existe para que ninguém — incluindo IAs de desenvolvimento
futuras — precise adivinhar o que é real. Regra do Prompt Mestre §3.1: nada aqui é descrito como
"completo" sem ter sido executado e testado nesta sessão. As seções sobre os Incrementos 1.1,
2.1 e 2.1.1 abaixo são mantidas como registro histórico.

## Rodada Voronoi (Incremento 2.2) — segunda topologia real (`voronoi_cell_edges_v1`)

Escopo desta rodada (Seções 1-14 da instrução de retomada): implementação real de uma segunda
topologia (Voronoi de células com struts, não Delaunay renomeado), sobre a base do contrato
`TopologyProvider` da rodada anterior. `master` e as tags `incremento-2.1-base`,
`incremento-2.1.1-final`, `incremento-2.1.1-v2.2.1` não foram tocados. **Incremento 2.2 NÃO é
declarado concluído nesta rodada** — ver "O que ainda depende de execução Windows real" abaixo.

| Item | Status | Evidência |
|---|---|---|
| Auditoria matemática (Voronoi real vs. Delaunay/aproximação) | **Real, decisão registrada** | `docs/architecture/voronoi-cell-edges-v1-math-audit.md` |
| Dependência de triangulação Delaunay 3D (`MIConvexHull` 1.1.19.1019, MIT) | **Avaliada e adotada** | `apps/geometry-worker/BioMatCadGeometryWorker.csproj`; `NOTICES.md` |
| Schema `voronoi_cell_edges_v1` (segundo ramo do `oneOf` de `topology`) | **Real** | `schemas/biomatcem/geometry-recipe-v1.schema.json`; `apps/api/tests/test_recipe_schema_voronoi.py` (41 testes) |
| Geração determinística de sítios (`uniform_random`, `jittered_grid`) | **Real** | `apps/geometry-worker/VoronoiSiteGenerator.cs` |
| Tesselação 3D real + grafo de arestas (via `MIConvexHull`, recorte pelo domínio) | **Real** | `apps/geometry-worker/VoronoiTessellation.cs`; `VoronoiMathTests.cs` (22 testes) |
| Struts implícitos + suavização de nós (smooth-union PicoGK) + calibração de porosidade sobre malha real | **Real (matemática independente de PicoGK provada; execução real do PicoGK não provada neste sandbox)** | `VoronoiImplicitMathTests.cs` (15 testes) |
| `VoronoiTopologyProvider` registrado (`status="implemented"`, Python + C#) | **Real, sem regressão no Gyroid** | `apps/api/src/biomatcad_api/services/topology_providers.py`; `apps/geometry-worker/VoronoiTopologyProvider.cs`; `test_topology_providers.py` |
| Métricas específicas Voronoi (sítios/células/nós/arestas/struts/grau de nó/contenção) | **Real, ponta a ponta (schema→worker→manifesto→frontend)** | `VoronoiTopologyProvider.cs` (`metrics.Extra`); `apps/web/src/pages/JobDetailPage.tsx` |
| 3 golden recipes Voronoi (`block-voronoi-preview-v1`, `block-voronoi-final-v1`, `cylinder-voronoi-preview-v1`) | **Real (validam contra o schema; execução PicoGK real não provada neste sandbox)** | `test_golden_recipes_all_validate` (6/6 com as 3 Gyroid) |
| Frontend: editor de receita, estimativa de custo, aviso de receita pesada, tabela de métricas Voronoi, demo honesto (`DEMO_EXECUTION_UNAVAILABLE`) | **Real** | `RecipeEditorPage.tsx`, `computeCostEstimate.ts`, `JobDetailPage.tsx`, `demoClient.ts`; `RecipeEditorPage.test.tsx` (7 testes) |
| Auditoria STL independente (parser + SDF reimplementados do zero) | **Real, testada contra fixtures sintéticas; nunca rodada contra STL real** | `apps/api/scripts/audit_stl_independent.py`; `test_audit_stl_independent.py` (13 testes) |
| Caderno de invenção confidencial | **Real, não público** | `docs/private/INVENTION_NOTEBOOK_VORONOI.md` |
| Roteiro único de validação Windows | **Real (sintaxe validada estaticamente); nunca executado neste sandbox** | `scripts/Run-VoronoiWindowsValidation.ps1` |

**Contagens de teste literais desta rodada** (ver `TEST_EVIDENCE.md`, seção 19, para o registro
completo com comandos):

- Worker C# (`dotnet test`): **99 passed, 0 failed** (62 Gyroid pré-existentes, sem regressão +
  22 `VoronoiMathTests` + 15 `VoronoiImplicitMathTests`).
- Backend (`pytest`): **194 passed, 2 failed (pré-existentes, não relacionados a Voronoi,
  reproduzidos comparativamente contra o commit `d09a616`), 2 skipped**.
- Frontend (`vitest run`): **118 passed, 0 failed** (23 arquivos); `tsc --noEmit` 0 erros;
  `eslint` 0 problemas; `build` e `build:pages` com sucesso.

**Commits desta rodada** (`incremento-2.2-alpha-pesquisa`, do primeiro ao último, do mais antigo
ao mais novo): `e07a5e2`, `347289c`, `6790938`, `d09a616`, `64d243b`, `3649550`, `284d2c6`,
`d319986`, `e6b446e`, `622c5a1`, `2f5a43f`, `bf756a4`.

**O que ainda depende de execução Windows real** (não provado neste sandbox Linux, sem PicoGK):

1. Execução de fato do `VoxelsFromImplicit`/`Mesh` do PicoGK sobre as 3 golden recipes Voronoi.
2. Determinismo geométrico real: mesma receita Voronoi + mesma seed, duas execuções reais,
   mesmo SHA-256 de STL (o roteiro `Run-VoronoiWindowsValidation.ps1` está pronto para produzir
   essa evidência, mas ainda não foi executado).
3. A auditoria STL independente (`audit_stl_independent.py`) rodando contra um STL Voronoi real
   gerado pelo PicoGK (hoje só provada contra fixtures sintéticas de teste).
4. Confirmação visual no visualizador 3D de uma malha Voronoi real.
5. E2E Playwright cobrindo o fluxo Voronoi (bloqueado neste sandbox por falta de dependências
   nativas do Chromium, mesma limitação de sempre).
6. Confirmação de que as 3 golden recipes Gyroid continuam produzindo o mesmo SHA-256 de sempre
   quando executadas lado a lado com as novas golden recipes Voronoi no mesmo ambiente Windows
   (regressão real, não apenas testes unitários).

### Tentativa real de validação Windows (20260806-112714) -- INCONCLUSIVA, causa raiz auditada e corrigida

O usuário rodou `Run-VoronoiWindowsValidation.ps1` de verdade no Windows (com PicoGK real
disponível). Resultado literal: `block-voronoi-preview-v1` excedeu o timeout (`WORKER_TIMEOUT`)
nas duas tentativas, e TODA invocação seguinte do dispatcher falhou em cascata (exit_code=1,
sem produzir nenhum STL) -- inclusive as 3 golden recipes Gyroid de controle, já aprovadas em
rodadas anteriores. **Isso não é uma regressão do Gyroid**: a causa raiz auditada (ver
`TEST_EVIDENCE.md`, seção 20) foi um defeito de orquestração/timeout no roteiro de validação
(um processo `dotnet.exe` órfão deixado por uma condição de corrida no script de gate), não uma
mudança na matemática/worker Gyroid.

Causa mais provável do `WORKER_TIMEOUT` em si (auditoria de código, sem poder reexecutar PicoGK
real neste sandbox para confirmar por instrumentação direta): a calibração de porosidade
fechada sobre malha real, reaproveitada do Gyroid, faz até 12 iterações de voxelização+malha
completas -- para Voronoi, cada avaliação por voxel é O(arestas+nós) sem estrutura de
aceleração espacial (limitação já documentada no próprio código como risco assumido), ~78x mais
cara que a avaliação O(1) do Gyroid nesta receita específica. **Não confirmado por medição real
de tempo no Windows** -- nenhum timeout de golden recipe foi alterado sem essa prova, por
instrução explícita.

Correções aplicadas (código de orquestração, nunca a ciência Gyroid/Voronoi em si):
`worker_client.py` (confirmação real de encerramento de árvore de processos + preservação de
stdout/stderr no erro persistido), `geometry_dispatcher.py` (flush=True nos prints de
diagnóstico), `verify_full_pipeline_sha256.py` (margem de timeout sempre maior que o orçamento
interno do worker + kill de árvore como defesa em profundidade),
`Run-VoronoiWindowsValidation.ps1` (isolamento real entre receitas via detecção/limpeza de
processos órfãos, `E2E_PYTHON_BIN` definida explicitamente, duração registrada por execução),
novo `Run-VoronoiWindowsValidation-Staged.ps1` (piloto de 2 receitas antes da matriz completa),
`global-setup.ts` (E2E_PYTHON_BIN agora obrigatória, nunca mais cai para o Python global),
2 testes backend corrigidos (premissas válidas só em Linux, ver `TEST_EVIDENCE.md` seção 20),
11 testes novos de regressão. Suítes completas re-executadas neste sandbox após as correções:
99 C# (sem regressão), 206 pytest passed + 2 failed pré-existentes (mesmas de sempre) + 1
skipped, 119 vitest passed.

**Veredito desta rodada de correção: NÃO declara Voronoi aprovado nem reprovado
cientificamente** -- nenhuma das 6 golden recipes produziu um STL real na rodada
20260806-112714, e o roteiro corrigido ainda não foi executado de novo no Windows. Ver
`TEST_EVIDENCE.md`, seção 20, para o registro completo e honesto do que essa rodada demonstrou
e do que não pôde demonstrar.

### Validação Windows real 20260806-133141 -- cascata de processos órfãos CONFIRMADA corrigida, Voronoi ainda REPROVADO, 3 falhas backend diagnosticadas e corrigidas

O usuário reexecutou a validação Windows (roteiro estagiado, commit `1cdc062`) e reportou
resultado literal: `block-voronoi-preview-v1` reproduziu o `WORKER_TIMEOUT` em 2/2 execuções
(66.7s e 65.5s), mas **nenhuma árvore `dotnet.exe` órfã** foi encontrada antes/depois de nenhuma
execução, e `preview-gyroid-low-res-v1` (executado logo depois dos dois timeouts) passou 2/2 com
determinismo confirmado (SHA-256 idêntico) -- **confirmando que a correção da cascata de
processos órfãos da rodada anterior (20260806-112714) funcionou de verdade no Windows real**.

Nova hipótese investigada (auditoria real, não suposição): o parâmetro `bEndAppWithTask` do
Voronoi estaria no padrão `false`. **Auditoria concluída e hipótese REFUTADA**: leitura direta
do código-fonte vivo confirma que `VoronoiScaffoldBuilder.cs` já passa `bEndAppWithTask: true`,
de forma idêntica ao Gyroid. Decompilação real do `PicoGK.dll` 2.2.0 (via `ilspycmd`) revelou
que `bEndAppWithTask: true` sozinho não garante o encerramento do processo -- depende também do
estado interno do viewer nativo (`bIsIdle()`), fora do alcance de qualquer parâmetro de
aplicação. Ver `apps/geometry-worker/WORKER_STATUS.md` seção 12 e `TEST_EVIDENCE.md` seção 21
para o registro técnico completo. **Voronoi continua sem STL real produzido -- não pode ser
declarado aprovado.**

As 3 falhas backend (`205 passed, 3 failed` -- uma nova em relação às "2 pré-existentes"
antigas) foram diagnosticadas como contaminação real: a suíte pytest rodava contra a MESMA
instância Postgres da validação manual, e via linhas reais já commitadas por essa validação
(job antigo capturado por engano no teste de cancelamento, 32 jobs reivindicados em vez de 24 no
teste de concorrência, 10 jobs "processing" inesperados na observabilidade). Corrigido via
schema Postgres exclusivo e efêmero para toda a suíte (`apps/api/tests/conftest.py`, nunca toca
no schema `"public"` real) -- **provado nesta rodada, neste sandbox, contra um Postgres efêmero
real semeado com 10 linhas contaminantes reais: 211 passed, 2 skipped, 0 failed, e as 10 linhas
semeadas continuaram intactas depois da suíte**. `Run-VoronoiWindowsValidation.ps1` corrigido
para nunca mais reportar `[OK]` quando o pytest falha de verdade (antes: `-Ok $true`
incondicional + mensagem fixa "2 falhas pré-existentes esperadas", que teria escondido esta
terceira falha nova).

Suítes completas re-executadas nesta rodada: 100 C# (era 99 -- +1 regressão nova: nenhum
`Library.Go` real sem `bEndAppWithTask: true`, escaneando TODOS os providers, não só Gyroid),
211 pytest passed + 2 skipped + 0 failed (contra Postgres isolado -- o ambiente real de
validação), 119 vitest passed, tsc/eslint/build/build:pages OK.

**Veredito desta rodada: cascata de processos órfãos comprovadamente corrigida no Windows;
Gyroid permanece íntegro; Voronoi ainda não aprovado (nenhum STL real produzido); E2E não
executado nesta rodada; as 3 falhas backend eram defeitos reais de isolamento da suíte/roteiro
contra um banco compartilhado, não bugs relacionados à ciência Voronoi/Gyroid -- corrigidos e
comprovados nesta rodada.** Ver `TEST_EVIDENCE.md` seção 21 para o registro completo.

### Rodada 3 -- Fase A real no Windows REFUTA hipótese PicoGK/Voronoi; causa raiz real: deadlock de pipes stdout/stderr no cliente Python

A Fase A (roteiro `Run-VoronoiDirectWorkerProbe.ps1`, invocação direta do worker sem API/
dispatcher) foi executada de verdade pelo usuário no Windows: `block-voronoi-preview-v1`
completou em 2,5s com exit code 0, STL real de 444.684 bytes e encerramento espontâneo
imediato, sem kill externo, sem órfão. **Isso refuta definitivamente a hipótese de que o
algoritmo Voronoi ou o processo PicoGK causam o `WORKER_TIMEOUT`** -- por instrução explícita do
usuário, a Fase B (`WorkerProcessExitCoordinator`/`Environment.Exit`) foi cancelada, sua premissa
não se sustentou.

Com essa hipótese eliminada, a auditoria se voltou para `DotnetPicoGkWorkerClient.execute()`
(`apps/api/src/biomatcad_api/services/worker_client.py`) e confirmou um deadlock clássico de
`subprocess.Popen`: o laço de espera fazia `proc.wait()` repetidamente sem nunca drenar
`stdout`/`stderr`, e se o processo filho escreve mais que o buffer do pipe do SO antes de
qualquer leitura, a própria escrita do filho bloqueia -- mascarando-se como um "travamento" só
resolvido pelo `WORKER_TIMEOUT` externo. Reproduzido de forma real e controlada (~5,7MB
escritos simultaneamente em stdout/stderr): ANTES da correção, `WORKER_TIMEOUT` determinístico;
DEPOIS, sucesso em ~0,18s. Corrigido com drenagem contínua via threads daemon, preservando
integralmente cancelamento, timeout genuíno, diagnóstico completo e extração do JSON final (4
novos testes de regressão permanentes, todos passando).

O achado colateral de `t_library_go_returned: null` na execução real (stderr vazio, DLL
provavelmente desatualizada em relação ao commit que adicionou o marcador de diagnóstico) foi
corrigido no roteiro `Run-VoronoiDirectWorkerProbe.ps1`: build Release explícito antes de
localizar a DLL, `RepoPath`/`OutputDir` absolutos obrigatórios, e um campo de relatório
documentando a causa sem invalidar a conclusão já comprovada.

Suítes completas re-executadas nesta rodada: worker C# 100/100 + 11/11 (dois projetos de
teste, via `dotnet vstest` sobre DLLs compiladas -- `dotnet test` en si travou indefinidamente
neste sandbox Linux por uma limitação de infraestrutura do VSTest host não relacionada ao
código, contornada sem alterar a cobertura real); backend 215 passed, 2 skipped, 0 failed
contra Postgres real isolado (as 2 falhas vistas contra SQLite, `test_two_concurrent_
dispatchers_never_claim_the_same_job` e `test_clinical_suite_expiration_is_respected`, são
artefatos documentados de ambiente/tempo, não regressões desta rodada -- confirmado ao
rodar a mesma suíte contra Postgres real); frontend 119/119 vitest + typecheck/lint/build OK.
Ver `TEST_EVIDENCE.md` seção 22 e `apps/geometry-worker/WORKER_STATUS.md` seção 14 para o
registro técnico completo.

**Veredito desta rodada: PicoGK/Voronoi definitivamente exonerados como causa do
`WORKER_TIMEOUT`; causa raiz real identificada e corrigida no cliente Python; roteiro de prova
direta corrigido; novo piloto Windows (Voronoi 2x + Gyroid 2x) ainda pendente de execução real
antes de declarar Voronoi aprovado.**

### Rodada 4 -- Matriz Voronoi/Gyroid APROVADA no Windows real; E2E corrigido (defeito de infraestrutura, não regressão)

O usuário executou o piloto estagiado completo no Windows real
(`voronoi-validation-staged-20260806-195638`), com a correção do deadlock de pipes da rodada 3
já aplicada: **a matriz científica e de orquestração passou integralmente**. As 6 golden
recipes (3 Voronoi + 3 Gyroid de regressão) rodaram 2x cada com o worker PicoGK genuíno --
`queued -> running -> succeeded`, cinco fontes de SHA-256 coerentes, determinismo byte a byte
entre execuções, watertight (worker + auditoria independente), zero arestas non-manifold,
contenção de domínio aprovada, zero processos `dotnet.exe` órfãos. Isso **prova
definitivamente** que a correção do deadlock de pipes (rodada 3) resolve o `WORKER_TIMEOUT`
historicamente relatado, sem qualquer alteração no algoritmo Voronoi/Gyroid, nas golden
recipes ou nos limites de tempo. Ver `TEST_EVIDENCE.md` seção 23 para os 6 hashes SHA-256
literais e `apps/geometry-worker/WORKER_STATUS.md` seção 15 para o registro técnico completo.

O único ponto de falha (`full_exit_code=1`) foi isolado à etapa de E2E:
`net::ERR_CONNECTION_REFUSED` em `http://localhost:5173/login`, porque
`Run-VoronoiWindowsValidation.ps1` nunca iniciava o frontend antes de chamar o Playwright --
um defeito de infraestrutura do próprio roteiro, não uma regressão da interface. Corrigido
delegando ao Playwright a inicialização do frontend via a opção nativa `webServer`
(`apps/web/playwright.config.ts`, com a função pura testável `shouldReuseExistingServer()` e 2
novos testes em `apps/web/tests/playwrightWebServer.test.ts`); corrigido também o
`API_SECRET_KEY` do roteiro (segredo sintético >= 32 caracteres, em vez de herdar
`ENVIRONMENT=test` do passo de pytest e mascarar o valor padrão inseguro de 31 caracteres);
adicionado o segundo projeto de testes do worker (`BioMatCadGeometryWorker.TopologyProviderTests`,
11 testes) à matriz Windows; corrigidas as contagens textuais fixas do relatório (99->100,
118->119); criado `scripts/Run-E2EOnly.ps1` para reexecutar somente o E2E sem repetir a matriz
geométrica completa.

Suítes nesta rodada (sandbox Linux, sem PicoGK real): frontend -- typecheck limpo, lint limpo,
vitest 121/121 (119 pré-existentes + 2 novos), build de produção OK; scripts PowerShell
sintaticamente validados.

**Veredito desta rodada**: matriz Voronoi/Gyroid **APROVADA** no Windows real; correção do
deadlock de pipes **COMPROVADA** no Windows real; E2E desta execução **INCONCLUSIVO** por
defeito de infraestrutura do roteiro (frontend não iniciado), não uma regressão; resultado
global do roteiro falhou **somente** por esse defeito, já corrigido nesta rodada. A
reconfirmação do E2E corrigido ainda depende de uma nova execução real do usuário -- não
declarada aprovada até essa confirmação.

### Rodada 5 -- E2E real reexecutado e APROVADO no Windows (`Run-E2EOnly.ps1`, commit `84f46fc`)

O usuário reexecutou SOMENTE o E2E (`scripts/Run-E2EOnly.ps1`, sem repetir a matriz geométrica)
no mesmo ambiente Windows, contra a API real e o frontend real iniciado automaticamente pelo
Playwright via `webServer` (correção do commit `84f46fc`): **APROVADO**. Evidência literal --
API disponível em `127.0.0.1:8000`; frontend Vite iniciado em `localhost:5173` pelo próprio
Playwright; `global-setup` executado com o Python real do venv; teste 1 (login, criação de
projeto e receita pela UI real) e teste 2 (job `succeeded` pré-semeado exibindo status,
métricas e download do STL) ambos aprovados; `2 passed (24.9s)`; `E2EExitCode=0`; processos
encerrados de forma controlada, sem órfãos. Relatórios em
`C:\biomatcad-runs\e2e-only-20260806-222320\E2E_ONLY_REPORT.{json,md}`. Ver `TEST_EVIDENCE.md`
seção 24 para o registro completo.

**Importante -- não confundir os dois eventos**: a execução original da matriz
(`voronoi-validation-staged-20260806-195638`, rodada 4 acima) permanece registrada como
inconclusiva especificamente naquele E2E, por aquele defeito de infraestrutura já corrigido --
esse registro histórico não foi reescrito nem apagado. Esta rodada 5 documenta uma reexecução
**posterior e separada**, já com a correção aplicada.

**Com isto, tanto a matriz real de 12 execuções Voronoi/Gyroid (6 golden recipes x 2 cada)
quanto o E2E real estão agora ambos APROVADOS no Windows real do usuário.** Nesta rodada não
foi alterada geometria, receita, API, frontend ou contrato científico -- apenas documentação.

### Rodada 6 -- Cobertura E2E real do visualizador 3D escrita e verificada no sandbox; execução real no Windows AINDA PENDENTE

Partindo do commit `3c61b3d`, esta rodada fechou exclusivamente a cobertura E2E
(Playwright/Chromium) dos controles do visualizador 3D já implementados (`StlViewer.tsx`) --
carregamento do STL, wireframe, transparência, eixos, grade, bounding box, clipping,
screenshot, fullscreen, cancelamento real e descarte de recursos -- sem alterar geometria,
receitas, TopologyProviders ou contratos científicos.

A auditoria obrigatória (regra 1 do usuário) revelou um bug real no fixture de teste usado pelo
job pré-semeado (`apps/api/scripts/seed_e2e_user.py`): o STL gravado estava vazio (zero facets)
e o `stl_sha256` retornado era um placeholder fake (`"0"*64`) sem relação com os bytes reais --
isso fazia o `StlViewer` nunca chegar a "ready" para esse job (checksum mismatch + STL sem
facets), um defeito nunca detectado porque `vertical.spec.ts` só verifica o botão de download,
nunca o estado do visualizador. Corrigido com um tetraedro sintético ASCII válido (4 facets) e o
SHA-256 real desses bytes (via `hashlib`, sem dependência nova) -- provado por 2 testes de
regressão novos em `apps/api/tests/test_e2e_seed_fixture.py` que rodam o script real via
subprocesso contra um SQLite efêmero e verificam a persistência de fora.

`apps/web/e2e/viewer.spec.ts` (12 testes novos) e 3 testes de regressão de componente novos em
`apps/web/tests/StlViewer.test.tsx` (screenshot: nome/formato do arquivo; fullscreen: contrato
suportado/não-suportado) foram escritos e verificados por todos os meios disponíveis no
sandbox: `tsc --noEmit` limpo, `eslint` limpo, `vitest run` **124 passed** (121 + 3 novos),
`npm run build` com sucesso, `pytest` backend **217 passed, 2 skipped** contra Postgres real
(215 + 2 novos), e `playwright test --list` confirmando a sintaxe/config dos 14 testes totais.
A execução REAL do Playwright continua **bloqueada neste sandbox** pela mesma limitação
recorrente desde o Incremento 2.1.1 (`libXdamage.so.1` ausente, sem `sudo`) -- documentado
honestamente, não fabricado como aprovado.

`scripts/Run-E2EOnly.ps1` (já existente e aprovado nas rodadas 4/5) não precisou de nenhuma
alteração funcional: `npm run test:e2e` já roda todos os `*.spec.ts` de `apps/web/e2e/`, então a
próxima execução real deste mesmo roteiro no Windows exercitará os 14 testes automaticamente,
sem repetir a matriz geométrica. **Consistente com a regra 17 do usuário, esta cobertura E2E do
visualizador NÃO é declarada aprovada nesta rodada** -- a aprovação depende da execução real do
usuário retornando 0 falhas. Ver `TEST_EVIDENCE.md` seção 25 para o registro completo.

### Rodada 7 -- Execução Windows real `e2e-only-20260807-001756` reprovou 12/14 (viewer); causa raiz confirmada (fixture legado não reconciliado) e corrigida

A primeira execução real do Windows da suíte de 14 testes (`Run-E2EOnly.ps1`, commit `1be54e3`)
retornou 2 aprovados (`vertical.spec.ts`) e **12 reprovados** (`viewer.spec.ts`), todos pela
mesma causa: `viewer-triangle-count` nunca encontrado (o `StlViewer` nunca chega a "ready").
`global-setup` reportou `status=already_seeded`.

Causa raiz confirmada: `seed_e2e_user.py` tinha um `if existing_user is not None: return` --
como o Postgres real do usuário já continha o fixture de rodadas ANTERIORES à correção do STL
vazio/hash fake (seções 23-25), essa saída antecipada nunca corrigia o job/Artifact legado.
Reproduzido byte a byte neste sandbox antes de qualquer edição (corromper manualmente
`Artifact.sha256` para `"0"*64` + STL vazio, confirmar que a versão antiga preservava a
corrupção).

Corrigido: `seed_e2e_user.py` reescrito como uma sequência "get-or-create" totalmente
idempotente e reconciliável, localizando o fixture exclusivamente por âncoras únicas (e-mail do
usuário, `idempotency_key` do design_run) e reparando qualquer componente (Artifact STL,
ArtifactManifest) cujo conteúdo divirja do esperado -- sem duplicar e sem tocar em dados
alheios ao fixture. Corrigido também um risco de segurança real descoberto durante a reescrita:
o script antigo usava `claim_next_queued_job()` (reivindica o job mais antigo de TODA a fila do
sistema), que em um Postgres real de pesquisa arriscaria roubar e fake-executar um job real de
outro usuário -- agora reivindica exclusivamente o `job.id` do fixture.

7 testes de regressão novos (`test_e2e_seed_fixture.py`, reescrito) provam: banco vazio->criado;
reexecução->already_valid sem duplicar; fixture legado (STL vazio+hash fake)->reparado; arquivo
físico ausente->recriado; Artifact correto+Manifest incorreto->reconciliado preservando IDs;
dados alheios ao fixture->intactos; bytes servidos pelo endpoint de download batem com o SHA
persistido. `pytest` backend: **222 passed, 2 skipped** contra Postgres real (215+7). Frontend
reconfirmado inalterado (124 passed, tsc/eslint/build limpos). Playwright real continua
bloqueado neste sandbox (mesma limitação de sempre). `Run-E2EOnly.ps1` não precisou de nenhuma
alteração (a correção é só no script de seed). Ver `TEST_EVIDENCE.md` seção 26.

**Cobertura E2E do visualizador continua NÃO aprovada** -- depende de nova execução real do
usuário no Windows retornando 14/14 e exit code 0.

### Rodada 8 -- Execução Windows real `viewer-e2e-evidence-20260807-012919` (commit `f8490d9`): seed CONFIRMADO reparado, mas as mesmas 12 falhas persistem -- causa raiz real DIFERENTE (deadlock de montagem do `StlViewer`) encontrada e corrigida

A segunda execução real do Windows (`Run-E2EOnly.ps1`, commit `f8490d9`) confirmou, pela
primeira vez com evidência bruta literal (`error-context.md`/`trace.zip` dos 12 testes), que a
correção da Rodada 7 funciona em produção: `global-setup` reportou `status=repaired`,
`stl_artifact: repaired`, `manifest: repaired` -- o fixture legado do Postgres real do usuário
foi genuinamente reconciliado. Mesmo assim, as mesmas 12 falhas de `viewer.spec.ts` persistiram
(`E2EExitCode=1`).

Seguindo a ordem exigida (ler os 12 `error-context.md` -> inspecionar os 12 `trace.zip` -> só
então editar), a hipótese prioritária levantada (perda do token do `AuthContext` via
`page.goto()` pós-login, mesma classe de regressão já corrigida em `vertical.spec.ts`) foi
**refutada pela evidência**: os 12 `banner` mostram o usuário sempre autenticado, sempre na
página correta (`/app/jobs/<id>`, "Concluído"). O ponto comum real, confirmado nos 12
`error-context.md`: todos mostram "Nenhum artefato disponível" sob "Visualização 3D", ao lado de
uma lista "Artefatos" que lista corretamente o STL (mesma renderização). O `trace.zip` de um dos
12 testes confirmou `GET .../artifacts` -> 200 OK com `kind: "stl"` e hash/tamanho corretos, e
nenhum erro de console -- refutando também as hipóteses de rede, checksum, WebGL e exceção
interna do `StlViewer`.

**Causa raiz real**: `JobDetailPage.tsx` monta `<StlViewer artifactUrl={null}>` na primeira
renderização em que o job aparece como "succeeded" (o `setJob` acontece antes do
`Promise.all(listJobArtifacts, getJobManifest)` resolver), e só recebe um `artifactUrl` válido
via atualização de props um instante depois. Em `StlViewer.tsx`, o estado `"empty"` ainda tinha
um `return` antecipado que nunca montava a `<div ref={containerRef}>` -- a MESMA classe de bug
que um comentário já existente no arquivo documenta ter sido corrigida anteriormente para
`"loading"`/`"size-warning"`, mas que ficou de fora daquela correção para `"empty"`. Resultado:
deadlock permanente -- o efeito de carregamento sempre abortava no guard `!containerRef.current`
porque a div nunca existia, preso em "empty" para sempre mesmo com artefato válido.

Corrigido removendo o `return` antecipado de `"empty"` em `StlViewer.tsx`, mantendo a div sempre
montada (como já era para os demais estados pós-decisão). Novo teste de regressão em
`StlViewer.test.tsx` reproduz exatamente a sequência real (mount com `artifactUrl=null`, depois
`rerender()` com URL válida) e chega a "ready" -- confirmado, via `git stash` isolando só a
correção, que o teste genuinamente falha sem ela.

Corrigido também: `seed_e2e_user.py` imprimia a senha sintética em texto plano no log do
`global-setup` -- removida da saída (nenhum consumidor real dependia dela), com novo teste de
regressão permanente verificando o `stdout`/`stderr` brutos do processo.

Verificação completa: `pytest` backend **223 passed, 2 skipped** contra Postgres real via
`pgserver` (222+1); frontend `tsc`/`eslint` limpos, `vitest` **125 passed** (124+1), `build`
limpo; `playwright test --list` confirma os mesmos 14 testes; execução real continua bloqueada
neste sandbox pela mesma limitação recorrente (`libXdamage.so.1`). `Run-E2EOnly.ps1` não
precisou de alteração. Ver `TEST_EVIDENCE.md` seção 27.

**Cobertura E2E do visualizador continua NÃO aprovada** -- depende de uma TERCEIRA execução real
do usuário no Windows retornando 14/14 e exit code 0.

### Rodada 9 -- Execução Windows real `e2e-only-20260807-110029` (commit `85b58c4`): 11 aprovados / 3 REPROVADOS -- salto real de progresso (2 -> 11), 3 causas diagnosticadas e corrigidas

A terceira execução real do Windows (`Run-E2EOnly.ps1`, commit `85b58c4`) confirmou um salto real
de progresso: 11 aprovados (2 de `vertical.spec.ts` + 9 de `viewer.spec.ts`), 3 reprovados. O
`global-setup` reportou `status=already_valid` em todos os componentes, sem a senha em texto
plano -- confirmando que as correções das Rodadas 7/8 seguem funcionando em produção.

As 3 falhas restantes foram auditadas e classificadas individualmente ANTES de qualquer edição:

1. **"eixos e grade"** -- expectativa incorreta do TESTE, não defeito do produto. `StlViewer.tsx`
   sempre teve `showAxes`/`showGrid` com `useState(true)` (visíveis por padrão) -- o teste
   unitário já existente confirmava isso corretamente há rodadas; só o spec E2E assumiu, por
   engano, um estado inicial desmarcado. Corrigido só o teste (dividido em dois, "eixos" e
   "grade" separadamente, provando o estado real e a alternância nos dois sentidos).
2. **"fullscreen"** -- DEFEITO REAL de acessibilidade, confirmado. `requestFullscreen()` era
   chamado em `containerRef` (só o `<canvas>`), deixando os controles como irmãos fora da "top
   layer" do navegador -- o canvas passava a interceptar cliques sobre a área dos controles em
   tela cheia real, inclusive o próprio botão de saída. Afetaria qualquer usuário real do Chrome,
   não só o Playwright. Corrigido introduzindo `viewerRootRef` no `<div>` mais externo (que já
   envolve controles + canvas) e chamando `requestFullscreen()`/`exitFullscreen()` nele -- sem
   z-index/position manual, sem `click({force:true})`.
3. **"cancelamento"** -- expectativa incorreta do TESTE, mas exigiu um marcador novo. O container
   é permanentemente montado (correção do deadlock "empty" -> URL, Rodada 8) e o `<canvas>` é
   criado assim que o carregamento COMEÇA, antes do fetch resolver -- cancelar aborta só o fetch,
   o `<canvas>` continua no DOM. `<canvas>` count=0 após cancelar nunca foi verdade desde aquela
   correção. Corrigido adicionando `data-viewer-status={status}` no container (nunca expõe nada
   sensível) -- o teste agora prova o estado real via esse atributo, não via presença/ausência
   do canvas.

Testes de regressão novos/estendidos em `StlViewer.test.tsx` para os 3 cenários. **Mutation
testing real via `git stash`**: isolando só a correção de `StlViewer.tsx`, os testes novos de
fullscreen e cancelamento falham exatamente como esperado, confirmando que detectam as
regressões de verdade.

Verificação completa: `tsc`/`eslint` limpos; `vitest` **128 passed** (125+3); `build` limpo;
`playwright test --list` confirma **15 testes** (subiu de 14 -- "eixos e grade" virou dois
testes); execução real continua bloqueada neste sandbox (`libXdamage.so.1`, confirmado no log
desta rodada). Backend não tocado; `pytest` reconfirmado **223 passed, 2 skipped** contra
Postgres real (idêntico à Rodada 8). Ver `TEST_EVIDENCE.md` seção 28.

**Cobertura E2E do visualizador continua NÃO aprovada** -- depende de uma QUARTA execução real
do usuário no Windows retornando 15/15 e exit code 0.

### Rodada 10 -- Execução Windows real `e2e-only-20260807-201720` (commit `7719aeb`): 15/15 APROVADOS, exit code 0 -- cobertura E2E completa do visualizador 3D APROVADA (rodada exclusivamente documental)

A quarta execução real do Windows (`Run-E2EOnly.ps1`, commit `7719aeb`, árvore de trabalho
limpa) retornou **15/15 aprovados, 0 falhas, `E2EExitCode=0`**, em 2,1 min de Playwright real
(Chromium real, PowerShell 7.6.4). Relatório em
`C:\biomatcad-runs\e2e-only-20260807-201720\E2E_ONLY_REPORT.md`. Confirma, com prova real, que
as 3 correções da Rodada 9 (eixos/grade, fullscreen, cancelamento) funcionam de ponta a ponta:
"fullscreen com entrada e saída" e "cancelamento real do download" + "retomada após
cancelamento" aparecem explicitamente entre os controles aprovados.

Nenhum código foi alterado nesta rodada (rodada exclusivamente documental, por instrução
explícita) -- as suítes completas já haviam sido rodadas e confirmadas na Rodada 9 sem nenhuma
mudança de código desde então.

**Diferenciação explícita de escopos já registrados** (para não confundir validações reais
distintas): a matriz Voronoi/Gyroid (worker PicoGK real, golden recipes) já estava aprovada
desde a seção 23 do `TEST_EVIDENCE.md` e não foi reexecutada (nem precisava); o E2E principal
(`vertical.spec.ts`) já estava aprovado desde a Rodada 5/seção 24 e seguiu aprovado em todas as
execuções desde então; o item que esta rodada aprova pela primeira vez é especificamente a
cobertura E2E COMPLETA do visualizador 3D (`viewer.spec.ts`, 13 testes), que vinha reprovando
desde a seção 26 (12/12 -> 12/12 por causa diferente -> 3/14 -> agora 0/14, ou seja, 15/15
somando os 2 do vertical).

**`npm audit` -- 11 avisos observados, não corrigidos nesta rodada.** O `npm ci` do frontend
reportou 11 avisos de vulnerabilidade; confirmado que não causaram nenhuma falha na execução
(`exit 0`). Por instrução explícita, `npm audit fix`/`npm audit fix --force` NÃO foram
executados -- nenhuma dependência foi tocada. Registrado como pendência de TRIAGEM separada
(avaliar severidade real e segurança de upgrade) antes do empacotamento final do Incremento 2.2
-- não bloqueia a aprovação do E2E do visualizador, que é sobre comportamento funcional real da
interface. Ver `TEST_EVIDENCE.md` seção 29 para o registro completo.

**Cobertura E2E completa do visualizador 3D: APROVADA no Windows real (15/15, exit code 0).**

## Incremento 2.2 Alpha Pesquisa — resumo (branch `incremento-2.2-alpha-pesquisa`)

Escopo desta rodada: observabilidade real + integração à GUI, GUI completa de pesquisa (retry,
seleção de material, aviso de proveniência), contrato `TopologyProvider` versionado (ADR-0009),
documentação de preparação técnica para Voronoi (sem código), módulo de inteligência
computacional (apenas contratos/registro de decisão, sem IA autônoma real), e integração da
identidade visual oficial (logo). Fora de escopo, explicitamente: prontuário, telemedicina,
dados clínicos reais, integração hospitalar, DICOM, prescrição, diagnóstico, produção clínica,
instalador clínico, launcher definitivo, dados pessoais de pacientes.

| Item | Status | Evidência |
|---|---|---|
| Observabilidade real (6 estados, checks reais) | **Real** | `apps/api/tests/test_observability.py`; painel `ObservabilityPage.tsx` |
| GUI completa de pesquisa (retry, material, proveniência) | **Real** | `apps/web/tests/JobDetailPage.test.tsx`, `ProjectDetailPage.test.tsx`, `RecipeDetailPage.test.tsx`, `MaterialDetailPage.test.tsx` |
| Contrato `TopologyProvider` (Gyroid real, Voronoi `planned`) | **Real** | ADR-0009; `apps/api/tests/test_topology_providers.py` (7 testes); `BioMatCadGeometryWorker.TopologyProviderTests` (5 testes) |
| Preparação técnica para Voronoi | **Documentação apenas, sem código** | `docs/architecture/voronoi-topology-preparation.md` |
| Módulo de inteligência computacional | **Contratos + registro de decisão real; nenhuma IA autônoma concreta** | `apps/api/tests/test_computational_intelligence.py` (7 testes, incluindo regressão que barra implementação concreta de `DesignAdvisor`) |
| Identidade visual oficial (logo) | **Real** | `apps/web/tests/brandAssets.test.ts`, `BrandLogo.test.tsx`, `AboutPage.test.tsx`; `docs/brand/ASSETS_NOTICE.md` |
| Visualizador 3D consolidado (checklist completo, STL real, sem Voronoi) | **Real** | `docs/architecture/viewer-3d-audit.md` (matriz + estado final); `apps/web/tests/StlViewer.test.tsx` (21), `demoStlViewer.test.tsx` (2), `artifactDownload.test.ts` (10), `stlParser.test.ts` (11); `test_artifact_download_is_denied_across_organizations` (backend) |
| E2E Playwright ponta a ponta neste sandbox | **Bloqueado** (mesma limitação de incrementos anteriores) | `apps/web/e2e/README.md`, `playwright.config.ts` — falta biblioteca nativa do Chromium, sem `sudo` |

### Visualizador 3D consolidado (rodada desta sessão -- STL real, sem Voronoi)

Objetivo explícito desta rodada: deixar o visualizador 3D pronto (STL real, controles
completos, métricas rastreáveis, segurança de recursos, testes) para permitir inspeção técnica
adequada de uma futura topologia -- **Voronoi real NÃO foi implementado nesta rodada**, por
instrução explícita.

**Commits desta rodada** (`incremento-2.2-alpha-pesquisa`, todos após `1abb99f`):

| Commit | Conteúdo |
|---|---|
| `32f4969` | Auditoria inicial (`docs/architecture/viewer-3d-audit.md`), antes de qualquer alteração de código -- achou um bug real de autenticação (fetch do STL e links de download sem token) |
| `61e8e2e` | Carregamento seguro: parser ASCII de STL (`stlParser.ts`); novo `artifactDownload.ts` (download autenticado via Blob/ObjectURL, verificação de checksum SHA-256, limite de tamanho) |
| `fa7d09f` | `StlViewer.tsx` com todos os controles pedidos (wireframe, opacidade granular, eixos, grade, bounding box, clipping, screenshot, fullscreen), painel de proveniência com detecção de divergência API/manifesto, aviso experimental literal, limites configuráveis, cancelamento, descarte completo de recursos WebGL, fallback sem WebGL |
| `35c51ee` | Suíte de testes do `StlViewer` (21 casos) + teste de isolamento entre organizações no endpoint de download de artefato (backend); 3 bugs reais de ciclo de vida React/WebGL encontrados e corrigidos durante a escrita dos testes |
| `4180a67` | Corrigido um 4º bug real: checksum placeholder do artefato de demonstração do GitHub Pages fazia a verificação de checksum do cliente falhar sempre; corrigido + teste de regressão com o arquivo real do disco |

**Formatos suportados**: STL binário (já existia) e STL ASCII (novo, `parseAsciiStl` com
detecção automática de formato via `detectStlFormat`).

**Limites adotados** (configuráveis via props do `StlViewer`, valores padrão): tamanho máximo
do arquivo 50 MiB (`DEFAULT_MAX_BYTES`, avaliado ANTES do fetch usando `Artifact.size_bytes` já
conhecido pela API, com gate explícito "Carregar mesmo assim"); acima de 500.000 triângulos
(`DEFAULT_MAX_TRIANGLES_DIRECT`), aviso de malha densa -- renderizada por completo, sem
decimação automática.

**Diferença entre o STL original e qualquer pré-visualização**: não existe pré-visualização
reduzida nesta rodada -- o que é buscado e renderizado é sempre o artefato original completo.
O único "modo reduzido" que existe é o rótulo `demoLabel` do GitHub Pages, que troca o arquivo
de origem inteiro por um STL sintético pequeno e claramente identificado como demonstração
(nunca uma redução do artefato real de uma execução).

**Segurança**: download sempre autenticado via `Authorization: Bearer` (nunca token na URL);
`URL.createObjectURL`/`revokeObjectURL` para evitar vazamento de memória; verificação de
checksum do lado do cliente contra o SHA-256 declarado pela API; teste dedicado de isolamento
entre organizações no endpoint `GET /artifacts/{id}/download` (complementando o já existente
para `GET /jobs/{id}`); nenhum caminho de arquivo do servidor exposto ao frontend; mensagens de
erro sanitizadas (nunca stack trace bruto).

**Testes executados nesta rodada** (contagens literais, ver `TEST_EVIDENCE.md` para o log
completo):
- Frontend: `npx vitest run` -- **23 arquivos de teste, 113 testes, 0 falhas**.
- Frontend: `npx tsc --noEmit` -- 0 erros. `npx eslint . --max-warnings=0` -- 0 erros/avisos.
- Frontend: `npm run build` (produção) e `npm run build:pages` (GitHub Pages/demo) -- ambos com
  sucesso.
- Backend: suíte completa rodada contra Postgres real efêmero (`pgserver`, diretório de dados
  novo) em dois lotes -- **136 testes aprovados, 2 pulados, 0 falhas**.

**Bloqueios/limitações registrados, não escondidos**:
- E2E Playwright continua bloqueado neste sandbox (falta biblioteca nativa do Chromium, sem
  `sudo`) -- mesma limitação de incrementos anteriores. O script de execução no Windows já
  existente (`npm run test:e2e` em `apps/web/`, ver `apps/web/e2e/README.md`) permanece válido
  para re-executar após esta rodada; o testid crítico do botão de download
  (`stl-download-link`) foi preservado, mas os novos controles do visualizador (wireframe,
  transparência, eixos, grade, bounding box, clipping, screenshot, fullscreen, cancelamento)
  ainda não têm cobertura E2E em navegador real, apenas em nível de componente.
- Clipping plane com orientação fixa (só a posição é ajustável); sem decimação/LOD real (apenas
  indicador textual opcional).
- Não há alegação de validação experimental em nenhuma métrica exibida -- o aviso literal
  `Resultado computacional — não validado experimentalmente.` é mostrado sempre que há uma
  malha carregada.

Ver `docs/architecture/viewer-3d-audit.md` para a matriz completa requisito-por-requisito
(20 itens auditados + itens extras encontrados) e o registro pós-implementação item a item.

### Achado real de ambiente de teste (não uma regressão de código) — registrado com transparência

Ao rodar a suíte backend completa nesta rodada, dois testes falharam de forma reprodutível
(`test_two_concurrent_dispatchers_never_claim_the_same_job` reivindicando mais jobs do que os 24
criados pelo próprio teste; `test_clinical_suite_expiration_is_respected` com
`TypeError: can't compare offset-naive and offset-aware datetimes`). Investigação (não
descartada como "flake" sem prova): o `DATABASE_URL` usado apontava para uma instância Postgres
efêmera (`pgserver`) cujo diretório de dados físico (`/tmp/pgserver-inc22` e variantes)
**persiste em disco entre invocações separadas do sandbox**, sem estar mais garantido que
`Base.metadata.drop_all()` (teardown da fixture `engine`) sempre executa até o fim se uma
invocação anterior foi interrompida — deixando linhas `QUEUED` órfãs e ao menos uma linha de
`clinical_suite` com datetime naive de uma execução anterior. **Prova**: subindo uma instância
`pgserver` nova, com diretório de dados vazio, dentro da MESMA chamada, a suíte completa passou
**135 aprovados, 2 pulados, 0 falhas** — confirmando que o mecanismo de exclusão mútua
(`SELECT ... FOR UPDATE SKIP LOCKED`) e a lógica de expiração da suíte clínica estão corretos;
o problema é higiene de dados de teste entre invocações do sandbox, não um defeito de código
introduzido nesta ou em rodadas anteriores. Recomendação registrada para um próximo incremento:
a fixture `engine` deveria fazer `TRUNCATE`/`DROP SCHEMA CASCADE` no **início** da sessão de
testes (não só no fim), para não depender de um teardown limpo da execução anterior.

## Fechamento do Incremento 2.2 Alpha Pesquisa (Fases B-G, branch `incremento-2.2-alpha-pesquisa`)

Rodada de fechamento a partir do commit-base `922cbae` (E2E completo do visualizador 3D já
aprovado, 15/15). Objetivo: concluir os itens genuinamente pendentes (ver `ROADMAP.md` seção
"Reconciliação de pendências -- Fase A") sem repetir nenhuma prova já aprovada e sem antecipar o
launcher/instalador clínico.

| Item | Status | Evidência |
|---|---|---|
| `DesignAdvisor` concreto (Fase B) | **Real** | `apps/api/src/biomatcad_api/services/design_advisor_rule_based.py`; `apps/api/tests/test_design_advisor_rule_based.py` (33 testes) |
| Segurança do ambiente de pesquisa, 14 itens (Fase C) | **Auditado e testado; 1 gap real corrigido (CORS wildcard)** | `apps/api/tests/test_security_hardening.py` (12 testes); `docs/security/RESEARCH_SECURITY_POSTURE.md` |
| Resiliência e recuperação de falha, itens genuinamente novos (Fase D) | **Real** | `apps/api/tests/test_resilience_recovery.py` (6 testes novos) + 2 testes novos em `test_geometry_dispatcher_continuous.py` + 3 test doubles corrigidos |
| Triagem `npm audit`, 11 avisos (Fase E) | **4/11 corrigidos, 7/11 formalmente deferidos com mitigação** | `docs/security/DEPENDENCY_AUDIT_2.2.md` |
| Gates completos -- backend/frontend/worker/scripts (Fase F) | **Todos executados e verificados** | `ruff check`/`mypy` limpos; 259 passed/2 skipped (API); 128/128 (frontend); 111/111 (.NET worker); 10/10 scripts PowerShell com sintaxe válida |
| Determinação de gate Windows complementar (Fase G) | **Nenhum necessário** | `ROADMAP.md` seção "Fase G"; os 4 gates Windows já aprovados (matriz Voronoi/Gyroid, hashes golden, E2E principal, E2E do visualizador) permanecem válidos e suficientes |

### `DesignAdvisor` concreto (Fase B) -- detalhamento

O `Protocol DesignAdvisor` (`computational_intelligence.py`) permanece exatamente como estava,
incluindo o teste de regressão que barra qualquer implementação concreta *nesse mesmo módulo*
(`test_design_advisor_e_apenas_um_protocolo_sem_implementacao_concreta`). A implementação real
(`RuleBasedDesignAdvisor`, `ADVISOR_ID="rule-based-v1"`, `RULES_VERSION="1.0.0"`) vive em um
módulo novo e separado, registrada explicitamente em `_ADVISOR_REGISTRY` -- o mesmo princípio de
não-descoberta-automática já usado pelo `TopologyProviderRegistry` (nenhum plugin/reflexão).

Entradas aceitas: domínio geométrico, topologia, porosidade alvo, resolução, métricas já
calculadas, e material apenas quando explicitamente disponível (nunca inferido). Saída sempre
estruturada: recomendação, justificativas rastreáveis, lista de regras disparadas por ID,
nível de confiança metodológica, limitações, campos ausentes, e um aviso fixo e não removível
de ausência de validação clínica (`NO_CLINICAL_VALIDATION_WARNING`). O módulo nunca inventa uma
propriedade de material que não foi fornecida, nunca prescreve medicação/tratamento/indicação
clínica, e não tem nenhuma dependência obrigatória de IA externa (as 5 regras são determinísticas
e versionadas em código, não chamadas a modelo).

Cobertura de teste (33 cenários): entradas válidas para Gyroid e Voronoi, dados incompletos
(material ausente, resolução ausente), casos de limite da faixa de porosidade das golden
recipes (55-70%), determinismo (mesma entrada -> mesma saída, byte a byte), ausência de qualquer
alegação clínica em qualquer caminho de saída, rastreabilidade de regra (cada recomendação aponta
exatamente quais regras dispararam), e um gap de cobertura real fechado via mutation testing
(`material.source == ""` não era distinguido de material ausente antes do teste
`test_material_com_source_vazia_nao_e_reconhecido_como_disponivel` ser adicionado).

### Segurança do ambiente de pesquisa (Fase C) -- detalhamento

Auditados os 14 itens pedidos. Treze já eram tecnicamente sólidos por construção (autenticação/
autorização, segregação entre organizações e projetos em múltiplos endpoints, proteção de
artefato/download sempre via `Authorization: Bearer`, ausência de segredo hardcoded, sanitização
de log via `RedactSensitiveFilter`, validação de caminho em `LocalStorageAdapter`, ausência de
`shell=True`/concatenação de string em qualquer chamada de subprocesso do worker, controle de
upload/download, auditoria de ação via `AuditEvent`, comportamento seguro em falha), mas sem
teste dedicado que provasse isso de forma permanente e repetível -- agora cobertos por
`test_security_hardening.py` (12 testes).

Um gap real de aplicação foi encontrado: o validador de configuração não rejeitava `cors_allowed_origins`
contendo `"*"` fora de `LOCAL_NETWORK`/`STAGING`/`PRODUCTION` -- corrigido com um novo
`field_validator` em `config.py`, confirmado por mutation testing (desabilitar o validador faz o
teste correspondente falhar de verdade).

`docs/security/RESEARCH_SECURITY_POSTURE.md` documenta os 14 itens com evidência/status e um
disclaimer explícito: isto **não** é conformidade clínica, LGPD completa, segurança hospitalar
ou certificação regulatória de nenhum tipo -- é a postura mínima coerente para um ambiente de
pesquisa que nunca deve receber dado clínico real. RBAC/ABAC completo (17 perfis, OIDC, MFA)
permanece `PM-ONLY-04e/f/g/h`, deliberadamente fora de escopo.

### Resiliência e recuperação de falha (Fase D) -- detalhamento

Auditados os 17 itens pedidos contra a suíte já existente. Catorze já estavam cobertos por
incrementos anteriores (claim atômico via `SELECT FOR UPDATE SKIP LOCKED`, cancelamento real com
kill de processo, timeout, limites computacionais, idempotência, isolamento entre organizações,
encerramento gracioso, ausência de processo órfão -- confirmado empiricamente nas execuções
Windows). Três gaps reais foram encontrados e corrigidos:

1. **Recuperação de job órfão via heartbeat** (`recover_orphaned_jobs`) já existia e já estava
   conectada ao ciclo do dispatcher (`process_queued_jobs`), mas nunca tinha um teste direto --
   adicionado (heartbeat expirado é recolocado na fila; heartbeat recente é ignorado; jobs
   `QUEUED`/`SUCCEEDED` nunca são tocados).
2. **STL vazio do worker** era silenciosamente aceito como artefato "concluído" -- agora é
   classificado como falha real (`WORKER_PARTIAL_OUTPUT`), nunca persistido como sucesso.
3. **Checksum autorreportado pelo worker era confiado cegamente** -- `dispatch_job()` agora
   recalcula o SHA-256 real dos bytes efetivamente gravados e, se o worker reportou um valor
   diferente, marca o job como falho (`WORKER_CHECKSUM_MISMATCH`) em vez de persistir integridade
   não verificada. O manifesto e o registro de `Artifact` sempre usam o hash recalculado, nunca
   o autorreportado.
4. **Dispatcher contínuo não sobrevivia a indisponibilidade transitória do Postgres**
   (`DBAPIError` derrubava o processo inteiro) -- agora tratado como um ciclo vazio (mesmo
   backoff geométrico já existente), com um evento de log estruturado
   (`database_temporarily_unavailable`).

As quatro correções foram confirmadas por mutation testing manual (reintroduzir o defeito,
observar a falha do teste correspondente, restaurar o código original com `diff` byte a byte).
Nenhuma delas depende de comportamento específico do Windows -- são caminhos de controle Python
puros, testados contra um Postgres real efêmero (`pgserver`) no sandbox.

### Triagem de dependências `npm audit` (Fase E) -- detalhamento

Ver `docs/security/DEPENDENCY_AUDIT_2.2.md` para a análise completa item a item. Resumo: dos 11
avisos (5 moderados, 5 altos, 1 crítico) já observados em execução real no Windows, 4 foram
corrigidos nesta rodada com atualização de PATCH sem mudança de comportamento
(`brace-expansion`, `js-yaml`, `nanoid`, `fast-uri`), verificados com a suíte completa do
frontend (typecheck, eslint, 128/128 testes, build normal e GitHub Pages). Os 7 restantes
exigem todos mudança de versão major -- cada um analisado individualmente quanto à
alcançabilidade real e formalmente adiado com mitigação documentada (nunca mascarado, nunca
declarado "sem risco" só por os testes passarem).

### Gates completos no sandbox (Fase F) -- detalhamento

Backend: `ruff check` e `mypy src/ scripts/` totalmente limpos (25 avisos + 2 erros
pré-existentes corrigidos, nenhum relacionado às Fases B-E, nenhuma mudança de comportamento);
suíte completa (259 passed, 2 skipped) contra Postgres real efêmero. Frontend: `tsc --noEmit`,
`eslint . --max-warnings 0`, `vitest run` (128/128), `npm run build` e `npm run build:pages`
(ambos sem erro), `playwright test --list` (15 testes confirmados nos 2 arquivos de spec).
Worker C#: `dotnet build -c Release` (0 Warning(s), 0 Error(s)); `BioMatCadGeometryWorker.Tests`
(100/100) e `BioMatCadGeometryWorker.TopologyProviderTests` (11/11). Scripts: os 10 arquivos
PowerShell do repositório parseiam sem erro de sintaxe (via `PSParser`/PowerShell 7.4.6);
auditoria confirma que nenhum caminho absoluto hardcoded é não-substituível (todos são exemplos
de documentação ou valores padrão de parâmetro) e que todo encerramento de processo é restrito
ao PID rastreado pelo próprio script.

### Determinação do gate Windows complementar (Fase G) -- detalhamento

Ver `ROADMAP.md` seção "Fase G" para a justificativa completa item a item. Conclusão: nenhuma
das mudanças das Fases B-F toca geometria, golden recipes, `TopologyProviders`, PicoGK ou o
código C# do worker, nem introduz comportamento novo de UI -- os 4 gates Windows já aprovados
(matriz Voronoi/Gyroid, hashes golden Gyroid, E2E principal via gate final real, E2E completo do
visualizador 3D 15/15) permanecem válidos e suficientes. Nenhum novo gate Windows obrigatório foi
criado nesta rodada.

## Legenda

- **Real**: código existe, foi executado nesta sessão, com evidência de teste/execução abaixo.
- **Demonstrativo**: existe e roda, mas é uma simulação (dados sintéticos, sem lastro real).
- **Planejado**: aparece em README/roadmap, sem nenhuma linha de código.

## Incremento 2.1.1 (Fase 2, corretivo) — o que é isto e como ler

O Incremento 2.1.1 **não adiciona escopo novo**. É uma correção de defeitos reais encontrados
numa auditoria do Incremento 2.1 (entregue anteriormente), abrangendo schema, worker C#, API e
frontend. Instrução explícita do usuário para este incremento: nenhuma correção pode ser
declarada "provada" além do que foi de fato testado nesta sessão — e a execução real do PicoGK
**continua bloqueada** neste sandbox Linux, exatamente como no Incremento 2.1 (ver ADR-0007).
Por isso, para vários itens abaixo, existe uma distinção importante entre:

- **(a) código corrigido e testado nesta sessão** — via testes unitários/integração que NÃO
  dependem de uma execução real do PicoGK (matemática pura em `GyroidMath.cs`, testes de
  concorrência/cancelamento contra Postgres real, testes de segurança entre organizações, testes
  de frontend); e
- **(b) provado ponta-a-ponta contra uma execução real do PicoGK** — que só poderá acontecer
  depois que o usuário rodar `apps/geometry-worker` no seu próprio Windows x64 (ver
  `docs/examples/WINDOWS_EXECUTION_KIT.md`) e devolver os resultados.

Todo o checklist abaixo usa essa distinção explicitamente. Nada foi apresentado como (b) quando
só (a) foi alcançado nesta sessão.

## Checklist de aceite do Incremento 2.1.1 (17 itens)

| # | Item | Status | Evidência / observação |
|---|---|---|---|
| 1 | Worker PicoGK realmente executado em Windows x64 | **PROVADO para as 3 golden recipes, com o código de calibração corrigido** | Usuário reexecutou de verdade bloco/cilindro/preview contra o commit `da75219` (pós-correção): build Release aprovado, 62/62 xUnit aprovados. As 3 receitas dentro da tolerância MEDIDA. Ver `apps/geometry-worker/WORKER_STATUS.md` §10.4. |
| 2 | Geração real de bloco Gyroid | **APROVADO** | 208.560 triângulos, 102.338 vértices únicos, watertight, validação de recarga do STL aprovada, determinismo binário confirmado em duas execuções (mesmo SHA-256), auditoria independente aprovada. SHA-256: `cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d`. Porosidade dentro de margem pequena (erro -1,33 p.p., dentro da tolerância de 2,0pp agora definida para modo final). Bloco genuinamente gerado pelo PicoGK real, não sintético. |
| 3 | Cilindro realmente recortado (não bounding box) | **APROVADO** | Pós-correção: contenção radial/Z verificada (493.664 triângulos, 1.480.992 vértices examinados, raio máximo 4,999950394mm, intervalo Z [-6,+6]mm, ZERO violações radiais e em Z, `ContainmentExitCode=0`) — prova real de que o corte é pelo volume do cilindro, não bounding box. Porosidade agora dentro da tolerância: alvo 55%, medido 55,75526607688106%, erro +0,7552660768810568pp (tolerância 2pp), convergiu em 5 iterações de calibração por malha. SHA-256: `2cb8cbdf9acbff579c838d8bf3cc2e2a688bcd33a3c475945174272cb278445e`. Auditoria independente aprovada, determinismo confirmado (Run1=Run2). Nota: a checagem de contenção radial/Z específica não foi gerada pela ferramenta `scripts/audit_stl_vs_worker_output.py` deste repositório — ver ressalva em `WORKER_STATUS.md` §10.4. |
| 4 | Diferença real preview vs. final | **APROVADO** | Pós-correção: `preview-gyroid-low-res-v1` executado de verdade com porosidade agora dentro da tolerância de modo preview: alvo 60%, medido 56,733228138231375%, erro -3,2667718617686248pp (tolerância 5pp), convergiu em 4 iterações de calibração por malha. SHA-256: `7660dae3ee263445835bbf9d26c16fa4ef8f8ee2fd2c320000b0546c1eaaba78`. Auditoria independente aprovada, watertight, determinismo confirmado. Prova real da diferença de tolerância por modo (2pp final vs. 5pp preview) e da correção do bug de calibração enganosa encontrado nesta sessão. |
| 5 | Parâmetros efetivamente aplicados (espessura/isovalor/porosidade/seed) | **APROVADO — porosidade PROVADA de verdade para as 3 receitas, pós-correção** | Calibração fechada (`GyroidMath.CalibrateByMonotonicBisection`) confirmada contra a malha real do PicoGK: bloco (1 iteração, erro -1,33pp), cilindro (5 iterações, erro +0,76pp), preview (4 iterações, erro -3,27pp) — todas dentro da tolerância medida por modo. Determinismo confirmado nas 3 receitas (Run1=Run2, `DeterminismoGlobal=True`). Espessura efetiva/isovalor/fase-por-seed continuam sem confirmação ISOLADA contra a malha real (dependeria de reprocessar o STL e comparar campo a campo contra os parâmetros efetivos reportados) — mas o resultado agregado (porosidade medida dentro da tolerância) já prova que a cadeia completa (espessura→banda→SDF→voxelização→malha) funciona corretamente de ponta a ponta. |
| 6 | Limites computacionais efetivamente controlados | Código corrigido, parcialmente verificado nesta sessão; laço de calibração também respeita os limites | Estimativa prévia de voxel/memória testada unitariamente; timeout + kill de árvore de processos **verificado neste sandbox** (cross-platform). Três bugs operacionais reais encontrados e corrigidos ao longo desta sessão via execução real: (1) limpeza de artefatos parciais apagava `job.json` de entrada — corrigido (`OutputCleanup.cs`); (2) viewer do PicoGK não fechava sozinho, inflando `duration_seconds` — corrigido (`bEndAppWithTask: true`); (3) calibração de porosidade cientificamente enganosa (item 5) — corrigida (calibração fechada). O novo laço de calibração fechada descarta Voxels/Mesh de cada candidato via `using`/`Dispose()` entre iterações, respeitando o mesmo limite de memória. Efeitos reais das correções (2) e (3) ainda dependem de nova execução do usuário para confirmação final. |
| 7 | Fila concorrente seguro | **PROVADO de verdade** | `SELECT ... FOR UPDATE SKIP LOCKED` contra Postgres real, duas conexões/threads reais e independentes, zero jobs reivindicados em duplicidade em 24 jobs (`test_geometry_job_concurrency.py`). |
| 8 | Cancelamento real | **PROVADO de verdade** | Teste de corrida contra o fluxo real de `dispatch_job`, kill de árvore de processos via `psutil` (cross-platform), idempotência de recancelamento (`test_geometry_job_cancellation.py`). |
| 9 | Isolamento organizacional | **PROVADO de verdade** | Testes de ataque dedicados (projeto/receita/material de outra organização, receita não pertencente ao projeto, receita não validada) — todos recusados e auditados (`test_geometry_job_security.py`). |
| 10 | Métricas coerentes com o STL | **PROVADO de verdade para as 3 receitas, pré e pós-correção** | Auditoria independente (`scripts/audit_stl_vs_worker_output.py`, ferramenta corrigida nesta sessão para UTF-8/UTF-16 e logs misturados) rodou de verdade contra os 3 STLs reais pós-correção: nenhuma divergência, `AuditExitCode=0` nas três, watertight confirmado nas três. Item fechado. |
| 11 | Manifesto coerente com os artefatos | **APROVADO -- gate final real de produção completo, executado no Windows do usuário** | Gate `apps/api/scripts/verify_full_pipeline_sha256.py` executado de verdade no Windows do usuário via `scripts/Run-FinalGate.ps1`, contra o worker PicoGK real, com um job NOVO (nunca pré-semeado, nenhuma simulação): job `3bf6587d-a9f6-40a1-91bb-f41d385db05d`, idempotency_key `gate-real-e7010eb3d7004294a172a543547ea0da`. Transição observada de verdade `queued -> running -> succeeded`. SHA-256 `cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d` idêntico nas 5 fontes independentes (STL físico, Artifact via API, Artifact via DB, Manifest, download via API). Métricas reais persistidas (`volume_mm3=413.30...`, `porosity_pct_measured=58.67...`, `vertex_count_unique=102338`, `triangle_count=208560`, `is_watertight=true`). Auditoria (`geometry_job_created`, `geometry_job_succeeded`) e associação usuário/organização/projeto/receita confirmadas. Relatório final: `result=APPROVED`, `overall_ok=true`. Ver TEST_EVIDENCE.md §16 para a transcrição literal completa. **Bug real de contrato de dependência encontrado e corrigido no caminho até aqui**: `pyproject.toml` só declarava `psycopg2-binary`, mas a `DATABASE_URL` real usa `postgresql+psycopg` (psycopg 3) -- corrigido adicionando `psycopg[binary]`, com preflight real adicionado a `scripts/Run-FinalGate.ps1` para detectar esse tipo de problema mais cedo no futuro (ver commit `d972471`). Item fechado. |
| 12 | Determinismo geométrico provado | **PROVADO para as 3 receitas, pós-correção** | Usuário confirmou: segunda execução real das três golden recipes (mesma receita+seed+worker+plataforma) produziu hashes IDÊNTICOS aos da primeira execução pós-correção nas três receitas (`DeterminismoGlobal=True`). Determinismo binário genuíno, com o código de calibração corrigido. Item fechado. |
| 13 | Visualização e download | Inalterado do Incremento 2.1, fora do núcleo de correções deste incremento | `StlViewer.tsx` (Three.js, orbit/pan/zoom/wireframe/corte/screenshot) e `JobDetailPage.tsx` continuam como estavam — nenhum defeito relacionado foi relatado na auditoria que motivou o 2.1.1, então nenhuma mudança foi feita aqui. |
| 14 | E2E real | **APROVADO no Windows do usuário (commit `f7a9614`) -- com ressalva de escopo, já fechada pelo item 11** | `npm run test:e2e` real: API em localhost:8000, frontend em localhost:5173, Chromium real, seed `already_seeded`, 2 testes rodados, `2 passed (8.9s)`, `PlaywrightExitCode=0` (ver TEST_EVIDENCE.md §11 para a transcrição literal). **Ressalva original**: o 2º cenário verifica a UI real sobre um job succeeded PRÉ-SEMEADO (`_FakeWorkerClientForE2ESeed`, nunca PicoGK real) -- prova a interface, mas por si só não provava a execução do worker PicoGK real através da fila de produção. **Essa prova complementar foi obtida separadamente no item 11** (gate completo, job novo, PicoGK real, aprovado no Windows) -- os dois juntos fecham a vertical completa (interface real + geometria real + fluxo de produção completo real). |
| 15 | Todos os testes/builds aprovados | **SIM** | Backend: 83 testes pytest (2 skips esperados sem `dotnet`/Windows) contra PostgreSQL real via `pgserver`, 0 falhas; ruff e mypy limpos. Worker C#: 62/62 xUnit neste sandbox E build Release real aprovado no Windows do usuário. Frontend: 42/42 Vitest (`tsc --noEmit` e `eslint` limpos, `npm run build` com sucesso). E2E Playwright: 2/2 aprovados de verdade no Windows do usuário (item 14). |
| 16 | Histórico preservado | **SIM, verificado** | Base (tag/commit do v2.2) intacta; apenas novos commits acrescentados nesta sessão (nenhum `git commit --amend`, `rebase` ou `push --force` usado); `git log` mostra a sequência completa desde o Incremento 1. |
| 17 | Checksums verificados na extração/restauração | **SIM para o bundle base v2.2** (início da sessão); **AINDA NÃO** para o pacote final v2.2.1 | O pacote v2.2.1 (zip/bundle/SHA256SUMS) ainda não foi gerado — é uma tarefa de empacotamento separada, posterior a esta documentação. |
| 18 | Iniciador executável (launcher) do BioMatCAD Nexus para Windows | **APROVADO por execução real no Windows do usuário** | `tools/windows-launcher/` (C#/.NET 9): implementa os 16 comportamentos pedidos (localizar raiz do repo, detectar Python/Node/npm/.NET, criar `.venv`, `pip install -e .` condicional, checar `node_modules`, gerar `API_SECRET_KEY` efêmero via CSPRNG, `ENVIRONMENT=test`, iniciar API/frontend, aguardar prontidão via socket TCP real, abrir `http://localhost:5173/login`, mostrar status/PIDs, encerrar só os filhos rastreados, detectar portas ocupadas, nunca expor o segredo, banner permanente "AMBIENTE DE TESTE"). 54 testes xUnit **reais** (sockets TCP reais, subprocessos reais, diretórios temporários reais — sem fakes de SO) cobrindo os 10 cenários pedidos. **Dois eventos distintos, ambos reais**: (1) cross-publish `win-x64` neste sandbox Linux — `.exe` PE32+ Windows genuíno (confirmado via `file`), SHA-256 `b6ae108ca7305b256d778403211cddb14d31d958cabb3f63b1132d99210070f6`, **apenas compilado nesta etapa, nunca executado** (sandbox não roda win-x64); (2) **execução real relatada pelo usuário no Windows dele**: SHA-256 conferido antes de executar, executável abriu corretamente, API e frontend iniciaram, navegador abriu a interface, login ficou disponível, encerramento funcionou corretamente, nenhum problema observado (ver TEST_EVIDENCE.md §14 para a transcrição literal e o que fica explicitamente fora do relato). Item fechado para o caminho principal; detalhes específicos não relatados individualmente (criação vs. reaproveitamento de `.venv`/`node_modules`, cenário de porta ocupada) permanecem como não confirmados isoladamente, sem impedir a aprovação do comportamento ponta a ponta. |

### Resumo honesto

**Atualização (execução real PÓS-correção -- commit `da75219`)**: o usuário reexecutou de
verdade as três golden recipes contra o worker com a calibração de porosidade corrigida.
Resultado por receita:

- **Bloco: APROVADO.** Watertight, auditoria independente aprovada, determinismo confirmado,
  porosidade dentro da tolerância (alvo 60% / medido 58,6698791858207% / erro -1,33pp / 1
  iteração de calibração por malha). SHA-256 idêntico ao da execução pré-correção (esperado: o
  palpite inicial já convergiu em 1 iteração, então a malha não mudou).
- **Cilindro: APROVADO.** Contenção radial/Z verificada (1.480.992 vértices examinados, raio
  máximo 4,999950394mm, intervalo Z [-6,+6]mm, ZERO violações), watertight, auditoria
  independente aprovada, determinismo confirmado, porosidade agora dentro da tolerância (alvo
  55% / medido 55,75526607688106% / erro +0,76pp / 5 iterações de calibração por malha).
- **Preview: APROVADO.** Watertight, auditoria independente aprovada, determinismo confirmado,
  porosidade agora dentro da tolerância de modo preview (alvo 60% / medido 56,733228138231375%
  / erro -3,27pp / 4 iterações de calibração por malha).

Build Release aprovado, 62/62 testes xUnit aprovados no Windows do usuário (não só neste
sandbox). Auditoria independente (`scripts/audit_stl_vs_worker_output.py`) rodou de verdade
contra os 3 STLs reais: nenhuma divergência, `AuditExitCode=0` nas três. Determinismo pós-
correção confirmado nas três receitas (`DeterminismoGlobal=True`).

Isso fecha, com prova real contra o PicoGK, a calibração de porosidade fechada, a auditoria
independente e o determinismo geométrico para as três golden recipes -- a correção do bug de
calibração enganosa encontrada na rodada anterior está agora provada, não apenas testada
matematicamente ou testada só para o bloco.

**Totalmente fechados e provados com execução real**: itens 1 (worker executado, 3 receitas),
2 (bloco), 3 (cilindro -- geometria e porosidade), 4 (preview -- geometria e porosidade), 5
(porosidade calibrada e medida dentro da tolerância nas 3 receitas), 7, 8, 9, 10 (métricas vs.
STL, auditado de verdade), 12 (determinismo, 3 receitas), 16 (todos exercitados contra
infraestrutura/execução reais).

**Ainda não testado isoladamente**: espessura efetiva/isovalor/fase-por-seed dentro do item 5
(o resultado agregado -- porosidade correta -- já é evidência forte de que a cadeia inteira
funciona, mas não há confirmação campo a campo separada).

**Simplesmente não feitos ainda**: item 14 (E2E Playwright -- nunca executado em nenhum
ambiente), validação da interface integrada (frontend) contra o worker corrigido, item 11
(manifesto -- as execuções reais continuam sendo invocações diretas do worker via CLI, fora do
fluxo API→dispatcher→manifesto), e item 17 para o pacote final v2.2.1 especificamente
(deliberadamente ainda não gerado).

**Sem mudança de escopo neste incremento**: item 13 (visualização/download), que segue como
estava no Incremento 2.1.

**Declaração explícita**: o Incremento 2.1.1 **continua NÃO concluído**. A validação geométrica
real -- calibração, auditoria independente, determinismo e contenção -- está agora APROVADA para
as três golden recipes. Faltam: validação da interface integrada, E2E Playwright real,
consistência STL-vs-manifesto via fluxo completo, e o empacotamento final v2.2.1. Só será
declarado concluído depois que esses critérios também forem realmente aprovados.

> **ATUALIZAÇÃO FINAL (2026-07-29) -- este parágrafo e a lista "Simplesmente não feitos ainda"
> logo acima ficaram desatualizados ao longo da sessão e são preservados aqui apenas como
> registro histórico do estado do incremento NAQUELE ponto.** Desde então, nesta mesma sessão:
> E2E Playwright real foi aprovado no Windows (commit `f7a9614`, item 14, `TEST_EVIDENCE.md`
> §11); e o gate final de produção completo (API -> dispatcher -> worker PicoGK real -> STL ->
> Artifact -> Manifest -> download -> SHA-256 em 5 fontes) foi executado com um job NOVO e
> aprovado no Windows do usuário (item 11, `TEST_EVIDENCE.md` §16). Com os três pilares
> independentemente provados -- geometria real (acima), interface real (E2E), e fluxo de
> produção completo real (gate final) -- **a vertical completa do Incremento 2.1.1 está
> aprovada**. O único item que permanece deliberadamente pendente é o empacotamento final
> v2.2.1, que esta mesma rodada de trabalho está gerando (ver seção dedicada mais abaixo/no
> fechamento deste documento).

## Evidência de teste do Incremento 2.1.1 (resumo; ver `TEST_EVIDENCE.md` para o log consolidado)

- **Backend** (`apps/api`): 83 testes pytest coletados e passando, 2 skips esperados (dependem de
  `dotnet`/ambiente Windows indisponível neste sandbox) — incluindo os novos
  `test_geometry_job_security.py`, `test_geometry_job_concurrency.py`,
  `test_geometry_job_cancellation.py`. `ruff check .` e `mypy src` limpos.
- **Worker C#** (`apps/geometry-worker`): `dotnet build` sem erros; 50/50 testes xUnit passando
  (`GyroidMathTests.cs`, `SimpleMeshWeldTests.cs`, `StlExporterTests.cs`,
  `GeometryMetricsCalculatorTests.cs`, `JobEnvelopeTests.cs`) — todos sobre código independente
  do PicoGK, nenhum contra o runtime nativo (que continua bloqueado, ver ADR-0007).
- **Frontend** (`apps/web`): 27/27 testes Vitest passando (incluindo `schemaSync.test.ts`, que
  garante que a cópia local do schema usada pelo Ajv é byte-idêntica ao schema real do backend),
  `tsc --noEmit` e `eslint` limpos, `npm run build` e `npm run build:pages` executados com
  sucesso.
- **Migração Alembic**: nova revisão do Incremento 2.1.1 (claim atômico e colunas de manifesto)
  verificada tanto a partir de um banco vazio (`alembic upgrade head` do zero) quanto de forma
  incremental (banco já na revisão anterior do Incremento 2.1).
- **Auditoria de dependências** (`docs/security/DEPENDENCY_AUDIT_2.1.1.md`): Python (`pip-audit`)
  e NuGet (`dotnet list package --vulnerable`) sem nenhuma vulnerabilidade conhecida; npm
  (`npm audit`) com 18 vulnerabilidades reportadas — 1 corrigida sem breaking change
  (react-router 6.26.2→6.30.4), 17 deliberadamente deferidas (todas de tooling de desenvolvimento
  — ESLint 8.x e sua cadeia, Vite/Vitest/esbuild — com explorabilidade nula/muito baixa no
  artefato de produção), ver `ROADMAP.md` para o plano de migração.
- **NÃO incluído nesta evidência**: execução real do PicoGK, E2E Playwright executado (ambos
  bloqueados neste sandbox, pendentes da execução real do usuário no Windows).

## O que mudou no Incremento 1.1 (resumo executivo)

O Incremento 1 continha um bug conceitual: o campo `clinical_suite_enabled` tratava Laboratório
como parte da suíte clínica e usava lógica "qualquer um habilitado" em vez de "os três
simultaneamente". O usuário identificou e corrigiu essa divergência. O Incremento 1.1 entrega:

1. Semântica corrigida da chave mestra: `research` e `laboratory` são contextos independentes;
   `clinical_test`/`clinical_pilot`/`clinical_production` só podem ser ativados/desativados **em
   conjunto**, atomicamente, via endpoints dedicados (`POST /api/v1/system/clinical-suite/activate`
   e `.../deactivate`) — ver ADR-0004.
2. Classificação explícita da autenticação atual como **`DEV_AUTH`**, com recusa de startup fora
   do ambiente de teste quando o segredo JWT está ausente/inseguro — ver ADR-0005.
3. Preservação do histórico Git completo (13 commits) via `git bundle`.
4. Reempacotamento com verificação de integridade (`SHA256SUMS.txt`).
5. Revalidação completa: 25 testes de backend (antes 10), 7 testes de frontend (antes 6), ambos
   builds, smoke test HTTP, verificação do bundle.

## Resumo por módulo

| Módulo | Status | Evidência |
|---|---|---|
| `apps/api` — health/ready/version | Real | ver seção "Backend" abaixo |
| `apps/api` — auth (login/me/logout) | Real, classificado como `DEV_AUTH` (mínima — sem MFA/refresh/OIDC) | testes + smoke test abaixo; ADR-0005 |
| `apps/api` — estado operacional independente (Pesquisa/Laboratório) | Real | testes + smoke test abaixo |
| `apps/api` — suíte clínica atômica (teste+piloto+produção) | Real | 7 testes dedicados (`test_clinical_suite.py`); ADR-0004 |
| `apps/api` — modelos + migrações Alembic (2 revisões) | Real | migração aplicada contra PostgreSQL real, do zero |
| `apps/api` — seed sintético (pesquisador + admin) | Real | executado, ver log abaixo |
| `apps/web` — landing/login/dashboard | Real | build + testes abaixo |
| `apps/web` — indicador de suíte clínica x laboratório (separados) | Real | `ClinicalSuiteIndicator.test.tsx` |
| `apps/web` — modo demo (GitHub Pages) | Demonstrativo (por design) | build `build:pages` executado |
| Preservação de histórico Git | Real | `git bundle create --all` + `git bundle verify` |
| `docker-compose.yml` | Não testado neste ambiente | ver "Limitações do ambiente" |
| CAD/FEM/materiais/ML/otimização | Planejado | nenhum código |
| LIMS/ELN/terapia celular/clínica/telemedicina | Planejado | nenhum código (escopo confirmado, ver ADR-0003) |
| RBAC/ABAC completo, Keycloak/OIDC, MFA/WebAuthn, step-up | Planejado | ver `REQUIREMENTS_MATRIX.md` seção D (`PM-ONLY-04a`–`04h`) |
| `schemas/biomatcem` — schema versionado da receita geométrica | Real | `test_recipe_schema.py` (15 testes); ADR-0006 |
| `apps/api` — modelos de materiais/projetos/receitas/jobs/artefatos (9 entidades) | Real | migração `97983fbc0288` aplicada contra banco vazio e populado |
| `apps/api` — orquestração de job (fila = coluna status, sem fila em memória) | Real | `test_geometry_job_orchestration.py` |
| `apps/api` — endpoints de materiais/projetos/receitas/jobs/artefatos | Real | `test_materials_projects_recipes_api.py`, `test_jobs_artifacts_api.py` |
| `apps/geometry-worker` — contrato C#/.NET9+PicoGK 2.2.0 | Real (compila); execução real BLOQUEADA neste sandbox (linux-x64 sem runtime nativo), mas **PROVADA com sucesso no Windows x64 do usuário para `block-gyroid-v1`** (ver §10 de `WORKER_STATUS.md`) | `WORKER_STATUS.md`, ADR-0007, 50 testes xunit sobre código independente de PicoGK — **atualizado para 50 testes no Incremento 2.1.1, ver seção dedicada acima** |
| `apps/web` — catálogo de materiais, projetos, editor de receita, jobs, visualizador 3D (Three.js) | Real | 17 testes Vitest; build normal e de demo executados — **atualizado para 27 testes no Incremento 2.1.1, ver seção dedicada acima** |
| `scripts/geometry_dispatcher.py` — processo separado da API | Real (contrato); execução de sucesso depende do worker bloqueado | inspeção de código + teste do caminho de falha real |
| `apps/api` — claim atômico de fila (Incremento 2.1.1) | **Real, provado** | `test_geometry_job_concurrency.py` (24 jobs, duas conexões reais, zero duplicidade) |
| `apps/api` — cancelamento real de job (Incremento 2.1.1) | **Real, provado** | `test_geometry_job_cancellation.py` (kill de árvore de processos via `psutil`, teste de corrida) |
| `apps/api` — isolamento entre organizações antes de criar `DesignRun` (Incremento 2.1.1) | **Real, provado** | `test_geometry_job_security.py` (testes de ataque) |
| `apps/api` — manifesto reestruturado, checksum fora do JSON (Incremento 2.1.1) | Real (código+testes de unidade/integração); não provado contra execução real do PicoGK | `manifest_service.py`, testes de `test_jobs_artifacts_api.py` |
| `schemas/biomatcem` — semântica espessura/isovalor (Incremento 2.1.1) | Real | `test_recipe_schema.py` (24 testes agora); ADR-0008 |
| `apps/geometry-worker` — `GyroidMath.cs` (domínio real, booleano, espessura/isovalor/porosidade/seed, preview/final) (Incremento 2.1.1) | Real (matemática testada); não provado contra execução real do PicoGK | `GyroidMathTests.cs` |
| `apps/geometry-worker` — solda de vértices (Incremento 2.1.1) | Real (testado com malhas sintéticas); não provado contra STL real do PicoGK | `SimpleMeshWeldTests.cs` |
| `apps/web` — validação de receita com Ajv sobre schema real (Incremento 2.1.1) | Real, provado | `schemaSync.test.ts`, `recipeValidationOffline.test.ts` |
| `apps/web` — fingerprint de demonstração (canonicalização recursiva) (Incremento 2.1.1) | Real, provado; explicitamente rotulado como NÃO sendo SHA-256 real | `recipeValidationOffline.test.ts` |
| `apps/web/e2e` — Playwright (Incremento 2.1.1) | Escrito; **nunca executado neste sandbox** | `apps/web/e2e/README.md` |
| Auditoria de dependências (Incremento 2.1.1) | Real, provado | `docs/security/DEPENDENCY_AUDIT_2.1.1.md` |

## Incremento 2.1 (Fase 2) — vertical geométrica funcional do núcleo BioMatCAD

> **Nota (Incremento 2.1.1)**: a seção abaixo é o registro histórico da entrega original do
> Incremento 2.1. Vários defeitos descritos como simplesmente "não verificados" abaixo foram, na
> verdade, auditados e encontrados como código **incorreto** (não apenas não executado) — ver a
> seção "Incremento 2.1.1" no topo deste documento para a lista completa de correções e o que
> continua pendente de execução real do PicoGK.

**Status geral: parcialmente bloqueado**, conforme instrução explícita do usuário ("Se o PicoGK
não puder ser executado no sandbox, declare o incremento parcialmente bloqueado. Não substitua
silenciosamente o worker por geometria falsa."). Nenhuma parte deste incremento fabrica sucesso
onde há bloqueio real.

### O que é REAL e verificado nesta sessão

- Schema JSON Draft 2020-12 da receita BioMatCEM, com validação estrita (`additionalProperties:
  false` em todos os níveis), canonicalização e checksum SHA-256 reais (`services/recipe_
  service.py`) — 15 testes dedicados.
- 9 entidades de dados (`MaterialRecord`, `MaterialProperty`, `ScientificReference`,
  `BioMatProject`, `GeometryRecipe`, `DesignRun`, `GeometryJob`, `Artifact`,
  `ArtifactManifest`), com migração Alembic aplicada e verificada contra banco vazio E banco já
  na revisão anterior.
- Orquestração real de job: fila baseada na própria coluna `GeometryJob.status` (sem fila em
  memória), com idempotência (unique constraint organização+chave), cancelamento, retry
  controlado, e um processo dispatcher (`scripts/geometry_dispatcher.py`) arquiteturalmente
  separado do processo da API.
- API real com autorização por organização (403 + auditoria em qualquer tentativa de acesso
  cross-organização) para materiais, projetos, receitas, jobs e artefatos.
- Frontend real: catálogo de materiais, projetos, editor de receita com validação ao vivo,
  acompanhamento de job com polling, visualizador 3D via Three.js (orbit/pan/zoom, wireframe,
  transparência, eixos, grade, plano de corte, screenshot, indicador de nível de detalhe).
- Worker C#/.NET 9 + PicoGK 2.2.0: **compila com sucesso** (`dotnet build`, 0 erros). Código
  matemático/de contrato independente de PicoGK (malha, métricas geométricas, exportador STL,
  contrato JSON) tem 9 testes xunit genuinamente executados e passando.

### O que está BLOQUEADO nesta sessão (com evidência, não suposição)

O pacote NuGet oficial `PicoGK` 2.2.0 só distribui o runtime nativo compilado (`picogk.26.2`)
para `win-x64` e `osx-arm64` — **não existe** `runtimes/linux-x64/native/` neste pacote,
confirmado tanto por inspeção do pacote restaurado quanto por execução real do binário
compilado, que produz `System.DllNotFoundException` reproduzida integralmente em
`apps/geometry-worker/WORKER_STATUS.md` e nos logs brutos `EVIDENCE_execution_attempt_std
{out,err}.log`. Ver ADR-0007 para a decisão e os caminhos de desbloqueio não tentados
(Windows/macOS, ou build nativo do PicoGK para linux-x64).

Consequências diretas do bloqueio:

1. Nenhum scaffold Gyroid real foi gerado nesta sessão — o STL usado no modo demo (GitHub
   Pages) é sintético, pré-calculado por script Python, e rotulado explicitamente como não
   sendo saída do PicoGK.
2. Determinismo geométrico real (mesma seed + mesma receita ⇒ mesmo STL) não pôde ser
   verificado — só o contrato de entrada é testável.
3. Geração de thumbnail e exportação VDB não puderam ser exercitadas (dependem de execução
   real).
4. O critério de aceite do Prompt Mestre para este incremento ("worker PicoGK executando de
   verdade", "geração do scaffold", "visualização do resultado real") **não está satisfeito**
   — apenas os itens que não dependem da execução real (schema, modelos, orquestração, API,
   frontend com dado sintético rotulado, testes) estão completos e verificados.
5. Por decisão explícita do Prompt Mestre, **a Fase 3 não deve começar** até esta vertical estar
   realmente executável — permanece como o item de maior prioridade do próximo incremento (ver
   `ROADMAP.md`).

### Testes desta sessão (resumo; ver `TEST_EVIDENCE.md` para o log bruto)

- Backend: 65 coletados (64 executados + 1 skip esperado quando `dotnet` não está no PATH),
  ruff e mypy limpos.
- Worker C#: `dotnet build` sem erros; 9/9 testes xunit passando (apenas código independente de
  PicoGK); execução real do binário reproduz o bloqueio esperado com evidência completa.
- Frontend: 17/17 testes Vitest, eslint e tsc limpos, `npm run build` e `npm run build:pages`
  ambos executados com sucesso, smoke HTTP do build de demo confirmado (200 no index e no STL
  sintético).

## Limitações do ambiente desta sessão

O sandbox de execução usado para desenvolver e testar este incremento **não tinha Docker nem
privilégios de root disponíveis**. Consequências diretas:

1. `docker-compose.yml` (Postgres/Redis/MinIO) foi validado apenas por parse de sintaxe YAML,
   nunca efetivamente executado com `docker compose up`. Isso é uma limitação do ambiente de
   desenvolvimento desta sessão, não uma afirmação de que o compose funciona — precisa ser
   validado por alguém com Docker.
2. Para testar a API contra um banco real sem Docker, foi usado
   [`pgserver`](https://pypi.org/project/pgserver/) (binários oficiais do PostgreSQL 16,
   redistribuídos como pacote Python, executáveis sem root). Isso permitiu testes de migração e
   conexão genuínos contra Postgres real — não é um mock nem SQLite disfarçado — mas o caminho
   de inicialização (`pg_ctl start` manual) é diferente do `docker-compose.yml` do repositório.
3. Processos em background não sobrevivem entre chamadas de shell distintas neste ambiente —
   por isso toda sequência start-Postgres → migrar → testar → seed → parar-Postgres precisou ser
   feita dentro de uma única invocação de shell corrida do início ao fim.
4. O workflow `deploy-pages.yml` foi escrito e validado apenas sintaticamente (YAML), nunca
   executado contra um repositório GitHub real — não há repositório remoto conectado a esta
   sessão.

## Backend — comandos executados e resultado (revalidação do Incremento 1.1)

Ambiente: `ENVIRONMENT=test`, banco `postgresql://postgres@127.0.0.1:5433/biomatcad` (dados/seed,
migrado do zero) e `.../biomatcad_test` (testes), servidor Postgres 16.2 iniciado via
`pgserver`/`pg_ctl` nesta sessão. Log bruto completo em `TEST_EVIDENCE.md`.

```text
$ ruff check .
All checks passed!

$ mypy src
Success: no issues found in 24 source files

$ alembic upgrade head   # banco 'biomatcad', vazio, do zero
INFO  Running upgrade  -> 927e185f097d, modelos iniciais: organizations, users, operational_states, audit_events
INFO  Running upgrade 927e185f097d -> 9242186001a8, adiciona expires_at em operational_states (suite clinica, incremento 1.1)

$ python -m biomatcad_api.seed
Seed sintético aplicado: organização='demo-biomatcad', usuário='demo@biomatcad.example' (researcher), admin='admin@biomatcad.example' (admin)

$ pytest -v   # banco 'biomatcad_test', criado do zero pela fixture
tests/test_auth_and_operational_state.py::test_login_rejects_wrong_password PASSED
tests/test_auth_and_operational_state.py::test_login_succeeds_and_returns_token PASSED
tests/test_auth_and_operational_state.py::test_logout_is_audited PASSED
tests/test_auth_and_operational_state.py::test_laboratory_activation_denied_without_master_key PASSED
tests/test_auth_and_operational_state.py::test_laboratory_activation_denied_for_non_admin PASSED
tests/test_auth_and_operational_state.py::test_laboratory_activation_succeeds_for_admin_with_correct_master_key PASSED
tests/test_auth_and_operational_state.py::test_clinical_kinds_rejected_on_independent_endpoint PASSED
tests/test_clinical_suite.py::test_initial_state_all_three_clinical_flags_disabled PASSED
tests/test_clinical_suite.py::test_activation_enables_all_three_flags_atomically PASSED
tests/test_clinical_suite.py::test_deactivation_disables_all_three_flags_atomically PASSED
tests/test_clinical_suite.py::test_activation_denied_for_non_admin_user PASSED
tests/test_clinical_suite.py::test_activation_rolls_back_completely_on_failure PASSED
tests/test_clinical_suite.py::test_clinical_suite_expiration_is_respected PASSED
tests/test_clinical_suite.py::test_clinical_suite_is_independent_from_laboratory PASSED
tests/test_db_connection.py::test_can_execute_simple_query PASSED
tests/test_dev_auth_startup.py::test_insecure_default_secret_is_rejected_outside_test_env PASSED
tests/test_dev_auth_startup.py::test_short_secret_is_rejected_outside_test_env PASSED
tests/test_dev_auth_startup.py::test_missing_secret_is_rejected_outside_test_env PASSED
tests/test_dev_auth_startup.py::test_real_secret_is_accepted_outside_test_env PASSED
tests/test_dev_auth_startup.py::test_insecure_default_is_tolerated_in_test_env PASSED
tests/test_health.py::test_health_ok PASSED
tests/test_health.py::test_ready_reports_database_connected PASSED
tests/test_health.py::test_version PASSED
tests/test_migrations.py::test_alembic_upgrade_head_runs_cleanly_on_empty_database PASSED
tests/test_system_status.py::test_system_status_defaults_only_research_enabled PASSED
======================== 25 passed, 1 warning in 14.98s ========================

$ python -c "... SELECT table_name FROM information_schema.tables ..."
['alembic_version', 'audit_events', 'operational_states', 'organizations', 'users']
```

### Os 7 cenários de teste da suíte clínica pedidos explicitamente pelo usuário

| # | Cenário pedido | Teste | Resultado |
|---|---|---|---|
| 1 | Worker PicoGK realmente executado em Windows x64 | **PROVADO para as 3 golden recipes, com o código de calibração corrigido** | Usuário reexecutou de verdade bloco/cilindro/preview contra o commit `da75219` (pós-correção): build Release aprovado, 62/62 xUnit aprovados. As 3 receitas dentro da tolerância MEDIDA. Ver `apps/geometry-worker/WORKER_STATUS.md` §10.4. |
| 2 | Geração real de bloco Gyroid | **APROVADO** | 208.560 triângulos, 102.338 vértices únicos, watertight, validação de recarga do STL aprovada, determinismo binário confirmado em duas execuções (mesmo SHA-256), auditoria independente aprovada. SHA-256: `cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d`. Porosidade dentro de margem pequena (erro -1,33 p.p., dentro da tolerância de 2,0pp agora definida para modo final). Bloco genuinamente gerado pelo PicoGK real, não sintético. |
| 3 | Cilindro realmente recortado (não bounding box) | **APROVADO** | Pós-correção: contenção radial/Z verificada (493.664 triângulos, 1.480.992 vértices examinados, raio máximo 4,999950394mm, intervalo Z [-6,+6]mm, ZERO violações radiais e em Z, `ContainmentExitCode=0`) — prova real de que o corte é pelo volume do cilindro, não bounding box. Porosidade agora dentro da tolerância: alvo 55%, medido 55,75526607688106%, erro +0,7552660768810568pp (tolerância 2pp), convergiu em 5 iterações de calibração por malha. SHA-256: `2cb8cbdf9acbff579c838d8bf3cc2e2a688bcd33a3c475945174272cb278445e`. Auditoria independente aprovada, determinismo confirmado (Run1=Run2). Nota: a checagem de contenção radial/Z específica não foi gerada pela ferramenta `scripts/audit_stl_vs_worker_output.py` deste repositório — ver ressalva em `WORKER_STATUS.md` §10.4. |
| 4 | Diferença real preview vs. final | **APROVADO** | Pós-correção: `preview-gyroid-low-res-v1` executado de verdade com porosidade agora dentro da tolerância de modo preview: alvo 60%, medido 56,733228138231375%, erro -3,2667718617686248pp (tolerância 5pp), convergiu em 4 iterações de calibração por malha. SHA-256: `7660dae3ee263445835bbf9d26c16fa4ef8f8ee2fd2c320000b0546c1eaaba78`. Auditoria independente aprovada, watertight, determinismo confirmado. Prova real da diferença de tolerância por modo (2pp final vs. 5pp preview) e da correção do bug de calibração enganosa encontrado nesta sessão. |
| 5 | Parâmetros efetivamente aplicados (espessura/isovalor/porosidade/seed) | **APROVADO — porosidade PROVADA de verdade para as 3 receitas, pós-correção** | Calibração fechada (`GyroidMath.CalibrateByMonotonicBisection`) confirmada contra a malha real do PicoGK: bloco (1 iteração, erro -1,33pp), cilindro (5 iterações, erro +0,76pp), preview (4 iterações, erro -3,27pp) — todas dentro da tolerância medida por modo. Determinismo confirmado nas 3 receitas (Run1=Run2, `DeterminismoGlobal=True`). Espessura efetiva/isovalor/fase-por-seed continuam sem confirmação ISOLADA contra a malha real (dependeria de reprocessar o STL e comparar campo a campo contra os parâmetros efetivos reportados) — mas o resultado agregado (porosidade medida dentro da tolerância) já prova que a cadeia completa (espessura→banda→SDF→voxelização→malha) funciona corretamente de ponta a ponta. |
| 6 | Limites computacionais efetivamente controlados | Código corrigido, parcialmente verificado nesta sessão; laço de calibração também respeita os limites | Estimativa prévia de voxel/memória testada unitariamente; timeout + kill de árvore de processos **verificado neste sandbox** (cross-platform). Três bugs operacionais reais encontrados e corrigidos ao longo desta sessão via execução real: (1) limpeza de artefatos parciais apagava `job.json` de entrada — corrigido (`OutputCleanup.cs`); (2) viewer do PicoGK não fechava sozinho, inflando `duration_seconds` — corrigido (`bEndAppWithTask: true`); (3) calibração de porosidade cientificamente enganosa (item 5) — corrigida (calibração fechada). O novo laço de calibração fechada descarta Voxels/Mesh de cada candidato via `using`/`Dispose()` entre iterações, respeitando o mesmo limite de memória. Efeitos reais das correções (2) e (3) ainda dependem de nova execução do usuário para confirmação final. |
| 7 | Independência do contexto Laboratório | `test_clinical_suite_is_independent_from_laboratory` | PASSED |

## Frontend — comandos executados e resultado (revalidação do Incremento 1.1)

```text
$ npm run typecheck        # tsc --noEmit
(sem erros)

$ npm run lint              # eslint . --max-warnings=0
(sem erros)

$ npx vitest run
✓ tests/Login.test.tsx (2 tests)
✓ tests/ClinicalSuiteIndicator.test.tsx (1 test)
✓ tests/Dashboard.test.tsx (1 test)
✓ tests/apiClient.test.ts (2 tests)
✓ tests/Landing.test.tsx (1 test)
Test Files  5 passed (5) | Tests  7 passed (7)

$ npm run build              # build de produção (base "/")
dist/assets/index-*.js   181.59 kB │ gzip: 59.09 kB
✓ built in 1.88s

$ npm run build:pages        # build de demonstração (base "/biomatcad-nexus/")
dist/assets/index-*.js   181.96 kB │ gzip: 59.22 kB
✓ built in 5.94s

$ npx vite preview --port 4173 --strictPort &
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:4173/biomatcad-nexus/
200
# <title>BioMatCAD Nexus</title> confirmado no HTML servido
```

### O que os testes de frontend cobrem (e o que não cobrem)

- **Cobrem**: renderização da Landing, formulário de login, indicador de suíte clínica x
  laboratório (separados — regressão específica do bug do Incremento 1), smoke test do
  Dashboard, cliente de API (sucesso e erro tipado).
- **Não cobrem**: fluxo E2E real de navegador (Playwright) — não configurado neste incremento.
  Os testes acima são testes de componente (Vitest + Testing Library + jsdom), não testes de
  navegador real. O smoke test é feito no nível de componente mais uma verificação HTTP real do
  build servido (`vite preview` + `curl`) — lacuna conhecida, não alegação de cobertura E2E.

## Contrato da chave mestra — semântica corrigida (Incremento 1.1)

**Dois grupos independentes, nunca confundidos:**

- **Contextos independentes**: `research` (habilitado por padrão) e `laboratory` (desabilitado
  por padrão) — cada um ativável isoladamente via `POST /api/v1/system/operational-state/activate`,
  exigindo admin + `OPERATIONAL_STATE_MASTER_KEY`.
- **Suíte clínica**: `clinical_test`, `clinical_pilot`, `clinical_production` — controlados
  **sempre em conjunto**, nunca individualmente. `POST /operational-state/activate` **rejeita**
  (400) qualquer tentativa de ativar um desses três isoladamente. Só é possível ativá-los/
  desativá-los via `POST /api/v1/system/clinical-suite/activate` e `.../deactivate`.

**Garantias da ativação/desativação da suíte clínica:**

- Transação única no banco — os três estados mudam juntos ou nenhum muda (testado com falha
  induzida por monkeypatch).
- Mesma chave mestra do sistema (`OPERATIONAL_STATE_MASTER_KEY`) — nunca uma segunda chave.
- Exige usuário com papel administrativo (`require_admin`); tentativa negada gera
  `AuditEvent(event_type="admin_action_denied")`.
- Registra estado anterior, estado novo, justificativa e identidade do administrador em
  `AuditEvent`.
- Suporta expiração opcional (`expires_at`), avaliada em tempo de leitura
  (`OperationalState.is_effectively_enabled`), sem exigir job de expiração em background.
- Reflete imediatamente no cartão de login e no dashboard (`ClinicalSuiteIndicator`,
  `DashboardPage`), que agora mostram Laboratório e suíte clínica como linhas separadas.

**Não implementado (backlog, `PM-ONLY-04`, ver `REQUIREMENTS_MATRIX.md` seção D):** rotação de
chave mestra, expiração da própria chave, segregação de chave por instituição/unidade, "break
glass" com prazo e revogação automática, qualquer UI de administração para essa ativação (hoje só
existe a chamada de API).

## Autenticação — classificação `DEV_AUTH` (Incremento 1.1, ADR-0005)

A autenticação atual (e-mail/senha com bcrypt, JWT stateless de 30 min, sessão em memória no
frontend) é explicitamente nomeada **`DEV_AUTH`** — exposta em
`GET /api/v1/system/status.auth_mode` e no cartão de login. Isso é uma classificação de
transparência, não uma alteração de comportamento: o mecanismo de login em si não mudou, o que
mudou é que agora ele nunca pode ser confundido com uma solução pronta para uso clínico real.

- **Nunca deve ser usado com dados clínicos reais**, independentemente do estado da suíte
  clínica — isso é uma limitação da camada de identidade, ortogonal ao estado operacional (ativar
  a suíte clínica tecnicamente NÃO torna a autenticação apta a dados clínicos reais).
- `Settings.assert_secure_for_environment()` faz o processo recusar iniciar
  (`InsecureConfigurationError`) sempre que `ENVIRONMENT != test` e `API_SECRET_KEY` estiver
  ausente, vazio, igual ao valor padrão de desenvolvimento, ou mais curto que 32 caracteres —
  testado em `test_dev_auth_startup.py` (5 testes).
- `POST /api/v1/auth/logout` é **simbólico**: como o JWT é stateless e não há blocklist nesta
  fase, o token continua criptograficamente válido até expirar; o endpoint apenas registra o
  evento de auditoria e o frontend descarta o token em memória. Isso não é revogação real de
  sessão.
- Pendências rastreadas em `PM-ONLY-04a`–`04h`: OIDC/OAuth 2.1+PKCE, MFA/WebAuthn, step-up
  authentication, refresh token, blocklist de sessão, painel de sessões ativas, RBAC/ABAC
  completo com os 17 perfis do Prompt Mestre §9, "break glass" auditado.

## Preservação do histórico Git

O repositório tem 13 commits organizados por incremento/preocupação (ver `git log --oneline`).
Para preservar esse histórico fora do sandbox de execução (que é efêmero):

```bash
git bundle create biomatcad-nexus-v2.1.bundle --all
git bundle verify biomatcad-nexus-v2.1.bundle
```

Restauração em qualquer máquina com Git:

```bash
git clone biomatcad-nexus-v2.1.bundle biomatcad-nexus
cd biomatcad-nexus
git log --oneline   # os 13 commits originais, com autoria e datas preservadas
```

O bundle preserva histórico completo (branches, tags, todos os commits) — diferente do
`biomatcad-nexus-scaffold-v2.1.zip`, que é uma foto (snapshot) de um único commit via
`git archive`, sem histórico.

## Incremento 2.3 (Rodada 1) — Fundação Canônica, Proveniência e Curadoria (branch `incremento-2.3-dados-cientificos`)

A partir do commit `e10d23d` (README modernizado registrando o encerramento formal do
Incremento 2.2 e o início do Incremento 2.3), esta rodada implementou a fundação persistente do
banco de dados científico — sem nenhuma coleta de dados externa nem importação em massa.

- **Fase A (auditoria)**: mapeamento do modelo `MaterialRecord` existente, dos dois pontos
  reais de dependência (`GeometryJob.material_id`, `manifest_service.py`), do mecanismo de
  autenticação/autorização (`get_current_user`/`require_admin`), e do padrão de seed idempotente
  (`_ensure_user` em `seed.py`) — todos reaproveitados sem reinvenção.
- **Fase B (modelo de domínio)**: 12 novas entidades em
  `apps/api/src/biomatcad_api/models/scientific_data.py` — ver `docs/data/SCIENTIFIC_DATA_MODEL.md`
  para o contrato completo.
- **Fase C (migração)**: `alembic/versions/4920cd8fd160_...py`, verificada em três cenários
  reais contra PostgreSQL (nunca SQLite): banco vazio, banco já populado (preserva
  `MaterialRecord` existente, `scientific_entity_id` fica `NULL`), e downgrade completo.
- **Fase D (API mínima)**: `routers/scientific_data.py`, prefixo `/api/v1/scientific-entities`
  — 8 endpoints (listagem/detalhe + 6 sub-rotas de leitura relacionada + criação de entidade +
  criação de decisão de revisão), com escopo de organização e autorização admin-only para
  escrita/revisão.
- **Fase E (seed sintético)**: `python -m biomatcad_api.seed_scientific_data` (idempotente) —
  5 entidades canônicas, observações conflitantes de fontes distintas, 1 fornecedor+produto
  fictício, 1 referência bibliográfica fictícia, 1 estrutura cristalográfica sintética, 1
  execução de ingestão fictícia, estados draft/reviewed/rejected. Nenhum identificador real
  (DOI/PMID/CAS/CID/accession) em nenhum lugar do seed.
- **Fase F (testes)**: 14 testes de domínio (`tests/test_scientific_data_domain.py`) + 8 testes
  de API (`tests/test_scientific_data_api.py`) + 1 novo teste de migração real
  (`test_scientific_data_migration_preserves_populated_materials_and_downgrade_is_reversible`,
  gated por `PG_ADMIN_URL`, já presente no CI). Suíte completa: **281 passed, 3 skipped** (sem
  nenhuma regressão dos 259 testes pré-existentes do Incremento 2.1/2.2).
- **Fase G (documentação)**: `docs/data/SCIENTIFIC_DATA_MODEL.md`,
  `docs/data/PROVENANCE_AND_CURATION.md`, `docs/data/SOURCE_REGISTRY_POLICY.md`,
  `docs/data/LICENSING_AND_REDISTRIBUTION.md`, além desta seção e das atualizações em
  `ARCHITECTURE.md`/`REQUIREMENTS_MATRIX.md`/`ROADMAP.md`/`TEST_EVIDENCE.md`.

**O que foi deliberadamente deixado para uma rodada futura** (nunca implementado nesta rodada):
qualquer conector de ingestão real contra bases externas (PubChem, ChEBI, ChEMBL, Crossref,
Europe PMC/PubMed, Crystallography Open Database, RCSB PDB, fornecedores comerciais); backfill
de `MaterialRecord.scientific_entity_id` para registros existentes; interface administrativa
extensa de curadoria (a API desta rodada é deliberadamente mínima); criação via API de
observação/identificador/fonte/referência/fornecedor/produto/estrutura cristalográfica (só via
seed nesta rodada); qualquer dado clínico ou de paciente real. **O Incremento 2.3 não é
declarado completo por esta rodada** — esta é apenas a Rodada 1 (fundação).

## Incremento 2.3 (Rodada 2) — Infraestrutura de Ingestão e Conector PubChem Piloto (branch `incremento-2.3-dados-cientificos`, WIP)

Construída sobre a Rodada 1 (fundação canônica acima), esta rodada implementou o primeiro
conector real de ingestão externa (PubChem PUG REST) e a infraestrutura comum de conectores
que qualquer fonte futura (ChEBI, ChEMBL, Crossref, etc.) reaproveitará. Ver
`docs/data/connectors/PUBCHEM_CONNECTOR.md` para o contrato completo e
`docs/data/connectors/PUBCHEM_MUTATION_TESTING.md` para o registro do exercício de mutation
testing manual.

- **Fases B-C (contrato + registro bruto)**: `services/connectors/base.py` (contrato comum
  `ScientificDataConnector`: validate_request → fetch → normalize → reconcile → persist,
  aplicado a qualquer conector futuro), `models/scientific_ingestion.py` (3 tabelas novas,
  aditivas: `raw_source_records`, `scientific_ingestion_requests`, `ingestion_conflicts`, mais
  1 coluna nullable em `property_observations`), migração `511279411501` (revisão anterior:
  `4920cd8fd160`, a da Rodada 1 — downgrade remove só o que esta rodada acrescentou).
- **Fase E (cliente HTTP seguro)**: `services/connectors/http_client.py::AllowlistedHttpsClient`
  — allowlist de host, TLS sempre verificado, sem redirecionamento automático, rate limit
  (máx. 4/s), retry/backoff só para falhas transitórias, limite de tamanho de resposta.
- **Fase D (fila + dispatcher)**: `scripts/scientific_ingestion_dispatcher.py`, processo
  independente do dispatcher geométrico, mesmo padrão de claim atômico
  (`SELECT ... FOR UPDATE SKIP LOCKED`) provado livre de dupla reivindicação por
  `tests/test_scientific_ingestion_concurrency.py`.
- **Fase F (conector PubChem)**: `services/connectors/pubchem.py` — mapeamento de propriedades
  documentadas do PUG REST (peso molecular, fórmula, SMILES, InChI/InChIKey), CID como
  identificador primário único de reconciliação.
- **Fase G (reconciliação)**: identidade de entidade decidida somente por CID; colisão de
  InChIKey com entidade diferente nunca fundida automaticamente (`IngestionConflict`); entidade
  nova sempre `CurationState.DRAFT`, nunca promovida a `REVIEWED` automaticamente.
- **Fases G-H (operação)**: API administrativa `/api/v1/scientific-ingestion` (7 endpoints,
  todos `require_admin`, sem busca livre nem importação em massa — máximo 10 CIDs por
  solicitação) + CLI `scripts/pubchem_ingest_cli.py`.
- **Fase I (piloto Windows real)**: `scripts/Run-PubChemPilotWindows.ps1` — único meio capaz
  de provar o conector contra a rede oficial do PubChem, pois o sandbox de desenvolvimento
  bloqueia `pubchem.ncbi.nlm.nih.gov` na camada TLS (`SSL: WRONG_VERSION_NUMBER`, confirmado
  repetidamente via `curl` e via o próprio `AllowlistedHttpsClient` de produção — nunca uma
  falha do PubChem ou do conector). **Execução real no Windows do usuário ainda pendente** —
  ver seção de bloqueio de rede em `docs/data/connectors/PUBCHEM_CONNECTOR.md`.
- **Fase J (testes + mutation testing)**: 90 testes novos específicos deste conector
  (`test_pubchem_connector.py`: 21, `test_pubchem_http_client.py`: 18,
  `test_pubchem_ingest_cli.py`: 7, `test_scientific_ingestion_api.py`: 14,
  `test_scientific_ingestion_concurrency.py`: 1, `test_scientific_ingestion_service.py`: 29),
  todos rodando contra PostgreSQL real, nenhum dependente de rede (payloads via
  `synthetic_contract_fixture`, rotulados como tal no código). 7 mutações manuais aplicadas
  (allowlist de host, autorização, dry-run, atomicidade do claim, idempotência de
  `RawSourceRecord`, registro de conflito de InChIKey, não-promoção a `REVIEWED`) — todas as 7
  mataram pelo menos um teste dedicado e foram revertidas; ver
  `docs/data/connectors/PUBCHEM_MUTATION_TESTING.md` para o registro literal, incluindo a
  nuance da mutação de idempotência não detectada pelo teste pré-existente de contadores
  agregados. Suíte completa do backend re-verificada após os reverts: 363 passed, 3 skipped
  (excluindo `test_e2e_seed_fixture.py`, que exige >175s e já era verificado separadamente).
  `ruff`/`mypy` limpos.
- **Fase K (documentação)**: `docs/data/connectors/PUBCHEM_CONNECTOR.md`,
  `docs/data/connectors/PUBCHEM_MUTATION_TESTING.md`, esta seção.

**Nenhum dado real do PubChem foi obtido nesta rodada** — o bloqueio de rede do sandbox impediu
qualquer chamada real. Todo o piloto foi validado por teste de contrato sintético (formato
documentado da API, valores químicos publicamente conhecidos, nunca capturados ao vivo). **A
Rodada 2 não é declarada cientificamente aprovada** até que `Run-PubChemPilotWindows.ps1` seja
executado com sucesso em uma máquina Windows real, com evidência literal de: (1) resposta
oficial confirmando o CID solicitado; (2) hash SHA-256 do payload preservado; (3) idempotência
real provada por duas submissões da mesma lista de CIDs produzindo o mesmo hash e nenhuma nova
versão de `RawSourceRecord` na segunda vez.

### Adendo de Interface Científica Mínima (Fases L-T, mesma Rodada 2, branch `incremento-2.3-dados-cientificos`)

Após a entrega inicial das Fases A-K acima, foi identificado que a lacuna "Adendo de Interface
Científica Mínima" — explicitamente parte do escopo da Rodada 2 — não tinha sido implementada:
até então, o Incremento 2.3 só era observável via API/CLI/testes, sem nenhuma tela real para um
usuário autenticado visualizar entidades científicas, propriedades/proveniência, conflitos, ou
operar o piloto PubChem. Este adendo fecha essa lacuna, sem alterar nada do backend "já
concluído" das Fases A-K além de duas extensões aditivas mínimas (ver Fase L).

- **Fase L (auditoria)**: mapeamento objetivo do que já existia (rotas de leitura da Rodada 1,
  rotas de ingestão da Rodada 2, `apiClient`/`demoClient`, `Sidebar`, componentes de
  tabela/badge/alerta/vazio/carregamento reutilizáveis, padrão de teste Vitest com
  login real via `AuthContext` + `fetch` mockado) e do que faltava. Only 2 extensões aditivas
  foram necessárias no backend, ambas cobertas por teste e adicionadas **antes** de qualquer
  rota estática colidir com `/{entity_id}`:
  - `GET /api/v1/scientific-entities/property-definitions` (vocabulário canônico de
    propriedades, qualquer usuário autenticado).
  - `GET /api/v1/scientific-entities/sources` (lista de `ScientificSource`, usada para o
    seletor de fonte do painel de ingestão).
  - `GET /api/v1/scientific-entities/{entity_id}/biological-evidence`,
    `.../raw-source-records`, `.../conflicts` (sub-recursos por entidade, reaproveitando
    exatamente os modelos e o padrão de autorização já existentes).
  Nenhuma rota, schema, migração ou regra de autorização das Fases A-K foi redesenhada.
- **Fase M (listagem)**: nova página `apps/web/src/pages/ScientificDataPage.tsx`, rota
  `/app/scientific-data` (ver nota de nomenclatura abaixo), item "Dados científicos" no
  `Sidebar`. Mostra nome preferido, tipo, CID PubChem (quando presente), InChIKey (quando
  presente), massa molecular (quando presente), visibilidade global/organizacional, badge de
  estado de revisão, data de criação; busca por nome e filtros por tipo/estado de revisão;
  estados de carregamento/vazio/erro explícitos; painel administrativo de ingestão PubChem
  (ver Fase O) somente para `role in {admin, superadmin}`.
- **Fase N (detalhe)**: nova página `apps/web/src/pages/ScientificEntityDetailPage.tsx`, rota
  `/app/scientific-data/:entityId`, 11 abas: visão geral, identificadores, propriedades,
  proveniência, snapshots, referências, evidências biológicas, produtos de fornecedor,
  estruturas cristalográficas, conflitos, histórico de revisão. Cada propriedade mostra nome,
  valor/unidade original, valor normalizado, condições, método, incerteza, tipo de evidência
  (rótulo literal — "calculado" nunca é escrito nem lido como "validado", ver
  `ScientificBadges.tsx::EVIDENCE_TYPE_LABEL`) e estado de revisão. A aba "Snapshots" expõe o
  `RawSourceRecord` (conector, identificador externo, data de obtenção, SHA-256 truncado,
  versão anterior) sem nunca mostrar o payload bruto completo.
- **Fase O (painel PubChem)**: `apps/web/src/components/scientific/PubChemIngestionPanel.tsx`
  — lista explícita de CIDs (validação local: só dígitos, máximo 10), botões Dry-run/Submeter/
  Cancelar, status com Correlation ID e contadores (recebidos/criados/atualizados/inalterados/
  rejeitados/conflitos), polling controlado (2s, encerrado explicitamente ao desmontar o
  componente — nunca um intervalo órfão), conflitos detectados exibidos inline. Nunca busca por
  nome, nunca importação em massa. Usuário `researcher` nunca vê este painel (gate por
  `role` no `ScientificDataPage`) e recebe 403 real da API se tentar chamar o endpoint
  diretamente (comportamento do backend da Rodada 2, inalterado).
- **Fase P (avisos)**: `apps/web/src/components/scientific/ScientificDisclaimers.tsx` — três
  avisos, sempre visíveis (nunca condicionais em nenhum caminho de sucesso): uso exclusivamente
  para pesquisa; fonte externa importada exige curadoria; dado sintético de demonstração nunca
  atribuído ao PubChem. Nenhuma linguagem de recomendação clínica/farmacêutica em lugar algum.
- **Fase Q (testes de componente)**: 31 novos testes Vitest (`tests/ScientificDataPage.test.tsx`
  12, `tests/ScientificEntityDetailPage.test.tsx` 9, `tests/PubChemIngestionPanel.test.tsx` 9),
  cobrindo navegação, listagem (carregamento/vazio/erro/filtros), campo ausente vs. valor real
  zero (nunca confundidos), rótulo "calculado" (nunca "validado"), avisos de origem
  PubChem/sintética, conflito visível, proveniência, painel ausente para pesquisador/presente
  para admin, validação de CID (máximo 10, rejeição de não-numérico), dry-run, submissão,
  progressão de polling controlada (via substituição direcionada de `setInterval`/
  `clearInterval` por valor de delay — nunca interferindo no polling interno do próprio
  Testing Library), cancelamento, encerramento do polling ao desmontar, erros 403/429/503
  sempre exibidos. **Total da suíte Vitest: 159 (128 preexistentes + 31 novos), 0 regressões.**
  `tsc --noEmit`, `eslint --max-warnings 0`, `npm run build` e `npm run build:pages` limpos.
- **Fase R (E2E)**: `apps/web/e2e/scientific-data.spec.ts` (9 testes, cobrindo os 12 cenários
  pedidos), usando exclusivamente o seed sintético (`python -m biomatcad_api.seed` +
  `biomatcad_api.seed_scientific_data`, ambos adicionados ao `globalSetup` do Playwright em
  `apps/web/e2e/global-setup.ts`), Postgres e API reais, nenhuma chamada ao PubChem real. Os
  cenários de dry-run/submissão/cancelamento criam uma `ScientificIngestionRequest` real no
  banco via a API real, mas como nenhum dispatcher de ingestão é iniciado nesta suíte, a
  solicitação nunca é processada — permanece `queued` (estado real, nunca fabricado) até ser
  cancelada pelo próprio teste, provando exatamente o contrato observável sem tocar a rede
  externa. Roteiro Windows independente `scripts/Run-ScientificDataE2EOnly.ps1` (PowerShell 7,
  `-RepoPath` absoluto obrigatório, prepara migrações via `alembic upgrade head`, inicia
  somente a API rastreada por PID, delega o seed sintético/científico e o frontend ao próprio
  `globalSetup`/`webServer` do Playwright, roda **exclusivamente**
  `npx playwright test e2e/scientific-data.spec.ts` — nunca repete `vertical.spec.ts`/
  `viewer.spec.ts` nem a matriz geométrica —, encerra somente o processo da API que ele mesmo
  iniciou, nunca chama o PubChem real, nunca depende do PicoGK). Validado neste sandbox via:
  `npx playwright test --list` (24 testes totais, 9 do novo spec, listados corretamente);
  cadeia completa de seed (migrações + 3 scripts, 2 execuções) rodada 2x contra Postgres real
  com contagens estáveis (idempotência confirmada); contrato completo da API exercido
  diretamente (login researcher/admin, listagem de entidades, conflito visível dos dois lados
  do relacionamento, dry-run/submissão/cancelamento, 403 real para pesquisador) — tudo com
  resultado esperado. **A execução real do Chromium em si permanece pendente no Windows do
  usuário**, pelo mesmo bloqueio de infraestrutura (bibliotecas nativas do Chromium ausentes,
  sem acesso root) já documentado para `vertical.spec.ts`/`viewer.spec.ts` desde incrementos
  anteriores — não uma limitação nova nem específica desta interface.
- **Fase S (verificação)**: frontend (`tsc --noEmit`, `eslint --max-warnings 0`, `vitest run`
  159/159, `npm run build`, `npm run build:pages`, `playwright test --list`) e backend (`ruff
  check`, `mypy`, suíte completa `pytest` contra PostgreSQL real: **376 testes, 373 passed + 3
  skipped, 0 falhas**, rodada em 7 lotes por limite de tempo do sandbox, nunca a suíte inteira
  de uma vez) — todos limpos. Worker C#/PicoGK: nenhum arquivo `.cs` alterado nesta rodada;
  `dotnet` não está disponível neste sandbox (ambiente resetado) — suíte do worker não pôde ser
  reexecutada aqui, documentado literalmente em vez de presumido aprovado. Roteiro PowerShell
  novo (`Run-ScientificDataE2EOnly.ps1`) validado via
  `[System.Management.Automation.Language.Parser]::ParseFile` (0 erros de sintaxe).
- **Fase T (documentação)**: esta seção, `docs/data/connectors/PUBCHEM_CONNECTOR.md`
  (referência à interface administrativa), `docs/data/INGESTION_OPERATIONS.md` (novo),
  `REQUIREMENTS_MATRIX.md`, `ROADMAP.md`, `TEST_EVIDENCE.md`, `README.md`,
  `apps/web/e2e/README.md`.

**Nota de nomenclatura (decisão consciente, não um desvio silencioso)**: as instruções desta
rodada pediam literalmente a rota `/scientific-data`. Todas as demais páginas autenticadas do
produto (materiais, projetos, jobs, observabilidade) usam o prefixo `/app/` (roteador protegido
por `ProtectedRoute` + `AuthenticatedLayout`) — por isso as rotas reais são
`/app/scientific-data` e `/app/scientific-data/:entityId`, preservando a arquitetura de rotas já
estabelecida em vez de introduzir uma exceção inconsistente. O item de navegação no `Sidebar`
("Dados científicos") aponta para o caminho real.

**Lacunas conhecidas e deliberadamente não resolvidas nesta rodada** (documentadas em vez de
fabricadas ou escondidas): (1) a listagem não tem paginação de servidor — aceitável dado o
tamanho pequeno do seed sintético atual, mas precisará de extensão se o volume real crescer;
(2) a coluna "Fórmula molecular" não aparece na listagem — o conector PubChem calcula fórmula/
SMILES/InChI em `normalize()`, mas `reconcile()`/`persist()` (Rodada 2, já concluída) só
persistem o InChIKey como `ScientificIdentifier`; expandir o `persist()` para reter
fórmula/SMILES/InChI foi deliberadamente deixado de fora deste adendo por ser uma mudança no
backend "já concluído" da Rodada 2, fora do escopo de uma interface mínima — backlog explícito
para uma rodada futura, não uma omissão silenciosa.

## Como executar hoje

Ver `README.md` (seção atualizada) para os comandos completos de backend e frontend, incluindo
variáveis novas (`AUTH_MODE`, `OPERATIONAL_STATE_MASTER_KEY`).

```bash
# Backend (requer PostgreSQL real acessível via DATABASE_URL)
cd apps/api
pip install -e ".[dev]"
alembic upgrade head
python -m biomatcad_api.seed
python -m biomatcad_api.seed_scientific_data  # opcional: dados científicos sintéticos (Incremento 2.3)
uvicorn biomatcad_api.main:app --reload

# Frontend
cd apps/web
npm install
npm run dev
```

O `docker-compose.yml` (Postgres/Redis/MinIO) deveria simplificar isso, mas não foi validado em
execução nesta sessão — ver "Limitações do ambiente" acima.
