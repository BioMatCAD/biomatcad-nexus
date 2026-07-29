# BioMatCAD Nexus

Plataforma integrada de engenharia computacional de biomateriais, laboratório, terapia celular
e saúde digital — projeto derivado do doutorado de Adler Lima Botelho de Azevedo
(PPGBiotec/UFBA) e do `Prompt_Mestre_BioMatCAD_Nexus.md`.

## Status real deste repositório (2026-07-29 — Incremento 2.1.1 da Fase 2, CORRETIVO, PARCIALMENTE BLOQUEADO)

O **Incremento 2.1.1** é uma correção de defeitos encontrados numa auditoria do Incremento 2.1
("Se o PicoGK não puder ser executado no sandbox, declare o incremento parcialmente bloqueado.
Não substitua silenciosamente o worker por geometria falsa." continua valendo). Ele não adiciona
funcionalidade nova de escopo — corrige, item a item, defeitos reais encontrados na vertical
geométrica entregue no Incremento 2.1: semântica ambígua de espessura/isovalor no schema, corte
por bounding box em vez do domínio real (cilindro), ausência de solda de vértices (bug que
produzia contagem de vértices divergente entre STL e manifesto), autorização entre organizações
insuficiente, condição de corrida na fila de jobs e no cancelamento, manifesto com risco de
circularidade de checksum, e validação de receita duplicada e divergente entre frontend e
backend. Todas essas correções estão **implementadas e testadas** nesta sessão — backend (83
testes pytest, 2 skips esperados sem `dotnet`/Windows), worker C# (50 testes xUnit, todos sobre
código independente do PicoGK), frontend (27 testes Vitest, `tsc`/`eslint`/build limpos).

**Atualização real**: o usuário executou de verdade o worker no seu Windows x64 contra a golden
recipe `block-gyroid-v1` -- sucesso real (ExitCode 0, PicoGK Core 26.2.0, STL watertight de
208.560 triângulos/102.338 vértices únicos, calibração de porosidade convergindo perto do
alvo). É a primeira geometria real gerada pelo PicoGK neste projeto inteiro. Essa execução
também revelou um segundo bug operacional real (viewer exigindo fechamento manual, inflando
`duration_seconds`), já corrigido nesta sessão com o parâmetro oficial `bEndAppWithTask: true`
(confirmado por reflexão contra o `PicoGK.dll` 2.2.0 real) -- ver `apps/geometry-worker/
WORKER_STATUS.md` §10/§10.1 para o relato completo.

**O que ainda falta**: por instrução explícita do usuário, `cylinder-gyroid-v1` e
`preview-gyroid-low-res-v1` deliberadamente ainda não foram executados nesta rodada.
Determinismo geométrico real (duas execuções, mesmo SHA-256), auditoria independente do STL
real contra o JSON do worker (o arquivo `.stl` em si ainda não foi devolvido para esta sessão),
e a execução E2E (Playwright) também permanecem pendentes. Para fechar esses itens, o usuário
continuará executando o worker real no seu próprio Windows x64 e devolvendo os resultados — ver
o guia completo em `docs/examples/WINDOWS_EXECUTION_KIT.md`. Ver `IMPLEMENTATION_STATUS.md` para o inventário
completo, critério de aceite por critério de aceite, do que está fechado vs. pendente dessa
execução.

O que existe de fato agora:

- Auditoria da Fase 0: `docs/SOURCE_DOCUMENTS.md`, `REQUIREMENTS_MATRIX.md`.
- ADRs de escopo e arquitetura: `docs/adr/0001-*.md` a `0008-*.md`.
- `apps/api`: FastAPI real, PostgreSQL via SQLAlchemy/Alembic (4 migrações), auth `DEV_AUTH`,
  estado operacional (Pesquisa/Laboratório/suíte clínica), materiais/projetos/receitas
  BioMatCEM/jobs geométricos/artefatos com autorização por organização e auditoria. **Incremento
  2.1.1**: verificação real cross-organização antes de criar um `DesignRun`, fila com claim
  atômico via `SELECT ... FOR UPDATE SKIP LOCKED`, cancelamento real com kill de árvore de
  processos e proteção de corrida, manifesto reestruturado com SHA-256 fora do próprio JSON —
  83 testes pytest coletados (2 skips esperados sem `dotnet`/Windows), ruff e mypy limpos.
- `schemas/biomatcem/`: schema JSON versionado da receita geométrica (`geometry-recipe-v1`) —
  **Incremento 2.1.1**: `wall_thickness_mm` agora obrigatório e único controlador de espessura,
  `isovalue` agora opcional (centro da banda, default 0.0), combinações contraditórias
  rejeitadas — ver ADR-0008. Golden recipes agora diretamente válidas contra o schema (metadados
  movidos para `METADATA.json` separado).
- `apps/geometry-worker`: worker C#/.NET9+PicoGK 2.2.0 — **compila com sucesso**; execução real
  **continua bloqueada** neste ambiente (sem runtime nativo linux-x64), com evidência completa em
  `WORKER_STATUS.md` e ADR-0007. **Incremento 2.1.1**: domínio real por interseção booleana de
  SDF (cilindro deixa de ser recortado pela bounding box), espessura/isovalor/porosidade/seed
  efetivamente aplicados, diferença real preview-vs-final, solda de vértices (`SimpleMesh.Weld()`)
  corrigindo a divergência de contagem de vértices da auditoria, validação pós-gravação do STL,
  limites computacionais pré-execução, timeout com kill de árvore de processos — 50 testes xUnit
  passando sobre o código matemático/contratual independente do PicoGK (`GyroidMath.cs`,
  `SimpleMesh`, `StlExporter`), nenhum contra PicoGK real.
- `apps/web`: React/TypeScript/Vite real — landing, login, dashboard, catálogo de materiais,
  projetos, editor de receita com validação ao vivo, acompanhamento de job, visualizador 3D via
  Three.js. **Incremento 2.1.1**: validação de receita unificada com Ajv contra uma cópia local
  sincronizada do schema real (com teste de sincronia byte-a-byte), fingerprint de demonstração
  corrigido (canonicalização recursiva real, documentado como NÃO sendo SHA-256 real) — 27 testes
  Vitest passando, `tsc`/`eslint`/build limpos. E2E Playwright escrito (`apps/web/e2e/`), mas
  **bloqueado neste sandbox** (faltam bibliotecas nativas do Chromium e `sudo` está desabilitado)
  — ver `apps/web/e2e/README.md`.
- `ARCHITECTURE.md`, `IMPLEMENTATION_STATUS.md` e `ROADMAP.md` — detalhamento técnico, evidências
  e priorização dos próximos passos (execução real do worker no Windows antes da Fase 3).
- `docs/examples/WINDOWS_EXECUTION_KIT.md` — guia passo a passo para o usuário compilar e
  executar `apps/geometry-worker` de verdade em Windows x64 (onde o PicoGK 2.2.0 tem runtime
  nativo oficial) e devolver os resultados para fechar os itens de aceite pendentes.
- `docs/security/DEPENDENCY_AUDIT_2.1.1.md` — auditoria de dependências Python/npm/NuGet;
  zero vulnerabilidades em Python/NuGet, 18 no npm (1 corrigida sem breaking change —
  react-router 6.26.2→6.30.4 —, 17 de tooling de desenvolvimento deferidas com justificativa,
  ver `ROADMAP.md`).
- `scripts/audit_stl_vs_worker_output.py` — recomputação independente (Python) de métricas de
  STL, para conferência cruzada contra a saída real do worker quando ela existir.
- `NOTICES.md` — atribuições de terceiros (PicoGK/Apache-2.0, three.js/MIT, etc.).
- `TEST_EVIDENCE.md` — log da revalidação completa, incluindo a seção do Incremento 2.1.1.
- Histórico Git completo preservado via `git bundle` (nunca reescrito — apenas novos commits
  acrescentados a cada incremento), verificado com `git bundle verify`.
- Estrutura de diretórios do monorepo para os módulos ainda não implementados (Seção 6 do
  Prompt Mestre), cada um com README explicando propósito e status.

## Chave mestra: semântica corrigida no Incremento 1.1

`OPERATIONAL_STATE_MASTER_KEY` é uma única chave compartilhada, nunca uma segunda por contexto.
Ela controla dois grupos **independentes e nunca combináveis**:

- **Contextos independentes** — `research` (ativo por padrão) e `laboratory` (inativo por
  padrão): cada um ativável isoladamente via `POST /api/v1/system/operational-state/activate`.
- **Suíte clínica** — `clinical_test`, `clinical_pilot`, `clinical_production`: só podem ser
  ativados/desativados **juntos**, atomicamente (uma transação, tudo ou nada), via
  `POST /api/v1/system/clinical-suite/activate` e `.../deactivate`. Exige papel administrativo,
  gera auditoria com estado anterior/novo/justificativa/identidade, e suporta expiração
  opcional. Ver ADR-0004 e `IMPLEMENTATION_STATUS.md` para os 7 cenários de teste.

## Autenticação: `DEV_AUTH`

A autenticação atual é classificada explicitamente como `DEV_AUTH` (exposta em
`GET /api/v1/system/status.auth_mode`) — adequada a desenvolvimento e demonstração com dados
sintéticos, **nunca para dados clínicos reais**. O processo recusa iniciar fora de
`ENVIRONMENT=test` se `API_SECRET_KEY` estiver ausente, for o valor padrão de dev, ou tiver
menos de 32 caracteres. OIDC/OAuth2.1+PKCE, MFA/WebAuthn, step-up authentication e RBAC/ABAC
completo permanecem como requisitos pendentes rastreados (`PM-ONLY-04a`–`04h` na matriz). Ver
ADR-0005.

## Restaurar o histórico Git completo a partir do bundle

O sandbox de desenvolvimento usado nesta sessão é efêmero — o histórico Git (13 commits) foi
preservado em `biomatcad-nexus-v2.2.bundle`:

```bash
git clone biomatcad-nexus-v2.2.bundle biomatcad-nexus
cd biomatcad-nexus
git log --oneline
```

Verifique a integridade do bundle antes de restaurar (opcional, mas recomendado):

```bash
git bundle verify biomatcad-nexus-v2.2.bundle
```

Verifique a integridade dos arquivos de entrega com `SHA256SUMS.txt`:

```bash
sha256sum -c SHA256SUMS.txt
```

## Por que o escopo é mais amplo que a tese de doutorado

O núcleo cientificamente validável (CAD 3D, FEM, banco de materiais, ML de predição biológica,
otimização multiobjetivo — requisitos `AP-*`/`TP-*` na matriz) vem diretamente da proposta de
tese e da apresentação de doutorado. Os módulos clínicos/laboratoriais (prontuário, FHIR,
telemedicina, LIMS, terapia celular — requisitos `PM-ONLY-*`) vêm exclusivamente do Prompt
Mestre, sem base nos documentos científicos. O usuário confirmou explicitamente que o escopo
completo deve ser seguido (ver `docs/adr/0001-escopo-completo-prompt-mestre.md`). Isso está
documentado para que ninguém confunda o escopo do software com o escopo do projeto de
doutorado aprovado pela banca/orientação.

## Estrutura

Ver árvore completa e propósito de cada diretório na Seção 6 do
`Prompt_Mestre_BioMatCAD_Nexus.md` e nos READMEs individuais de `apps/*`, `packages/*`,
`services/*`, `infra/*`, `data/*`, `tests/*`, `docs/*`.

## Quatro estados operacionais (Seção 3.2 do Prompt Mestre)

Todo módulo clínico/laboratorial deste sistema deve respeitar os quatro estados — Pesquisa,
Laboratório, Piloto clínico, Produção clínica — com uso clínico bloqueado por padrão até
aprovação institucional, ética, jurídica, de segurança e regulatória formal.

## Como executar hoje

### Backend (`apps/api`)

Requer PostgreSQL real acessível via `DATABASE_URL` (o `docker-compose.yml` deveria fornecer
isso, mas não foi validado em execução nesta sessão — ver `IMPLEMENTATION_STATUS.md`).

```bash
cd apps/api
pip install -e ".[dev]"
cp ../../.env.example .env   # ajuste DATABASE_URL, API_SECRET_KEY etc.
alembic upgrade head
python -m biomatcad_api.seed        # cria organização/usuário sintéticos
uvicorn biomatcad_api.main:app --reload
# docs interativas: http://localhost:8000/api/v1/docs
```

Login de desenvolvimento (seed sintético):
- Pesquisador: `demo@biomatcad.example` / `demo-synthetic-password-123`
- Admin (necessário para ativar Laboratório ou a suíte clínica): `admin@biomatcad.example` /
  `admin-synthetic-password-456`

Para testar a ativação da suíte clínica, defina `OPERATIONAL_STATE_MASTER_KEY` no `.env` do
backend, autentique-se como admin e chame
`POST /api/v1/system/clinical-suite/activate` com a chave e uma justificativa.

Rodar os testes (requer `TEST_DATABASE_URL` e `PG_ADMIN_URL` apontando para um Postgres real):

```bash
pytest -v
```

### Worker geométrico (`apps/geometry-worker`) — Incremento 2.1, corrigido no 2.1.1

```bash
cd apps/geometry-worker
dotnet build                                        # compila (0 erros esperados)
mkdir -p ~/Documents                                # PicoGK grava um log aqui
dotnet bin/Debug/net9.0/BioMatCadGeometryWorker.dll <job.json>
# Em linux-x64 sem runtime nativo: exit code 1, error_code=PICOGK_RUNTIME_UNAVAILABLE (esperado
# e documentado — ver apps/geometry-worker/WORKER_STATUS.md e ADR-0007). Sem mudança neste
# incremento corretivo: o bloqueio de runtime nativo em linux-x64 continua o mesmo.

cd tests/BioMatCadGeometryWorker.Tests
dotnet test                                          # 50/50 esperado, independe do PicoGK
```

**Execução real (Windows x64)**: para exercitar de verdade o PicoGK nativo — geração real do
scaffold Gyroid, domínio recortado pelo cilindro real, espessura/isovalor/porosidade/seed
efetivamente aplicados, determinismo — siga
`docs/examples/WINDOWS_EXECUTION_KIT.md` num Windows x64 real (única plataforma, junto de
`osx-arm64`, com runtime nativo oficial no pacote NuGet 2.2.0). Inclui
`apps/geometry-worker/tools/New-JobFromRecipe.ps1` (monta um `job.json` a partir de uma golden
recipe) e `scripts/audit_stl_vs_worker_output.py` (recomputa métricas do STL de forma
independente, para conferência cruzada).

### Dispatcher de jobs (processo separado da API) — corrigido no Incremento 2.1.1

```bash
cd apps/api
python scripts/geometry_dispatcher.py --once         # processa jobs QUEUED uma vez e sai
python scripts/geometry_dispatcher.py                # loop contínuo (Ctrl+C para parar)
```

Desde o Incremento 2.1.1, o claim de um job pela fila usa `SELECT ... FOR UPDATE SKIP LOCKED`
(atômico no PostgreSQL), substituindo o padrão anterior de ler-depois-atualizar, vulnerável a
dois dispatchers concorrentes reivindicarem o mesmo job — provado com dois processos/conexões
reais concorrentes contra Postgres real, zero duplicidade em 24 jobs (`test_geometry_job_
concurrency.py`). O dispatcher também emite heartbeat e recupera jobs órfãos (processo morto a
meio da execução).

### Frontend (`apps/web`)

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173, espera apps/api em localhost:8000
npm run test         # Vitest
npm run build         # build de produção
npm run build:pages   # build estático para GitHub Pages (dados sintéticos apenas)
# npm run test:e2e     # Playwright — BLOQUEADO neste sandbox (falta libXdamage.so.1 e sudo
#                        está desabilitado); ver apps/web/e2e/README.md. Rodar de verdade requer
#                        um ambiente com `npx playwright install --with-deps chromium` completo.
```

## Documentos de referência

- `Prompt_Mestre_BioMatCAD_Nexus.md` — especificação completa (fornecida pelo usuário).
- `docs/SOURCE_DOCUMENTS.md` — inventário e proveniência dos documentos-fonte científicos.
- `REQUIREMENTS_MATRIX.md` — matriz de requisitos rastreável.
- `docs/adr/` — decisões de arquitetura registradas, incluindo ADR-0007 (bloqueio do PicoGK em
  Linux) e ADR-0008, novo neste incremento (semântica espessura/isovalor do gyroid).
- `ARCHITECTURE.md` — arquitetura detalhada e o que dela está implementado.
- `IMPLEMENTATION_STATUS.md` — inventário real vs. demonstrativo vs. planejado, com evidências,
  incluindo o checklist dos 17 itens de aceite do Incremento 2.1.1 (o que está fechado vs.
  pendente de execução real no Windows).
- `docs/examples/WINDOWS_EXECUTION_KIT.md` — guia para o usuário executar o worker real em
  Windows x64 e devolver os resultados.
- `docs/security/DEPENDENCY_AUDIT_2.1.1.md` — auditoria de dependências e decisões registradas.
- `TEST_EVIDENCE.md` — log de evidência de teste, incluindo a seção do Incremento 2.1.1.
