# Status de Implementação — BioMatCAD Nexus

Última atualização: 2026-07-29 (Incremento 2.1 da Fase 2 — primeira vertical funcional do
núcleo BioMatCAD, entregue **parcialmente bloqueada** por ausência de runtime nativo do PicoGK
em linux-x64; ver seção dedicada abaixo e ADR-0007). Este documento existe para que ninguém —
incluindo IAs de desenvolvimento futuras — precise adivinhar o que é real. Regra do Prompt
Mestre §3.1: nada aqui é descrito como "completo" sem ter sido executado e testado nesta sessão.

## Legenda

- **Real**: código existe, foi executado nesta sessão, com evidência de teste/execução abaixo.
- **Demonstrativo**: existe e roda, mas é uma simulação (dados sintéticos, sem lastro real).
- **Planejado**: aparece em README/roadmap, sem nenhuma linha de código.

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
| `apps/geometry-worker` — contrato C#/.NET9+PicoGK 2.2.0 | Real (compila); **execução real BLOQUEADA** (linux-x64 sem runtime nativo) | `WORKER_STATUS.md`, ADR-0007, 9 testes xunit sobre código independente de PicoGK |
| `apps/web` — catálogo de materiais, projetos, editor de receita, jobs, visualizador 3D (Three.js) | Real | 17 testes Vitest; build normal e de demo executados |
| `scripts/geometry_dispatcher.py` — processo separado da API | Real (contrato); execução de sucesso depende do worker bloqueado | inspeção de código + teste do caminho de falha real

## Incremento 2.1 (Fase 2) — vertical geométrica funcional do núcleo BioMatCAD

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
| 1 | Estado inicial: os 3 flags clínicos desabilitados | `test_initial_state_all_three_clinical_flags_disabled` | PASSED |
| 2 | Ativação conjunta habilita os 3 | `test_activation_enables_all_three_flags_atomically` | PASSED |
| 3 | Desativação conjunta desabilita os 3 | `test_deactivation_disables_all_three_flags_atomically` | PASSED |
| 4 | Tentativa por usuário não autorizado | `test_activation_denied_for_non_admin_user` | PASSED |
| 5 | Rollback completo em caso de falha | `test_activation_rolls_back_completely_on_failure` (via monkeypatch forçando exceção no meio da transação) | PASSED |
| 6 | Expiração | `test_clinical_suite_expiration_is_respected` | PASSED |
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
