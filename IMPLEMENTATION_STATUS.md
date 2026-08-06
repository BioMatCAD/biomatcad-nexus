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

## Como executar hoje

Ver `README.md` (seção atualizada) para os comandos completos de backend e frontend, incluindo
variáveis novas (`AUTH_MODE`, `OPERATIONAL_STATE_MASTER_KEY`).

```bash
# Backend (requer PostgreSQL real acessível via DATABASE_URL)
cd apps/api
pip install -e ".[dev]"
alembic upgrade head
python -m biomatcad_api.seed
uvicorn biomatcad_api.main:app --reload

# Frontend
cd apps/web
npm install
npm run dev
```

O `docker-compose.yml` (Postgres/Redis/MinIO) deveria simplificar isso, mas não foi validado em
execução nesta sessão — ver "Limitações do ambiente" acima.
