# Arquitetura — BioMatCAD Nexus

Este documento descreve a arquitetura oficial (ADR-0002) e o que dela está realmente
implementado após o Incremento 2.1 da Fase 2 (primeira vertical funcional do núcleo BioMatCAD)
e as correções do **Incremento 2.1.1** (corretivo, sobre defeitos encontrados em auditoria — ver
ADR-0006, ADR-0007 e ADR-0008). A vertical geométrica continua **parcialmente bloqueada** por
ausência de runtime nativo do PicoGK em linux-x64 — isso não mudou neste incremento corretivo,
que corrigiu o código em volta do bloqueio (segurança, fila, cancelamento, manifesto, schema,
matemática do gyroid) sem poder provar a execução real do PicoGK neste sandbox. Para decisões e
motivações, ver `docs/adr/`. Para o inventário funcional item a item, ver
`IMPLEMENTATION_STATUS.md`.

## Visão geral

```text
apps/web  (React + TS + Vite)  ──HTTP/JSON──►  apps/api  (FastAPI)  ──SQL──►  PostgreSQL
                                                     │                          ▲
                                                     │                          │ fila = coluna
                                                     │                          │ GeometryJob.status,
                                                     │                          │ claim atômico
                                                     │                          │ (SELECT ... FOR
                                                     │                          │  UPDATE SKIP LOCKED,
                                                     │                          │  Incremento 2.1.1)
                                                     ├── scripts/geometry_dispatcher.py (processo
                                                     │   Python separado da API, consome jobs QUEUED,
                                                     │   emite heartbeat, recupera jobs órfãos)
                                                     │        │
                                                     │        └──subprocess──► apps/geometry-worker
                                                     │                          (C#/.NET9 + PicoGK 2.2.0
                                                     │                          — compila; correções de
                                                     │                          domínio/espessura/
                                                     │                          porosidade/seed/solda de
                                                     │                          vértices (2.1.1); execução
                                                     │                          real BLOQUEADA em
                                                     │                          linux-x64, ver ADR-0007)
                                                     ├── LocalStorageAdapter (artefatos, disco local;
                                                     │   mesmo contrato de um MinIO/S3 futuro)
                                                     ├── Redis (cache/locks) — não usado ainda
                                                     └── compute-worker (FEM/imagem/ML) — não implementado
```

O worker geométrico (`apps/geometry-worker`) é um processo **verdadeiramente separado** da API
— um binário .NET distinto, invocado via `subprocess` pelo dispatcher Python, nunca importado
in-process. Isso satisfaz o requisito explícito do Incremento 2.1 de que "o processo geométrico
deve ser separado da API", mesmo sem Docker disponível neste ambiente. O cancelamento
(Incremento 2.1.1) mata a árvore de processos do subprocess real (via `psutil`), não apenas o
processo pai — cross-platform, verificado neste sandbox.

O build de demonstração de `apps/web` (`npm run build:pages`) gera um site estático que **não**
se conecta a nenhum backend por padrão — usa `demoClient.ts`, um cliente sintético em memória,
conforme Prompt Mestre §3.3/§7.1.

## apps/web (frontend)

- React 18 + TypeScript estrito + Vite 5.
- Roteamento: `react-router-dom`, com `basename` dinâmico via `import.meta.env.BASE_URL` — o
  mesmo bundle funciona em `/` (dev/local) e em `/biomatcad-nexus/` (GitHub Pages), sem
  recompilar lógica de rota manualmente.
- Estado de autenticação: `AuthContext` guarda o token JWT **somente em memória** (React state).
  Não há `localStorage`/`sessionStorage` envolvido na autorização — consequência: recarregar a
  página derruba a sessão (limitação conhecida, aceita deliberadamente por segurança).
- Estado de tema (claro/escuro): `ThemeProvider`, persistido em `localStorage` — isso é
  preferência de UI, não segredo nem token, então não viola a restrição do Prompt Mestre.
- Cliente de API: `src/api/client.ts` (real, fala com `apps/api`) e `src/api/demoClient.ts`
  (sintético, usado quando `__BIOMATCAD_DEMO_MODE__` é `true`, injetado em build-time pelo Vite
  conforme o modo `demo`).
- Design system inicial: tokens CSS em `src/theme/tokens.css`, cores conforme Prompt Mestre §8
  (azul-petróleo, verde biomédico, branco quente, grafite, âmbar de alerta, vermelho de erro).
  Um `packages/ui` compartilhado formal ainda não existe — os componentes vivem em
  `apps/web/src/components` por ora.

## apps/api (backend)

- FastAPI + Pydantic v2 + `pydantic-settings` (configuração 100% via variáveis de ambiente,
  nenhum segredo hardcoded).
- SQLAlchemy 2.0 (ORM) + Alembic (migrações). PostgreSQL é o banco alvo oficial; SQLite só é
  aceito em `development`/`test` (validado por `field_validator` em `config.py`, que recusa
  SQLite em `local-network`/`staging`/`production`).
- Autenticação: login por e-mail/senha (bcrypt via passlib) emitindo JWT (PyJWT) de curta
  duração (30 min por padrão). Classificada explicitamente como **`DEV_AUTH`** (ADR-0005) —
  exposta em `GET /api/v1/system/status.auth_mode`. Sem refresh token, sem MFA, sem RBAC
  granular — isso é `PM-ONLY-04a`–`04h`, backlog (`REQUIREMENTS_MATRIX.md` seção D).
  `Settings.assert_secure_for_environment()` recusa iniciar o processo fora de `ENVIRONMENT=test`
  se `API_SECRET_KEY` estiver ausente, for o valor padrão de desenvolvimento, ou tiver menos de
  32 caracteres. `POST /api/v1/auth/logout` é simbólico (sem blocklist de token).
- Estado operacional: tabela `operational_states` com 5 estados (`OperationalStateKind`):
  `research`, `laboratory` (contextos independentes) e `clinical_test`/`clinical_pilot`/
  `clinical_production` (suíte clínica). **Dois grupos nunca combináveis** (ADR-0004,
  corrigindo um bug do Incremento 1):
  - `POST /api/v1/system/operational-state/activate` ativa `research`/`laboratory`
    individualmente (admin + `OPERATIONAL_STATE_MASTER_KEY`); rejeita (400) qualquer um dos 3
    kinds clínicos.
  - `POST /api/v1/system/clinical-suite/activate` e `.../deactivate`
    (`services/operational_state_service.py::set_clinical_suite`) ativam/desativam os três
    estados clínicos **atomicamente, em uma única transação de banco** — os três mudam juntos
    ou nenhum muda (rollback completo em falha, testado com falha induzida). Mesma chave
    mestra, nunca uma segunda; exige admin; suporta `expires_at` opcional avaliado em tempo de
    leitura (`OperationalState.is_effectively_enabled`).
  - `clinical_suite_enabled` em `GET /api/v1/system/status` é `all(...)` sobre os 3 estados
    clínicos — nunca inclui `laboratory` (bug corrigido do Incremento 1, onde usava OR e incluía
    Laboratório).
- Auditoria: tabela `audit_events`, populada em login (sucesso/falha), logout, e em toda
  tentativa de ativação/desativação de estado operacional independente ou de suíte clínica
  (negada por chave incorreta, negada por falta de permissão administrativa, ou concedida) —
  com estado anterior, estado novo, justificativa e identidade do administrador quando
  aplicável. Append-only por convenção da camada de aplicação — não há garantia de imutabilidade
  a nível de infraestrutura ainda (Prompt Mestre §23.3 pede que isso fique explícito, não
  implícito).
- Erros: handler padronizado (`errors.py`) retorna `{"error": {"id", "code", "message",
  "details"}}` para toda exceção HTTP, de validação ou não tratada, com `id` correlacionável ao
  log do servidor.
- Logging: `logging_config.py` filtra mensagens contendo palavras-chave sensíveis
  (senha/token/secret/cpf/etc.) antes de emitir — mitigação simples, não uma garantia formal de
  ausência de vazamento de dados sensíveis em logs.

## Bancos de dados usados nesta sessão (ambiente de desenvolvimento)

Sem Docker disponível no sandbox de execução, os testes e a migração rodaram contra PostgreSQL
16 real via [`pgserver`](https://pypi.org/project/pgserver/) (binários oficiais do Postgres,
sem privilégio de root, iniciados/parados manualmente por script). Isso é equivalente em
comportamento a rodar contra o `postgres:16-alpine` do `docker-compose.yml`, mas **não é** o
mesmo caminho de execução — o `docker-compose.yml` do repositório continua não testado neste
ambiente (ver `IMPLEMENTATION_STATUS.md`).

## services/operational_state_service.py (novo no Incremento 1.1)

Módulo dedicado, separado dos routers, que concentra a lógica de transição de estado:

- `get_or_create_state(db, kind)` — obtém ou cria a linha `OperationalState` de um kind.
- `get_effective_states(db)` — retorna `dict[str, bool]` de todos os 5 kinds, já resolvendo
  expiração (`is_effectively_enabled`), usado tanto por `system.py` (status) quanto pelos
  routers de ativação.
- `set_clinical_suite(db, *, enabled, admin_user, justification, expires_at)` — a única função
  que grava os 3 estados clínicos; usa `db.flush()` para validar antes do commit, envolve tudo
  em `try/except` com `db.rollback()` explícito e levanta `ClinicalSuiteTransactionError` em
  caso de falha, garantindo que nenhum dos três fique parcialmente alterado.

Essa separação existe para que a garantia de atomicidade viva em um único lugar testável
isoladamente (`tests/test_clinical_suite.py`), em vez de replicada entre o router de ativação e
o de desativação.

## BioMatCEM — receita geométrica versionada (Incremento 2.1, semântica corrigida no 2.1.1)

`schemas/biomatcem/geometry-recipe-v1.schema.json` (JSON Schema Draft 2020-12) é o único
contrato aceito entre frontend, API e worker para descrever uma geometria a gerar (domínio
block/cylinder, topologia gyroid, resolução, modo preview/final, seed, limites computacionais,
formatos de saída). Validado em duas camadas — `services/recipe_service.py` (Python, fonte de
verdade real) e, desde o Incremento 2.1.1, `recipeValidationOffline.ts` no frontend usando Ajv
(`ajv/dist/2020`) contra uma cópia local **sincronizada** do mesmo schema (`apps/web/src/
schemas/geometry-recipe-v1.schema.json`, com teste de sincronia byte-a-byte,
`schemaSync.test.ts`) — em vez de ~15 regras manuais que divergiam do schema real. Nunca aceita
campos desconhecidos nem qualquer forma de código executável.

**Semântica espessura/isovalor corrigida no Incremento 2.1.1 (ver ADR-0008):** no Incremento
2.1, `isovalue` e `wall_thickness_mm` tinham papéis ambíguos/sobrepostos. Agora:
`wall_thickness_mm` é **obrigatório** em `topology` e é o único controlador de espessura de
parede — o worker converte esse valor em meia-largura de banda isovalor via uma aproximação
documentada (`GyroidMath.WallThicknessMmToHalfBandWidth`, ver comentário no próprio arquivo:
não há distância euclidiana exata conhecida para a superfície gyroid). `isovalue` passou a ser
**opcional** (default `0.0`) e representa apenas o **centro** da banda sólida — não controla
espessura. Combinações fisicamente contraditórias (ex.: `wall_thickness_mm >= cell_size_mm / 2`,
ou banda que extrapola a amplitude máxima da função gyroid) são rejeitadas na validação, com erro
estruturado `TOPOLOGY_PARAMETERS_INCONSISTENT`, antes de qualquer execução. Ver ADR-0006 (schema
original) e `schemas/biomatcem/README.md`.

## apps/geometry-worker (C#/.NET 9 + PicoGK 2.2.0) — Incremento 2.1, corrigido no 2.1.1

Worker real, compilado com sucesso, responsável por gerar o scaffold Gyroid a partir de uma
receita BioMatCEM já validada e canonicalizada. Separa deliberadamente o código dependente do
runtime nativo do PicoGK (`GyroidScaffoldBuilder.cs`, `Program.cs`) do código independente e
puramente matemático (`GyroidMath.cs`, novo no Incremento 2.1.1; `JobEnvelope.cs`,
`SimpleMesh.cs`, `GeometryMetricsCalculator.cs`, `StlExporter.cs`), o que permite testar
genuinamente essa segunda parte (62 testes xUnit) mesmo com a primeira bloqueada.

- `GyroidMath.cs` — TOTALMENTE independente do PicoGK (nenhuma referência a
  `PicoGK.Library`/`Voxels`/`Mesh`): avaliação do campo gyroid de Schoen (1970), SDF exata de
  bloco e cilindro, interseção booleana implícita via `max()` (CSG padrão), conversão
  `wall_thickness_mm` → meia-largura de banda, mapeamento determinístico seed→deslocamento de
  fase, estimativa de fração sólida por amostragem em grade regular, e calibração de porosidade
  por bisseção analítica (`CalibratePorosityByBisection`) usando essa estimativa como oráculo.
  Também define o piso de voxel size do modo preview (0.3 mm) e as estimativas prévias
  (limite superior, grade densa) de contagem de voxels e memória usadas para rejeitar receitas
  antes da execução.
- `GyroidScaffoldBuilder.cs` — a classe `GyroidDomainImplicit` (substitui o antigo arquivo
  `GyroidImplicit.cs` do Incremento 2.1, que não existe mais como arquivo separado) implementa
  `IImplicit` combinando a banda gyroid com o SDF do domínio real (bloco ou cilindro) via
  `GyroidMath.IntersectSignedDistance` — o cilindro deixa de ser recortado pela bounding box e
  passa a ser recortado pelo volume real do cilindro. `GyroidScaffoldBuilder.BuildAndExport`
  aplica a calibração de porosidade quando `target_porosity_pct` está presente, o piso de voxel
  size em modo preview, e solda a malha (`SimpleMesh.Weld()`) antes de exportar/medir — corrige
  a divergência de contagem de vértices encontrada na auditoria (STL com 224 vértices únicos/336
  triângulos enquanto o manifesto reportava 168 vértices; causa raiz era ausência de
  deduplicação, agora corrigida na fonte).

**Execução real continua bloqueada neste ambiente** — o pacote NuGet 2.2.0 não traz runtime
nativo para linux-x64 (ver `apps/geometry-worker/WORKER_STATUS.md` e ADR-0007 para a evidência
completa: inspeção do pacote + `DllNotFoundException` real reproduzida). Isso significa que
todas as correções acima estão provadas matematicamente (62 testes xUnit); a geração real de
bloco (`block-gyroid-v1`) já **foi** provada contra o PicoGK real (ver `IMPLEMENTATION_STATUS.md`),
mas cilindro, preview, determinismo e auditoria independente ainda **não** foram
provadas contra uma execução real do PicoGK nesta sessão — essa prova depende da execução no
Windows do usuário (`docs/examples/WINDOWS_EXECUTION_KIT.md`).

## Segurança, fila e ciclo de vida de jobs (Incremento 2.1.1)

Correções concentradas em `apps/api/src/biomatcad_api/services/geometry_job_service.py`,
`worker_client.py`, `manifest_service.py` e `scripts/geometry_dispatcher.py`:

- **Isolamento entre organizações**: antes de criar um `DesignRun`, o serviço agora verifica
  explicitamente que projeto, receita e material pertencem à mesma organização do usuário
  autenticado, que a receita pertence de fato ao projeto informado, e que a receita está no
  estado `validated`. Qualquer violação retorna 403 com auditoria — coberto por
  `test_geometry_job_security.py` (testes de ataque dedicados: projeto de outra organização,
  receita de outra organização, receita não pertencente ao projeto informado, receita não
  validada). **Provado de verdade, não apenas por código revisado.**
- **Fila com claim atômico**: o dispatcher reivindica um `GeometryJob` via
  `SELECT ... FOR UPDATE SKIP LOCKED` (PostgreSQL), eliminando a janela de corrida do padrão
  anterior (ler status, depois atualizar em uma transação separada), onde dois dispatchers
  concorrentes podiam reivindicar o mesmo job. `test_geometry_job_concurrency.py` sobe duas
  conexões/threads reais e independentes contra um Postgres real e confirma zero jobs
  reivindicados em duplicidade ao longo de 24 jobs. O dispatcher também emite heartbeat
  periódico e recupera jobs órfãos (processo que morreu no meio da execução, heartbeat expirado).
- **Cancelamento real**: cancelar um `GeometryJob` em execução mata a árvore de processos real
  do subprocess do worker (via `psutil`, cross-platform), é idempotente (recancelar não falha
  nem duplica efeito) e tem proteção de corrida — um job cancelado no meio da execução nunca
  pode transicionar depois para `succeeded` (`test_geometry_job_cancellation.py`, incluindo um
  teste de corrida dedicado contra o fluxo real de `dispatch_job`).
- **Manifesto reestruturado para rastreabilidade completa**: `ArtifactManifest` agora registra
  commit Git, versão do worker/.NET/PicoGK, plataforma, seed e deslocamento de fase efetivo,
  parâmetros efetivamente aplicados (espessura/isovalor/porosidade), lista de artefatos com
  SHA-256 individual, e status de validação do STL. O SHA-256 do **próprio** manifesto é
  calculado e armazenado numa coluna de banco separada (`Artifact.manifest_checksum` ou
  equivalente) — nunca embutido dentro do JSON que ele mesmo descreve, o que evitaria
  circularidade (o hash de um documento não pode depender de um campo dentro do próprio
  documento sem uma convenção de exclusão, que é exatamente o que se evitou aqui ao mover o
  checksum para fora).
- Nenhum destes itens depende de uma execução real do PicoGK — todos foram exercitados com um
  `FakeWorkerClient`/mocks de subprocess controlados, o que é suficiente para provar a lógica de
  autorização, concorrência de fila e cancelamento (que são propriedades do processo Python, não
  da geometria em si). Ver `IMPLEMENTATION_STATUS.md`, itens 7, 8 e 9 do checklist de aceite.

## O que ainda não existe

- `apps/compute-worker` (FEM, imagem, ML, otimização) — apenas README.
- `packages/biomat-dsl`, `packages/scientific-core`, `packages/contracts`,
  `packages/fhir-mappings`, `packages/ui` — apenas README.
- Todos os `services/*` (identity/Keycloak, fhir, pacs, video, object-storage, observability).
- Todo o envelope clínico/laboratorial (`PM-ONLY-01/02/03/05`).
- RBAC/ABAC completo (`PM-ONLY-04` parcialmente iniciado: só há um `role` de string simples no
  modelo `User`, sem permissões por instituição/unidade/projeto).
- Geração real de scaffold Gyroid, thumbnail, exportação VDB e determinismo geométrico
  verificado (bloqueados pela ausência de runtime nativo do PicoGK — ver acima e ADR-0007). As
  correções de código do Incremento 2.1.1 (domínio real, espessura/isovalor/porosidade/seed,
  preview vs. final, solda de vértices) estão prontas e unitariamente testadas, mas **ainda não
  provadas contra uma execução real do PicoGK** — essa prova é o próximo passo, no Windows do
  usuário.
- E2E real (Playwright) executado de ponta a ponta em um navegador real — escrito
  (`apps/web/e2e/`), mas bloqueado neste sandbox Linux (faltam bibliotecas nativas do Chromium e
  `sudo` está desabilitado) — ver `apps/web/e2e/README.md`.

## Incremento 2.2 Alpha Pesquisa — o que foi adicionado (branch `incremento-2.2-alpha-pesquisa`)

Este incremento **não tenta desbloquear o PicoGK** (continua bloqueado neste sandbox Linux,
ADR-0007) nem retoma o launcher Windows (classificado como protótipo técnico deferido — ver
`docs/DEFERRED_WINDOWS_LAUNCHER.md` ou documento equivalente). O foco é a GUI de pesquisa, a
observabilidade real, e três preparações arquiteturais auditáveis:

- **Observabilidade real**: contrato de 6 estados operacionais (`healthy/degraded/unavailable/
  stale/stopped/unknown`) derivado de checks reais (binário do worker compilado, heartbeat de
  job `running`, tamanho da fila), nunca um estado "saudável" inventado — integrado à GUI
  (`ObservabilityPage.tsx`, painel autenticado).
- **GUI completa de pesquisa**: fluxo login → catálogo → projeto → receita → job → métricas →
  visualizador 3D → download, com 3 lacunas reais fechadas nesta rodada: reenvio (retry) de
  jobs falhos/cancelados, seleção de material antes do envio do job, e um aviso de proveniência
  obrigatório acima da tabela de métricas (nunca deixar implícito que um resultado calculado é
  validação experimental).
- **Contrato `TopologyProvider` (ADR-0009)**: abstração versionada e explícita, espelhada em
  Python (`apps/api/src/biomatcad_api/services/topology_providers.py`) e C#
  (`apps/geometry-worker/ITopologyProvider.cs` +  `TopologyProviderRegistry.cs`), com
  `GyroidTopologyProvider` como única implementação real (delega 1:1 para o
  `GyroidScaffoldBuilder` já existente, sem alterar nenhum resultado das 3 golden recipes
  aprovadas) e `voronoi` registrado como `status="planned"` — rejeitado explicitamente em
  ambos os lados até ter implementação real. Nenhum carregamento dinâmico/reflection/eval é
  usado; toda topologia suportada é uma classe estaticamente compilada. O provider
  efetivamente usado é registrado no manifesto (`manifest_json["topology_provider"]`).
- **Preparação técnica para Voronoi** (`docs/architecture/voronoi-topology-preparation.md`):
  documento de arquitetura (sem código) cobrindo geração de sítios, distribuição determinística
  por seed, diagrama de Voronoi, extração de grafo, geração de struts, suavização de nós
  (comparação técnica evenhanded entre Catmull–Clark e cápsulas implícitas/smooth-union do
  PicoGK, sem preferência estética), recorte pelo domínio anatômico, calibração de porosidade,
  conectividade, métricas, manifold/watertight e limites computacionais. Nenhuma dessas etapas
  foi implementada em código nesta rodada.
- **Módulo de inteligência computacional** (`apps/api/src/biomatcad_api/services/
  computational_intelligence.py`): apenas contratos de dados (`DesignConstraints`,
  `DesignProposal`, `ObjectiveComparison`, `DesignIterationRecord`) e um `Protocol`
  (`DesignAdvisor`) sem nenhuma implementação concreta, mais 3 funções reais e determinísticas
  (listagem de providers compatíveis via o registro real do TopologyProvider, comparação
  aritmética de métricas contra objetivos, montagem de um registro de decisão manual completo
  com `algorithm_name` sempre `"manual-researcher-decision"`). Nenhuma alegação de equivalência
  a softwares de IA autônoma proprietários é feita. **Atualização (fechamento do Incremento
  2.2, Fase B)**: implementação concreta real do `DesignAdvisor` adicionada em módulo separado
  (`apps/api/src/biomatcad_api/services/design_advisor_rule_based.py`,
  `RuleBasedDesignAdvisor`, `RULES_VERSION="1.0.0"`), registrada de forma explícita e
  não-reflexiva (mesmo padrão do `TopologyProviderRegistry`), sem alterar o `Protocol` original
  nem o teste de regressão que impede implementação concreta dentro do módulo de contratos. Só
  emite recomendação/alerta com justificativa rastreável, nível de confiança metodológica e
  aviso fixo de ausência de validação clínica -- nunca uma decisão clínica, nunca uma
  propriedade de material inventada. Ver `IMPLEMENTATION_STATUS.md` seção "Fechamento do
  Incremento 2.2" para o detalhamento completo e `REQUIREMENTS_MATRIX.md` seção I.
- **Identidade visual oficial**: logomarca original preservada byte a byte
  (`apps/web/public/brand/biomatcad-nexus-logo-original.png`), derivados gerados por operações
  não-destrutivas (remoção de fundo por conectividade de borda, recorte, redimensionamento) —
  componente `BrandLogo` (`apps/web/src/components/brand/BrandLogo.tsx`) integrado em
  landing/login/cabeçalho/sidebar/página "Sobre" (`/about`, nova), favicon e manifesto PWA
  usando o placeholder `%BASE_URL%` do Vite para funcionar tanto no build normal quanto no de
  demonstração do GitHub Pages. Origem, autoria, situação de licença e uma limitação real de
  contraste no tema escuro (medida, não corrigida por redesenho) estão em
  `docs/brand/ASSETS_NOTICE.md`.

## Incremento 2.2 (rodada Voronoi) — segunda topologia real (`voronoi_cell_edges_v1`)

Sobre a base da rodada anterior (contrato `TopologyProvider`, ADR-0009), esta rodada implementa
a **segunda topologia real** anunciada como "planejada": Voronoi de células com arestas
espessadas (struts), não Delaunay e não uma aproximação mal rotulada. Continua **sem desbloquear
o PicoGK** neste sandbox Linux (ADR-0007) — toda a matemática independente de PicoGK foi provada
via testes unitários reais; a execução do worker completo (`Voxels`/`Mesh` reais) permanece
dependente de execução em Windows pelo usuário.

- **Auditoria matemática prévia**: decisão registrada de usar diagrama de Voronoi real (não
  Delaunay renomeado) — sítios gerados deterministicamente por seed, tesselação 3D via
  triangulação de Delaunay (`MIConvexHull`, MIT, única dependência nova) seguida de extração do
  grafo dual real (nós = circuncentros dos tetraedros, arestas = faces compartilhadas entre
  tetraedros vizinhos — convenção de adjacência do MIConvexHull verificada empiricamente, não
  assumida da documentação). Arestas que cruzam o domínio são recortadas pelo SDF real do
  domínio (reuso de `GyroidMath.BoxSignedDistanceMm`/`CappedCylinderSignedDistanceMm`).
- **Schema**: `voronoi_cell_edges_v1` adicionado a `geometry-recipe-v1.schema.json` como um
  segundo ramo do `oneOf` de `topology`, com campos próprios (`site_count`, `distribution`,
  `strut_radius_mm`, `node_smoothing`, `node_radius_factor`, `boundary_behavior`,
  `seed_site_min_separation_mm`, `target_porosity_pct`) e rejeição explícita de mistura com
  campos do Gyroid (`wall_thickness_mm` etc.) em qualquer direção.
- **Worker**: `VoronoiSiteGenerator.cs` (geração determinística por seed, distribuições
  `uniform_random` e `jittered_grid`), `VoronoiTessellation.cs` (tesselação 3D real + grafo de
  arestas + recorte pelo domínio + verificação de contenção com tolerância nomeada), struts
  implícitos (cápsulas arredondadas ao redor de cada aresta) com suavização de nós via
  smooth-union do PicoGK (`node_smoothing`, `node_radius_factor`), calibração de porosidade
  fechada sobre a malha real (mesmo padrão do Gyroid, iterativa contra o volume medido, não
  estimado). `VoronoiTopologyProvider` registrado no `TopologyProviderRegistry` ao lado do
  Gyroid, sem alterar nenhum resultado das 3 golden recipes Gyroid já aprovadas
  (`voronoi_cell_edges_v1` passa a ter `status="implemented"` nos dois lados, Python e C#).
- **Métricas específicas**: contagens de sítios/células/nós/arestas (incluindo arestas
  descartadas por ficarem fora do domínio), comprimento de strut (média/min/max/desvio-padrão),
  grau de nó (média/min/max/desvio-padrão), componentes conectados, nós isolados, contenção
  máxima no domínio e uma flag booleana de contenção verificada — tudo via o mesmo padrão
  `[JsonExtensionData]`/`metrics.Extra` já usado pelo Gyroid, sem exigir nenhuma mudança de
  schema no lado Python (`dict[str, Any]` genérico já suportava isso).
- **Frontend**: `RecipeEditorPage.tsx` com formulário completo para os dois ramos da união
  discriminada `topology` (Gyroid/Voronoi), estimativa de custo computacional client-side
  (`computeCostEstimate.ts`, mesma fórmula de voxel/memória do servidor, independente de
  topologia), aviso de "receita pesada" para Voronoi com muitos sítios, tabela de métricas
  Voronoi dedicada em `JobDetailPage.tsx` com disclaimer explícito de que a conectividade
  reportada é topológica (grafo de Voronoi), não uma alegação de conectividade biológica. O modo
  de demonstração (`demoClient.ts`, GitHub Pages) **não fabrica** um resultado Voronoi de
  sucesso: qualquer job Voronoi enviado no demo termina em `failed` com
  `error_code: "DEMO_EXECUTION_UNAVAILABLE"`, reaproveitando a UI de falha já existente.
- **3 golden recipes Voronoi** (`block-voronoi-preview-v1`, `block-voronoi-final-v1`,
  `cylinder-voronoi-preview-v1`) — mesma convenção de nomenclatura e localização das golden
  recipes Gyroid, cobrindo domínio bloco e cilindro, `preview` e `final`.
- **Auditoria independente de STL** (`apps/api/scripts/audit_stl_independent.py`): parser STL e
  reimplementação da SDF de domínio escritos do zero (não reusam o código do worker), para dar
  uma segunda opinião real sobre watertight/manifold/contenção — desenhado para ter chance real
  de capturar um bug no próprio cálculo de métricas do worker, e não apenas comparar o worker
  contra si mesmo.
- **Caderno de invenção confidencial** (`docs/private/INVENTION_NOTEBOOK_VORONOI.md`, não
  público) — registra alternativas consideradas, decisões, experimentos e bugs reais
  encontrados durante esta implementação, sem nenhuma linguagem de reivindicação de patente,
  ®/™ ou declaração de registro no INPI.
- **Roteiro único de validação Windows** (`scripts/Run-VoronoiWindowsValidation.ps1`) — orquestra
  build/testes do worker, testes do backend/frontend, subida da API, execução das 6 golden
  recipes (3 Gyroid + 3 Voronoi) duas vezes cada para checar determinismo por SHA-256, auditoria
  STL independente, inspeção visual manual e E2E Playwright — para ser executado pelo usuário em
  Windows; **nunca executado neste sandbox Linux** (sintaxe validada estaticamente apenas).
- **O que permanece real mas não provado neste sandbox**: qualquer execução de fato do
  `VoxelsFromImplicit`/`Mesh` do PicoGK sobre uma das 3 golden recipes Voronoi; determinismo
  geométrico real (dois SHA-256 de STL iguais); a auditoria STL independente rodando contra um
  STL real (hoje só provada contra fixtures sintéticas de teste); a inspeção visual no
  visualizador 3D; o E2E Playwright completo. Todos dependem da execução do roteiro acima em
  Windows pelo usuário — ver `TEST_EVIDENCE.md`, seção "Rodada Voronoi", para o registro
  detalhado do que foi e não foi provado nesta sessão.

## Incremento 2.3 (Rodada 1) — Fundação Canônica, Proveniência e Curadoria (branch `incremento-2.3-dados-cientificos`)

Objetivo desta rodada: tornar o sistema capaz de armazenar dado científico com proveniência
completa (fonte, data de acesso, método/condições, unidade, incerteza, licença, estado de
revisão) para materiais, biomateriais, substâncias químicas, fármacos, formulações,
nanomateriais, produtos de fornecedor, estruturas cristalográficas e evidência bibliográfica —
**sem** nenhuma coleta de dados externa nem importação em massa de bases reais. Essa parte
permanece explicitamente para uma rodada futura (ver `docs/data/SOURCE_REGISTRY_POLICY.md`).

- **12 novas entidades** (`apps/api/src/biomatcad_api/models/scientific_data.py`):
  `ScientificEntity`, `ScientificIdentifier`, `ScientificSource`, `BibliographicReference`,
  `PropertyDefinition`, `PropertyObservation`, `BiologicalEvidence`, `Supplier`,
  `SupplierProduct`, `CrystalStructureReference`, `IngestionRun`, `ReviewDecision`. Documentação
  detalhada do contrato em `docs/data/SCIENTIFIC_DATA_MODEL.md`.
- **Compatibilidade aditiva**: `MaterialRecord` (Incremento 2.1) ganha apenas uma coluna nova e
  nullable (`scientific_entity_id`), sempre `NULL` para registros pré-existentes, sem nenhum
  backfill. `GeometryJob.material_id` e `manifest_service.py` — os dois pontos que dependem de
  `MaterialRecord` — continuam absolutamente intocados. Nenhum endpoint/teste do Incremento
  2.1/2.2 foi alterado.
- **Migração real** (`alembic/versions/4920cd8fd160_...py`), verificada contra PostgreSQL real
  (nunca SQLite) em três cenários: banco vazio, banco já populado com um `MaterialRecord`
  pré-existente (preservado sem alteração), e downgrade completo e reversível.
- **Deduplicação por fingerprint determinístico** (SHA-256, `compute_observation_fingerprint`):
  a única forma de duas observações serem tratadas como "a mesma" é terem entidade, propriedade,
  fonte, valor, unidade, método e condições idênticos. Qualquer divergência gera um fingerprint
  diferente e as duas linhas coexistem — nunca há sobrescrita silenciosa de um valor científico
  divergente.
- **API mínima de pesquisa** (`routers/scientific_data.py`, prefixo
  `/api/v1/scientific-entities`): leitura com escopo por organização (registro global se
  `organization_id IS NULL`, privado caso contrário); escrita (criação de entidade) e revisão
  exigem `require_admin`, reaproveitando exatamente o mecanismo já existente em `routers/auth.py`.
  Criação de observação/identificador/fonte/referência/fornecedor/produto/estrutura
  cristalográfica **não** é exposta via API nesta rodada — só pelo seed sintético
  (`seed_scientific_data.py`), por instrução explícita de não construir ainda uma interface
  administrativa extensa.
- **Seed científico sintético** (`python -m biomatcad_api.seed_scientific_data`, idempotente):
  popula 5 entidades canônicas (uma de cada tipo obrigatório), 2 observações conflitantes de
  fontes sintéticas distintas para a mesma propriedade (nunca sobrescritas), 1 observação
  supplier_declared, 1 fornecedor+produto fictício, 1 referência bibliográfica fictícia, 1
  estrutura cristalográfica sintética, 1 execução de ingestão fictícia (nenhum conector real
  existe), e os três estados de curadoria (draft/reviewed/rejected). Nenhum DOI/PMID/CAS/CID/
  accession real é usado em nenhum lugar do seed.
- **O que permanece deliberadamente fora desta rodada**: qualquer conector de ingestão real
  contra PubChem/ChEBI/ChEMBL/Crossref/Europe PMC/PubMed/Crystallography Open Database/RCSB PDB
  ou bases de fornecedor; qualquer dado clínico ou de paciente real; qualquer interface
  administrativa extensa de curadoria; backfill de `MaterialRecord.scientific_entity_id` para
  registros existentes. Ver `ROADMAP.md` para o encadeamento sugerido de rodadas futuras.

## Próximo incremento sugerido

Ver `REQUIREMENTS_MATRIX.md`, `ROADMAP.md` e `docs/adr/` para prioridades. O Prompt Mestre
condiciona explicitamente o avanço à Fase 3 à vertical geométrica estar "realmente executável" —
isso ainda não é o caso (ADR-0007). O próximo incremento razoável é executar de fato
`apps/geometry-worker` em Windows (ver `docs/examples/WINDOWS_EXECUTION_KIT.md`) — ou
alternativamente investigar build nativo do PicoGK para linux-x64 —, confirmar determinismo
geométrico com o mesmo seed em duas execuções reais, rodar o E2E Playwright de ponta a ponta, e
só então carregar dados reais de materiais (AP-07: 32+ materiais com DOI) antes de avançar para
FEM/DICOM/LIMS/prontuário.
