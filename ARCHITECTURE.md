# Arquitetura — BioMatCAD Nexus

Este documento descreve a arquitetura oficial (ADR-0002) e o que dela está realmente
implementado após o Incremento 1.1 da Fase 1 (auditoria de consistência, segurança e
preservação de histórico — ver ADR-0004 e ADR-0005). Para decisões e motivações, ver
`docs/adr/`. Para o inventário funcional item a item, ver `IMPLEMENTATION_STATUS.md`.

## Visão geral

```text
apps/web  (React + TS + Vite)  ──HTTP/JSON──►  apps/api  (FastAPI)  ──SQL──►  PostgreSQL
                                                     │
                                                     ├── Redis (cache/locks/fila) — não usado ainda
                                                     ├── MinIO/S3 (artefatos) — não usado ainda
                                                     ├── geometry-worker (C#/.NET, PicoGK) — não implementado
                                                     └── compute-worker (Python científico) — não implementado
```

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

## O que ainda não existe

- `apps/geometry-worker` (C#/.NET, PicoGK/ShapeKernel) — apenas README.
- `apps/compute-worker` (FEM, imagem, ML, otimização) — apenas README.
- `packages/biomat-dsl`, `packages/scientific-core`, `packages/contracts`,
  `packages/fhir-mappings`, `packages/ui` — apenas README.
- Todos os `services/*` (identity/Keycloak, fhir, pacs, video, object-storage, observability).
- Todo o envelope clínico/laboratorial (`PM-ONLY-01/02/03/05`).
- RBAC/ABAC completo (`PM-ONLY-04` parcialmente iniciado: só há um `role` de string simples no
  modelo `User`, sem permissões por instituição/unidade/projeto).

## Próximo incremento sugerido

Ver `REQUIREMENTS_MATRIX.md` e `docs/adr/` para prioridades. O Prompt Mestre pede
explicitamente para não avançar ainda para DICOM/CAD/FEM/LIMS/prontuário — o próximo incremento
razoável é reforçar esta fundação (RBAC básico por organização, `packages/contracts` gerado a
partir do OpenAPI real já exposto em `/api/v1/openapi.json`, e um primeiro `Organization`/
`Project` CRUD) antes de iniciar o núcleo científico (Fase 2).
