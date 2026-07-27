# Status de Implementação — BioMatCAD Nexus

Última atualização: 2026-07-27 (Incremento 1 da Fase 1). Este documento existe para que ninguém
— incluindo IAs de desenvolvimento futuras — precise adivinhar o que é real. Regra do Prompt
Mestre §3.1: nada aqui é descrito como "completo" sem ter sido executado e testado nesta sessão.

## Legenda

- **Real**: código existe, foi executado nesta sessão, com evidência de teste/execução abaixo.
- **Demonstrativo**: existe e roda, mas é uma simulação (dados sintéticos, sem lastro real).
- **Planejado**: aparece em README/roadmap, sem nenhuma linha de código.

## Resumo por módulo

| Módulo | Status | Evidência |
|---|---|---|
| `apps/api` — health/ready/version | Real | ver seção "Backend" abaixo |
| `apps/api` — auth (login/me) | Real (mínima — sem MFA/refresh) | testes + smoke test abaixo |
| `apps/api` — estado operacional + chave mestra | Real | testes + smoke test abaixo |
| `apps/api` — modelos + migração Alembic | Real | migração aplicada contra PostgreSQL real |
| `apps/api` — seed sintético | Real | executado, ver log abaixo |
| `apps/web` — landing/login/dashboard | Real | build + testes abaixo |
| `apps/web` — modo demo (GitHub Pages) | Demonstrativo (por design) | build `build:pages` executado |
| `docker-compose.yml` | Não testado neste ambiente | ver "Limitações do ambiente" |
| CAD/FEM/materiais/ML/otimização | Planejado | nenhum código |
| LIMS/ELN/terapia celular/clínica/telemedicina | Planejado | nenhum código (escopo confirmado, ver ADR-0003) |
| RBAC/ABAC completo, Keycloak/OIDC | Planejado | modelo `User.role` é uma string simples |

## Limitações do ambiente desta sessão

O sandbox de execução usado para desenvolver e testar este incremento **não tinha Docker nem
privilégios de root disponíveis**. Consequências diretas:

1. `docker-compose.yml` (Postgres/Redis/MinIO) foi validado apenas por parse de sintaxe YAML
   (`python -c "import yaml; yaml.safe_load(...)"`), nunca efetivamente executado com
   `docker compose up`. Isso é uma limitação do ambiente de desenvolvimento desta sessão, não
   uma afirmação de que o compose funciona — precisa ser validado por alguém com Docker.
2. Para testar a API contra um banco real sem Docker, foi usado
   [`pgserver`](https://pypi.org/project/pgserver/) (binários oficiais do PostgreSQL 16,
   redistribuídos como pacote Python, executáveis sem root). Isso permitiu testes de migração e
   conexão genuínos contra Postgres real — não é um mock nem SQLite disfarçado — mas o caminho
   de inicialização (`pg_ctl start` manual) é diferente do `docker-compose.yml` do repositório.
3. Processos em background não sobrevivem entre chamadas de shell distintas neste ambiente
   (cada chamada roda em um namespace isolado nesta sessão) — por isso toda sequência
   start-Postgres → migrar → testar → seed → parar-Postgres precisou ser feita dentro de uma
   única invocação de shell corrida do início ao fim.
4. O workflow `deploy-pages.yml` foi escrito e validado apenas sintaticamente (YAML), nunca
   executado contra um repositório GitHub real — não há repositório remoto conectado a esta
   sessão.

## Backend — comandos executados e resultado

Ambiente: `ENVIRONMENT=test`, banco `postgresql://postgres@127.0.0.1:5433/biomatcad` (dados) e
`.../biomatcad_test` (testes), servidor Postgres 16.2 iniciado via `pgserver`/`pg_ctl` nesta
sessão.

```text
$ ruff check .
All checks passed!

$ mypy src
Success: no issues found in 21 source files

$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 927e185f097d,
      modelos iniciais: organizations, users, operational_states, audit_events

$ pytest -v
tests/test_auth_and_operational_state.py::test_login_rejects_wrong_password PASSED
tests/test_auth_and_operational_state.py::test_login_succeeds_and_returns_token PASSED
tests/test_auth_and_operational_state.py::test_operational_state_activation_denied_without_master_key PASSED
tests/test_auth_and_operational_state.py::test_operational_state_activation_succeeds_with_correct_master_key PASSED
tests/test_db_connection.py::test_can_execute_simple_query PASSED
tests/test_health.py::test_health_ok PASSED
tests/test_health.py::test_ready_reports_database_connected PASSED
tests/test_health.py::test_version PASSED
tests/test_migrations.py::test_alembic_upgrade_head_runs_cleanly_on_empty_database PASSED
tests/test_system_status.py::test_system_status_defaults_only_research_enabled PASSED
======================== 10 passed, 1 warning in 4.27s =========================

$ python -m biomatcad_api.seed
Seed sintético aplicado: organização='demo-biomatcad', usuário='demo@biomatcad.example'

$ python - <<'PY'   # smoke test via TestClient contra o app real
GET  /health                                    -> 200 {"status": "ok"}
GET  /ready                                     -> 200 {"status": "ok", "database": "connected"}
GET  /version                                   -> 200 {"version": "0.1.0", "environment": "test"}
GET  /api/v1/system/status                      -> 200 {clinical_suite_enabled: false, research: true, demais: false}
POST /api/v1/auth/login                         -> 200 {token_type: "bearer", expires_in: 1800}
GET  /api/v1/auth/me                            -> 200 {email: "demo@biomatcad.example", role: "researcher", ...}
POST /api/v1/system/operational-state/activate  -> 403 (sem OPERATIONAL_STATE_MASTER_KEY configurada)
PY

$ python -c "... SELECT table_name FROM information_schema.tables ..."
['alembic_version', 'audit_events', 'operational_states', 'organizations', 'users']
```

## Frontend — comandos executados e resultado

```text
$ npm install --no-audit --no-fund --prefer-offline
added 426 packages in 27s

$ npm run typecheck        # tsc --noEmit
(sem erros)

$ npm run lint              # eslint . --max-warnings=0
(sem erros)

$ npx vitest run
✓ tests/Login.test.tsx (2 tests)
✓ tests/Dashboard.test.tsx (1 test)
✓ tests/apiClient.test.ts (2 tests)
✓ tests/Landing.test.tsx (1 test)
Test Files  4 passed (4) | Tests  6 passed (6)

$ npm run build              # build de produção (base "/")
dist/index.html                   0.64 kB
dist/assets/index-*.css           1.77 kB
dist/assets/index-*.js          180.59 kB
✓ built in 1.60s

$ npm run build:pages        # build de demonstração (base "/biomatcad-nexus/")
dist/index.html                   0.67 kB
dist/assets/index-*.css           1.77 kB
dist/assets/index-*.js          180.96 kB
✓ built in 1.61s
# index.html gerado referencia corretamente /biomatcad-nexus/assets/... (basename OK)

$ npx vite preview --port 4173 --strictPort &
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:4173/biomatcad-nexus/
200
# <title>BioMatCAD Nexus</title> confirmado no HTML servido
```

### O que os testes de frontend cobrem (e o que não cobrem)

- **Cobrem**: renderização da Landing, formulário de login (preenchimento + erro de credenciais
  inválidas via `fetch` mockado), smoke test do Dashboard (carrega, mostra estado vazio de
  projetos), cliente de API (sucesso e erro tipado).
- **Não cobrem**: fluxo E2E real de navegador (Playwright) — não configurado neste incremento.
  Os testes acima são testes de componente (Vitest + Testing Library + jsdom), não testes de
  navegador real. O "smoke test da landing/login/dashboard" pedido foi entregue nesse nível
  (componente) mais uma verificação HTTP real do build servido (`vite preview` + `curl`), não
  como testes Playwright de ponta a ponta — isso é uma lacuna conhecida, não uma alegação de
  cobertura E2E completa.

## Contrato de chave mestra — o que foi e não foi implementado

Implementado: endpoint `POST /api/v1/system/operational-state/activate`, autenticado, que exige
`OPERATIONAL_STATE_MASTER_KEY` configurada no ambiente do backend; sem essa variável, a resposta
é sempre `403` (testado). Toda tentativa (negada ou concedida) gera `AuditEvent`.

Não implementado (backlog, `PM-ONLY-04`): rotação de chave mestra, expiração de chave,
segregação de chave por instituição/unidade, "break glass" com prazo e revogação automática,
qualquer UI de administração para essa ativação (hoje só existe a chamada de API).

## Como executar hoje

Ver `README.md` (seção atualizada) para os comandos completos de backend e frontend. Resumo:

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
execução nesta sessão — ver "Limitações do ambiente" acima. Se você tiver Docker disponível,
rode `docker compose up -d` e reporte se funcionar como esperado; isso não foi confirmado aqui.
