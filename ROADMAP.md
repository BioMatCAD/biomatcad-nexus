# Roadmap — BioMatCAD Nexus

Este roadmap reflete o estado real após o Incremento 2.1 (Fase 2, entregue parcialmente
bloqueado) e o Incremento 2.1.1 (corretivo sobre defeitos da auditoria do 2.1, também entregue
parcialmente bloqueado no mesmo ponto — ver `IMPLEMENTATION_STATUS.md`, ADR-0007 e ADR-0008).
Não é uma promessa de prazos; é uma priorização técnica, atualizada a cada incremento aceito.
Ver `REQUIREMENTS_MATRIX.md` para o mapeamento completo de requisitos e `docs/adr/` para as
decisões que o sustentam. Atualizado em 2026-08-06 com a rodada Voronoi do
Incremento 2.2 (segunda topologia real, `voronoi_cell_edges_v1`) — ver seção dedicada abaixo.
Atualizado novamente em 2026-08-06 (rodada Windows real `voronoi-validation-staged-
20260806-195638`): a matriz Voronoi/Gyroid (6 golden recipes, 2x cada) foi APROVADA no Windows
real do usuário, com worker PicoGK genuíno, determinismo byte a byte, auditoria independente e
zero processos órfãos -- ver seção dedicada abaixo e `TEST_EVIDENCE.md` seção 23.

## Feito

- **Fase 1 (Incrementos 1 e 1.1)**: fundação executável — auth `DEV_AUTH`, estado operacional
  (Pesquisa/Laboratório/suíte clínica), modelos iniciais, frontend com landing/login/dashboard,
  histórico Git preservado em bundle.
- **Fase 2 (Incremento 2.1)**: primeira vertical funcional do núcleo BioMatCAD — material
  documentado → projeto → receita BioMatCEM → job geométrico → worker C#/PicoGK → scaffold
  Gyroid → métricas → artefatos → visualização 3D. **Parcialmente bloqueado**: o worker
  compila e tem seu contrato testado, mas a execução real do PicoGK está bloqueada neste
  sandbox (ausência de runtime nativo linux-x64 no pacote oficial 2.2.0 — ver ADR-0007).
- **Fase 2 (Incremento 2.1.1, corretivo)**: corrigidos defeitos encontrados em auditoria do
  2.1 — semântica espessura/isovalor do schema (ADR-0008), domínio cilíndrico recortado pelo
  volume real via SDF (não bounding box), espessura/isovalor/porosidade/seed efetivamente
  aplicados, solda de vértices na malha (corrigindo a divergência STL-vs-manifesto encontrada na
  auditoria), autorização real entre organizações antes de criar um `DesignRun`, fila com claim
  atômico (`SELECT ... FOR UPDATE SKIP LOCKED`, provado sem duplicidade em 24 jobs concorrentes
  reais), cancelamento real com kill de árvore de processos e proteção de corrida, manifesto
  reestruturado com SHA-256 fora do próprio JSON, validação de receita no frontend migrada para
  Ajv contra o schema real, fingerprint de demonstração corrigido. **Mesmo bloqueio de execução
  real do PicoGK** desta sessão continua valendo — nenhuma dessas correções foi provada contra
  uma malha PicoGK real ainda (ver `IMPLEMENTATION_STATUS.md`).
- **Fase 2 (Incremento 2.2 Alpha Pesquisa, em andamento)**: observabilidade real integrada à
  GUI; GUI completa de pesquisa (retry, seleção de material, aviso de proveniência); contrato
  `TopologyProvider` versionado (Gyroid real, Voronoi registrado como `planned`, ADR-0009);
  documentação de preparação técnica para Voronoi (sem código); módulo de inteligência
  computacional (apenas contratos + registro de decisão manual, sem IA autônoma real);
  identidade visual oficial integrada (logo, favicon, PWA, página Sobre); visualizador 3D
  consolidado com STL real (checklist completo de recursos, carregamento seguro com checksum,
  controles de visualização, métricas/proveniência, limites de desempenho e descarte de
  recursos WebGL, suíte de testes de componente e correção de 4 bugs reais encontrados durante
  a auditoria/testes -- ver `docs/architecture/viewer-3d-audit.md` e a seção dedicada em
  `IMPLEMENTATION_STATUS.md`). Launcher Windows permanece formalmente **deferido** (não
  retomado).
- **Fase 2 (Incremento 2.2, rodada Voronoi)**: segunda topologia real implementada
  (`voronoi_cell_edges_v1`) -- sítios determinísticos por seed, tesselação Voronoi 3D real via
  `MIConvexHull` (não Delaunay renomeado), grafo de arestas recortado pelo domínio via SDF real,
  struts implícitos com suavização de nós, calibração de porosidade sobre malha real, métricas
  específicas completas, `VoronoiTopologyProvider` registrado (`status="implemented"`, sem
  regressão no Gyroid), 3 golden recipes, frontend completo (editor, estimativa de custo, aviso
  de receita pesada, demo honesto sem fabricar sucesso), auditoria STL independente escrita do
  zero, caderno de invenção confidencial, roteiro único de validação Windows -- ver
  `IMPLEMENTATION_STATUS.md` (seção "Rodada Voronoi") e `TEST_EVIDENCE.md` (seção 19).
  **CONFIRMADO na rodada Windows real `voronoi-validation-staged-20260806-195638`**: as 6
  golden recipes (3 Voronoi + 3 Gyroid de regressão) rodaram 2x cada com o worker PicoGK real,
  todas com `queued -> running -> succeeded`, cinco fontes de SHA-256 coerentes, determinismo
  byte a byte entre execuções, watertight (worker + auditoria independente), zero arestas
  non-manifold, contenção de domínio aprovada e nenhum processo `dotnet.exe` órfão -- ver
  `TEST_EVIDENCE.md` seção 23 para os hashes literais. A investigação e correção do deadlock
  real de pipes stdout/stderr em `DotnetPicoGkWorkerClient` (causa raiz do `WORKER_TIMEOUT`
  historicamente relatado -- nunca foi um defeito do algoritmo Voronoi/PicoGK) também foi
  comprovada nesta mesma execução real. O E2E Playwright DESSA execução específica ficou
  inconclusivo por um defeito de infraestrutura do próprio roteiro (frontend nunca iniciado
  antes do Playwright, `net::ERR_CONNECTION_REFUSED`) -- esse registro histórico permanece
  como aconteceu, não foi apagado nem reescrito. A correção (Playwright `webServer` nativo) foi
  aplicada e **CONFIRMADA em uma reexecução real separada e posterior** no mesmo Windows
  (`Run-E2EOnly.ps1`, commit `84f46fc`): 2/2 testes aprovados, `E2EExitCode=0`, sem processos
  órfãos -- ver `TEST_EVIDENCE.md` seção 24. **Com isto, tanto a matriz Voronoi/Gyroid (12
  execuções) quanto o E2E real estão hoje ambos aprovados no Windows real do usuário.** Ainda
  não feito: empacotamento final v2.2.

## Próximo (prioridade, nesta ordem)

1. **Executar o worker geométrico de verdade no Windows do usuário** e devolver os resultados
   para fechar os itens de aceite que dependem disso — guia completo em
   `docs/examples/WINDOWS_EXECUTION_KIT.md`. Sem isso, a Fase 3 não deve começar (condição
   explícita do Prompt Mestre). O que precisa ser confirmado com uma execução real (não apenas
   testes unitários matemáticos, já feitos no Incremento 2.1.1):
   - Geração real de um scaffold Gyroid via `Voxels`/`Mesh` do PicoGK, com o domínio cilíndrico
     de fato recortado pelo volume real (não a bounding box).
   - Espessura/isovalor/porosidade/seed efetivamente refletidos na malha resultante.
   - Diferença real preview vs. final (voxel size efetivo).
   - Determinismo geométrico real: mesma receita + mesma seed, em duas execuções, produz o
     mesmo SHA-256 de STL.
   - Métricas (`GeometryMetricsCalculator`) e manifesto coerentes com o STL real gerado (hoje
     só provados contra malhas sintéticas de teste).
   - E2E Playwright (`apps/web/e2e/`) executado de ponta a ponta — bloqueado neste sandbox
     Linux (falta `libXdamage.so.1`/dependências nativas do Chromium, `sudo` desabilitado).
   - Alternativa não tentada: investigar um build nativo do PicoGK a partir do código-fonte C++
     para linux-x64 — caminho mais lento, exige avaliação de licença/suporte antes de adotar.
2. **Carregar dados reais de materiais** (AP-07: 32+ materiais, 43+ referências DOI) no catálogo
   que hoje está vazio — sem inventar nenhum valor, só o que estiver expressamente nos
   documentos-fonte auditados (`docs/SOURCE_DOCUMENTS.md`) ou claramente rotulado como
   sintético.
3. **RBAC básico por organização/projeto** (`PM-ONLY-04h`) — hoje só existe `role` de string
   simples; falta hierarquia institucional real antes de abrir o sistema a múltiplas
   organizações de verdade.
4. **Segunda topologia TPMS** (Schwarz-P ou IWP) como `schema_version "1.1.0"` do BioMatCEM,
   seguindo o padrão de versionamento do ADR-0006 — só depois do worker desbloqueado, para não
   acumular funcionalidade não verificável.
5. **FEM (Fase 2, continuação)** — explicitamente fora de escopo do Incremento 2.1/2.1.1; só
   deve começar depois que a vertical geométrica estiver realmente executável.

## Pendências para fechar o Incremento 2.2 Alpha Pesquisa

Registradas aqui para não perder o fio entre sessões — nenhuma delas foi decidida como "próxima"
sem confirmação do usuário, apenas listadas como o que falta para poder declarar este
incremento concluído:

1. ~~**Visualizador 3D consolidado**~~ -- **CONCLUÍDO e APROVADO no Windows real (E2E completo 15/15)** (branch `incremento-2.2-alpha-pesquisa`,
   commits `32f4969`..`4180a67`): STL real (binário e ASCII), download autenticado com checksum
   e limite de tamanho, todos os controles do checklist (órbita/pan/zoom, wireframe,
   transparência/opacidade, eixos, grade, bounding box, clipping, screenshot, fullscreen),
   painel de proveniência com detecção de divergência API-vs-manifesto, cancelamento, descarte
   completo de recursos WebGL, fallback sem WebGL. Voronoi real continua deliberadamente fora
   desta rodada (item 2 abaixo). **Cobertura E2E dos controles (`apps/web/e2e/viewer.spec.ts`,
   12 testes) ESCRITA** -- primeira execução real no Windows (`e2e-only-20260807-001756`,
   commit `1be54e3`) reprovou 12/12 por um bug real no fixture do job pré-semeado
   (`seed_e2e_user.py` retornava `already_seeded` sem reconciliar o job legado já persistido no
   banco Windows de rodadas anteriores) -- causa raiz confirmada e corrigida (script reescrito
   como sequência idempotente/reconciliável; 7 testes de regressão novos; ver `TEST_EVIDENCE.md`
   seção 26). **Segunda execução real** (`viewer-e2e-evidence-20260807-012919`, commit
   `f8490d9`) confirmou a reconciliação do seed funcionando (`status: repaired`), mas reprovou as
   MESMAS 12/12 por uma causa raiz DIFERENTE e real: um deadlock de montagem no estado "empty"
   do `StlViewer.tsx` (a div de `containerRef` nunca era renderizada nesse estado, bloqueando
   para sempre a transição a "ready" quando o artefato chegava depois do mount, como acontece de
   fato em `JobDetailPage.tsx`) -- corrigido, com teste de regressão que reproduz exatamente essa
   sequência e comprovadamente falha sem a correção; ver `TEST_EVIDENCE.md` seção 27. **Terceira
   execução real** (`e2e-only-20260807-110029`, commit `85b58c4`) saltou para 11/14 aprovados.
   Das 3 falhas restantes: "eixos e grade" e "cancelamento" eram expectativa INCORRETA do teste
   (o produto sempre teve eixos/grade visíveis por padrão; o container do canvas é
   permanentemente montado desde a correção anterior, então `<canvas>` nunca chega a count=0 só
   por cancelar) -- corrigidos os testes (divididos/estendidos, com um novo marcador
   `data-viewer-status` observável e não sensível). "Fullscreen" era um DEFEITO REAL de
   acessibilidade: `requestFullscreen()` era chamado só no container do canvas, deixando os
   controles (inclusive o botão de saída) fora da "top layer" do navegador e inalcançáveis em
   tela cheia real -- corrigido chamando `requestFullscreen()` no `<div>` mais externo (controles
   + canvas juntos), sem z-index manual nem `click({force:true})`. Testes de regressão
   confirmados via mutation testing (`git stash` isolando a correção). Ver `TEST_EVIDENCE.md`
   seção 28. **Quarta execução real** (`e2e-only-20260807-201720`, commit `7719aeb`, árvore de
   trabalho limpa) retornou **15/15 aprovados, 0 falhas, `E2EExitCode=0`**, em Chromium real no
   Windows (2,1 min de Playwright) -- confirma as 3 correções da rodada anterior funcionando de
   ponta a ponta: "fullscreen com entrada e saída", "cancelamento real do download" e "retomada
   após cancelamento" aparecem explicitamente entre os controles aprovados. Ver
   `TEST_EVIDENCE.md` seção 29. **Cobertura E2E completa do visualizador 3D: APROVADA.** Nenhuma
   alteração de código foi necessária nesta rodada documental -- as suítes completas já haviam
   sido confirmadas na rodada anterior. Pendência separada registrada (não bloqueia esta
   aprovação): 11 avisos de `npm audit` observados no `npm ci` desta execução (sem causar
   falha) exigem TRIAGEM antes do empacotamento final do Incremento 2.2 -- `npm audit fix`/
   `--force` deliberadamente NÃO executados nesta rodada (ver item 5 abaixo).
2. ~~**`VoronoiTopologyProvider` real**~~ -- **CONCLUÍDO e APROVADO no Windows real** (commits
   `e07a5e2`..`bf756a4` implementaram; execução real `voronoi-validation-staged-
   20260806-195638` aprovou): geração de sítios, tesselação 3D real (`MIConvexHull`, MIT,
   licença auditada), grafo, struts, suavização de nós, calibração de porosidade, métricas,
   golden recipes, frontend, auditoria STL independente e roteiro Windows -- todos implementados,
   testados E confirmados contra o worker PicoGK real (6/6 golden recipes, 2x cada, determinismo
   byte a byte, zero processos órfãos -- ver `TEST_EVIDENCE.md` seção 23). O E2E Playwright
   DESSA mesma execução ficou inconclusivo por um defeito de infraestrutura do roteiro
   (frontend não iniciado antes do Playwright) -- registro histórico preservado sem alteração.
   A correção foi **CONFIRMADA em uma reexecução real separada e posterior**
   (`Run-E2EOnly.ps1`, commit `84f46fc`): 2/2 testes E2E aprovados, `E2EExitCode=0`, sem
   processos órfãos -- ver `TEST_EVIDENCE.md` seção 24. Nota de escopo: esse E2E cobre
   login/projeto/receita e a página de job com download do STL -- os controles novos do
   visualizador 3D (item 1 acima) agora têm um spec E2E próprio escrito
   (`apps/web/e2e/viewer.spec.ts`), já incluído automaticamente na próxima execução do mesmo
   `Run-E2EOnly.ps1` (roda todos os `*.spec.ts` de `apps/web/e2e/`), mas ainda pendente de
   confirmação real no Windows (ver item 1 e `TEST_EVIDENCE.md` seção 25).
3. **`DesignAdvisor` concreto** — hoje é só um `Protocol` sem implementação; qualquer
   implementação futura precisa registrar-se explicitamente (mesmo princípio de
   não-descoberta-automática do `TopologyProviderRegistry`) e nunca decidir sozinha sem revisão
   humana registrada.
4. **Empacotamento final v2.2** — explicitamente NÃO feito nesta rodada, por instrução: nenhum
   pacote final foi gerado, e o incremento não foi declarado concluído.
5. **Triagem dos 11 avisos de `npm audit` observados na quarta execução Windows real**
   (`e2e-only-20260807-201720`, ver `TEST_EVIDENCE.md` seção 29) — não causaram falha na
   execução, e `npm audit fix`/`npm audit fix --force` deliberadamente NÃO foram executados (por
   instrução explícita, para não arriscar breaking change indiscriminado, mesmo princípio já
   aplicado às 17 vulnerabilidades de tooling documentadas em
   `docs/security/DEPENDENCY_AUDIT_2.1.1.md` -- ver seção "Dependências deferidas" abaixo).
   Pendente: avaliar item a item se são as mesmas 17 já conhecidas (tooling de desenvolvimento,
   risco nulo/baixo no `dist/` de produção) ou achados novos, e decidir upgrades seguros --
   ANTES do empacotamento final v2.2 (item 4 acima).

## Reconciliação de pendências -- Fase A (rodada de fechamento do Incremento 2.2)

Auditoria integral realizada antes de qualquer alteração de código nesta rodada (commit-base
`922cbae`), cobrindo `ROADMAP.md`, `IMPLEMENTATION_STATUS.md`, `REQUIREMENTS_MATRIX.md`,
`TEST_EVIDENCE.md`, `apps/geometry-worker/WORKER_STATUS.md`, `docs/architecture/`,
`docs/security/DEPENDENCY_AUDIT_2.1.1.md`, `docs/regulatory/README.md`,
`docs/threat-model/README.md`, os relatórios das matrizes Windows e o histórico Git. Classifica
cada pendência para não repetir prova já aprovada e não deixar nada em aberto por omissão.

| # | Item | Classificação | Evidência já existente |
|---|---|---|---|
| 1 | Visualizador 3D + cobertura E2E completa | **JÁ APROVADA** | `TEST_EVIDENCE.md` seções 26-29; 15/15, exit code 0, commit `7719aeb`/`922cbae`. Não repetir. |
| 2 | `VoronoiTopologyProvider` real (matriz científica) | **JÁ APROVADA** | `TEST_EVIDENCE.md` seção 23; Windows real `voronoi-validation-staged-20260806-195638`. Não repetir. |
| 3 | Reprodução dos hashes golden Gyroid ("Seção 11" do plano do launcher) | **JÁ APROVADA por evidência equivalente** | As 3 golden recipes de regressão Gyroid (`block-gyroid-v1`, `cylinder-gyroid-v1`, `preview-gyroid-low-res-v1`) já rodaram 2x cada com o worker PicoGK real no Windows, com os 3 SHA-256 literais registrados e determinismo byte a byte confirmado (`WORKER_STATUS.md` seção 15, `TEST_EVIDENCE.md` seção 23). Não há necessidade de uma nova reprodução -- o requisito já está integralmente satisfeito. |
| 4 | E2E "fluxo não pré-semeado" ("Seção 10" do plano do launcher) | **JÁ APROVADA por evidência equivalente e mais forte** | O "gate final real" (`Run-FinalGate.ps1`, `TEST_EVIDENCE.md` seção 14, aprovado no Windows) exercita API→fila→worker PicoGK **real** (não `FakeWorkerClient`)→STL→Artifact/Manifest→download de ponta a ponta, sem nenhum job pré-semeado. Isso satisfaz o requisito de "fluxo real não pré-semeado" com rigor igual ou maior do que um spec Playwright equivalente faria (o gate final usa o worker de verdade; os specs Playwright usam seed só para não depender do PicoGK real dentro do teste de UI). Não é necessário criar um novo E2E Playwright sem preseed. |
| 5 | `DesignAdvisor` concreto | **Realmente pendente** | Hoje é só `Protocol` (`computational_intelligence.py`), com um teste de regressão explícito (`test_design_advisor_e_apenas_um_protocolo_sem_implementacao_concreta`) que barra qualquer classe concreta *nesse módulo*. Endereçado nesta rodada (Fase B) via um módulo novo e separado, registrado explicitamente, sem alterar o contrato nem o teste de regressão existente. |
| 6 | Segurança do ambiente de pesquisa (14 itens pedidos) | **Parcialmente aprovada** | Já implementado e testado: `DEV_AUTH` classificado (ADR-0005), recusa de startup com segredo inseguro (`assert_secure_for_environment`), autorização mínima admin (`require_admin`), auditoria de login/logout/tentativas negadas (`AuditEvent`), isolamento entre organizações em múltiplos endpoints (jobs, artefatos, projetos/receitas/materiais -- `test_geometry_job_security.py`, `test_artifact_download_is_denied_across_organizations`), download sempre autenticado via `Authorization: Bearer` (nunca token na URL), CORS restritivo por padrão (nunca `*` fora de development). **Sem cobertura dedicada ainda**: sanitização de logs, validação de caminhos de artefato, prevenção de command injection no processo do worker, política explícita de dados sintéticos/bloqueio de dados clínicos reais, comportamento seguro em falhas. Endereçado nesta rodada (Fase C). RBAC/ABAC completo (17 perfis, OIDC, MFA, revogação de sessão) é `PM-ONLY-04e/f/g/h` -- **deliberadamente adiado**, backlog de fases futuras, fora do escopo de pesquisa do 2.2 (`REQUIREMENTS_MATRIX.md`). |
| 7 | Testes de resiliência (dispatcher/fila/worker) | **Parcialmente aprovada** | Já cobertos: claim atômico via `SELECT FOR UPDATE SKIP LOCKED` (Incremento 2.1.1 item 6), cancelamento real com kill de processo (item 7), limites computacionais + cleanup (item 3), zero processos `dotnet.exe` órfãos confirmado nas execuções Windows reais (observação empírica, não teste automatizado permanente). **Sem teste automatizado dedicado ainda**: recuperação de job órfão, heartbeat, arquivo parcial, checksum divergente, manifesto inconsistente, indisponibilidade temporária de banco, encerramento gracioso como cenário isolado e repetível. Endereçado nesta rodada (Fase D) -- apenas no backend/fila/worker, sem reabrir a estabilização do launcher. |
| 8 | Launcher/instalador clínico completo | **Deliberadamente adiado** | Classificado como protótipo técnico deferido para a fase clínica (`IMPLEMENTATION_STATUS.md`, decisão já registrada). Não reaberto nesta rodada, por instrução explícita do usuário. O "dispatcher contínuo" básico já existente (parte do protótipo) não será expandido; a Fase D cobre resiliência do backend/fila/worker, não da orquestração do executável. |
| 9 | Triagem dos 11 avisos de `npm audit` | **Realmente pendente** | Endereçado nesta rodada (Fase E), com classificação técnica pacote a pacote (ver `docs/security/DEPENDENCY_AUDIT_2.2.md` após a Fase E). |
| 10 | Critério de aceite final + empacotamento v2.2 | **Realmente pendente -- objetivo desta rodada** | Fases I e J desta rodada. |
| 11 | FEM, DICOM, dados clínicos reais, prontuário, telemedicina, LIMS/ELN/biobanco, matriz regulatória formal (Anvisa/ISO/IEC), validação hospitalar | **Fora de escopo do Incremento 2.2** | `PM-ONLY-01/02/03/05` (`REQUIREMENTS_MATRIX.md`) -- confirmados como escopo de produto futuro, não deste incremento de pesquisa. Nenhuma ação nesta rodada. |

### Consolidação da lista de tarefas internas

As tarefas internas antigas "Seção 8: Segurança (pesquisa apenas)", "Seção 9: Testes novos
(launcher/dispatcher/UI/resiliência)", "Seção 10: E2E real obrigatório (fluxo não
pré-semeado)", "Seção 11: Compatibilidade -- reproduzir os 3 hashes golden do Gyroid" e "Seção
14/15: Critério de aceite + empacotar" vinham do plano original da rodada do launcher/dispatcher
(commits `9a6...`-`...`, antes da decisão de adiar o launcher). Itens 3 e 4 da tabela acima
mostram que a matriz Gyroid e o fluxo E2E não pré-semeado já foram satisfeitos por evidência
equivalente fora daquele plano original -- essas duas tarefas internas foram encerradas sem
repetição de prova. Segurança, testes de resiliência e critério de aceite/empacotamento
permanecem genuinamente pendentes e são retomados nesta rodada sob as Fases C, D, I e J deste
plano (mais amplo e mais preciso que o plano original do launcher).

## Fase G -- Determinação do gate Windows complementar (rodada de fechamento do Incremento 2.2)

Objetivo desta fase: decidir, com base em evidência e não em suposição, se alguma prova real no
Windows ainda falta antes do empacotamento final v2.2 -- sem repetir a matriz geométrica
Voronoi/Gyroid, a reprodução dos hashes golden, o E2E principal ou o E2E completo do
visualizador 3D, todos já aprovados (ver tabela da Fase A acima).

**Determinação: nenhum gate Windows complementar é necessário para fechar o Incremento 2.2.**

Justificativa, item a item, cobrindo tudo que mudou nas Fases B-F desta rodada de fechamento
em relação ao commit-base `922cbae` (último commit com gate Windows aprovado):

- **Fase B (`DesignAdvisor` concreto)**: modulo Python novo e isolado
  (`design_advisor_rule_based.py`), sem nenhuma dependência de geometria, PicoGK, worker C# ou
  UI. Toda a superfície é determinística e testada localmente (33 testes, mutation-tested). Não
  há comportamento observável no Windows que dependa de execução real além do que já é coberto
  pela suíte Python padrão.

- **Fase C (segurança do ambiente de pesquisa)**: validador de CORS, testes de path traversal,
  sanitização de log, comportamento seguro em falha -- tudo backend Python puro, sem nenhuma
  dependência de SO. A suíte de 12 testes novos roda de forma idêntica em Linux (sandbox) e
  Windows (mesmo interpretador Python, mesmas bibliotecas).

- **Fase D (resiliência)**: as duas mudanças de comportamento real (recomputação independente do
  SHA-256 do STL, tratamento de STL vazio como falha) alteram apenas *como a API reage* ao que o
  worker já devolve -- não alteram o worker C#/PicoGK, que permanece intocado nesta rodada. Para
  qualquer execução real já aprovada (golden recipes, gate final), o worker sempre produziu um
  STL não vazio cujo hash reportado bate com o hash real dos bytes gravados -- ou seja, o novo
  caminho de recomputação simplesmente confirma o mesmo hash que já era confirmado antes, sem
  mudar o resultado observável dessas execuções já aprovadas. Os novos caminhos de falha
  (`WORKER_CHECKSUM_MISMATCH`, `WORKER_PARTIAL_OUTPUT`) só são exercitados por cenários de
  injeção de defeito (dublês de worker no Python), nunca pelo worker PicoGK real nas condições já
  testadas. O terceiro item (dispatcher sobrevive a indisponibilidade transitória do banco) é
  controle de fluxo Python em torno de uma exceção do SQLAlchemy -- também independente de SO.
  Nenhum desses três itens exige uma nova execução do worker real no Windows para ser considerado
  provado; a suíte de 259 testes (Postgres real efêmero) já constitui a prova completa.

- **Fase E (triagem de dependências)**: mudanças restritas a `package-lock.json` do frontend
  (4 patches de dependências transitivas/de build). Build de produção e `build:pages` já
  reverificados no sandbox sem erro; nenhuma mudança de comportamento em tempo de execução do
  navegador.

- **Fase F (gates completos)**: exclusivamente correções de estilo/lint (ruff, mypy, bits de
  execução de arquivo) e confirmação de que os gates existentes (build do worker C#, 111 testes
  .NET, 10 scripts PowerShell) continuam passando. Nenhuma mudança de comportamento.

Em resumo: nenhuma das Fases B-F desta rodada tocou geometria, golden recipes, `TopologyProviders`,
PicoGK ou o código C# do worker, e nenhuma introduziu comportamento novo de UI que exigisse uma
nova cobertura Playwright real no Windows. Os quatro gates Windows já aprovados anteriormente
(matriz Voronoi/Gyroid, hashes golden Gyroid, E2E principal via gate final real, E2E completo do
visualizador 3D 15/15) continuam válidos e suficientes como evidência para o Incremento 2.2.

Caso o usuário deseje, por precaução adicional (não por exigência técnica), uma reexecução do
gate final real (`Run-FinalGate.ps1`) para reconfirmar que as mudanças de checksum/STL-vazio da
Fase D não regrediram o caminho feliz no worker PicoGK real, o comando exato já documentado
permanece válido e não foi alterado nesta rodada:

```powershell
.\scripts\Run-FinalGate.ps1 -RepoPath <caminho-do-repo> -BundlePath <caminho-do-bundle>
```

Esta reexecução é opcional/confirmatória, não bloqueante -- o empacotamento final v2.2 pode
prosseguir sem ela, dado que nada no diff desta rodada altera o caminho feliz já comprovado.

## Incremento 2.3, Rodada 1 (fundação canônica, proveniência e curadoria) — concluída

A partir do commit `e10d23d`, branch `incremento-2.3-dados-cientificos`: fundação persistente
do banco de dados científico (12 novas entidades, migração real verificada contra PostgreSQL em
3 cenários, API mínima de leitura/criação/revisão, seed sintético idempotente, 22 testes novos,
documentação completa em `docs/data/`) — ver `IMPLEMENTATION_STATUS.md` para o detalhamento
completo e `REQUIREMENTS_MATRIX.md` seção J. **Esta rodada NÃO declara o Incremento 2.3
completo** — é deliberadamente apenas a fundação.

## Incremento 2.3, Rodada 2 (infraestrutura de ingestão + conector PubChem + Adendo de Interface Científica Mínima) — concluída (execução real do piloto Windows ainda pendente)

Conector real de ingestão PubChem PUG REST, infraestrutura comum de conectores, e a interface
web mínima (`/app/scientific-data` e `/app/scientific-data/:entityId`) para visualizar
entidades/propriedades/proveniência/conflitos e operar o piloto via UI (dry-run/submissão/
status/cancelamento, restrito a admin). Ver `IMPLEMENTATION_STATUS.md` (seção "Adendo de
Interface Científica Mínima") e `REQUIREMENTS_MATRIX.md` seção K.1 para o detalhamento
completo. **Dois itens permanecem pendentes de execução real fora deste sandbox**: (1) o piloto
PubChem contra a rede oficial (`scripts/Run-PubChemPilotWindows.ps1`); (2) o E2E real da
interface científica em Chromium (`scripts/Run-ScientificDataE2EOnly.ps1`) — ambos escritos,
validados por parser/`--list`, e com o contrato subjacente exercido diretamente no sandbox, mas
não executados de ponta a ponta por bloqueio de infraestrutura do próprio sandbox (rede
bloqueada para o primeiro; bibliotecas nativas do Chromium ausentes para o segundo).

## Próximo (Incremento 2.3, Rodada 2 e além — candidatas, não decididas)

1. **Conector de ingestão real para uma única fonte candidata** (mais provável: Crossref, por
   ter o escopo mais restrito — apenas metadados bibliográficos — e a licença de metadados mais
   claramente aberta, CC0) — só depois de uma confirmação formal da licença vigente, nunca
   assumida. Ver `docs/data/SOURCE_REGISTRY_POLICY.md` e `docs/data/LICENSING_AND_REDISTRIBUTION.md`.
2. **Interface administrativa de curadoria** além da API mínima desta rodada — listagem/edição
   de observações pendentes de revisão, fila de revisão para curadores.
3. **Backfill opcional e auditável** de `MaterialRecord.scientific_entity_id` para os registros
   existentes do Incremento 2.1, se e quando fizer sentido consolidar os dois modelos.
4. **Camada de agregação/reconciliação de observações divergentes** — hoje elas apenas
   coexistem; uma futura funcionalidade de "valor consolidado" (com metodologia explícita, nunca
   uma média silenciosa) poderia ajudar o `DesignAdvisor` a consumir esses dados.
5. Carregar dados reais de materiais (AP-07) permanece condicionado à mesma cautela de sempre —
   nenhum valor inventado, e agora com a estrutura desta rodada disponível para armazená-los com
   proveniência completa quando isso for decidido.

## Dependências deferidas (Incremento 2.1.1)

17 vulnerabilidades npm de **tooling de desenvolvimento apenas** (ESLint 8.x e sua cadeia —
`@eslint/eslintrc`, `minimatch`, `brace-expansion`, etc. —, e Vite/Vitest/esbuild) foram
deliberadamente **não** corrigidas nesta sessão, por decisão explícita do usuário contra
atualizações forçadas/indiscriminadas — cada uma tem risco de breaking change real (majors:
ESLint 9/10 com flat config, Vite 8/Vitest 4) e explorabilidade nula ou muito baixa no artefato
de produção entregue (`dist/`), conforme análise item a item em
`docs/security/DEPENDENCY_AUDIT_2.1.1.md`. Migração planejada, não urgente:

- Migrar ESLint para flat config (`eslint.config.js`) e atualizar para 9.x/10.x.
- Avaliar migração de Vite 5→8 e Vitest→4 (ambos majors, múltiplas mudanças de API/config).
- **Migração para React Router v7** — o bump não-quebrador já aplicado neste incremento
  (6.26.2→6.30.4) resolve a maior parte do risco prático, mas o advisory de segurança
  (GHSA-jjmj-jmhj-qwj2) ainda afeta toda a série 6.x; a correção completa exige a migração major
  para v7 (API de rotas mudou, `createBrowserRouter`/tipos), avaliada e feita como item dedicado,
  não misturada a outra tarefa.

## Mais adiante (fora de escopo dos próximos incrementos)

- DICOM/imagens médicas, LIMS/ELN/terapia celular, prontuário/telemedicina/agenda clínica —
  `PM-ONLY-01/02/03` — todos fora de escopo até o núcleo científico (CAD/FEM/materiais/ML)
  estar consolidado, por decisão de sequenciamento, não por reavaliação do escopo confirmado em
  ADR-0001/ADR-0003.
- Matriz regulatória completa (`PM-ONLY-05`) — depende dos módulos clínicos acima existirem
  primeiro.
- OIDC/OAuth2.1+PKCE, MFA/WebAuthn, step-up authentication (`PM-ONLY-04e/04f/04g`) — substituir
  `DEV_AUTH` antes de qualquer uso com dados reais (nunca clínicos, mesmo depois).

## Princípio de sequenciamento

Nenhum incremento futuro deve ser apresentado como mais completo do que realmente é. Se um
bloqueio de ambiente (como o do PicoGK neste incremento) se repetir, o padrão a seguir é o
mesmo: implementar o máximo do contrato possível, testar genuinamente o que não depende do
bloqueio, documentar a evidência do bloqueio, e declarar o incremento parcialmente bloqueado —
nunca simular sucesso.
