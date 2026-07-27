# Arquitetura — BioMatCAD Nexus

Este documento descreve a arquitetura oficial (ADR-0002) e o que dela está realmente
implementado após o Incremento 1 da Fase 1. Para decisões e motivações, ver `docs/adr/`. Para
o inventário funcional item a item, ver `IMPLEMENTATION_STATUS.md`.

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
  duração (30 min por padrão). Sem refresh token, sem MFA, sem RBAC granular — isso é
  `PM-ONLY-04`, backlog.
- Estado operacional: tabela `operational_states` com os 4 estados do Prompt Mestre §3.2.
  Pesquisa habilitada por padrão; Laboratório/Piloto clínico/Produção clínica exigem uma
  chamada autenticada a `POST /api/v1/system/operational-state/activate` com a chave mestra
  configurada em `OPERATIONAL_STATE_MASTER_KEY` (nunca no cliente). Sem essa variável
  configurada, a ativação é sempre recusada (403) — inclusive em desenvolvimento.
- Auditoria: tabela `audit_events`, populada em login (sucesso/falha) e em tentativas de
  ativação de estado operacional (negadas ou concedidas). Append-only por convenção da camada
  de aplicação — não há garantia de imutabilidade a nível de infraestrutura ainda (Prompt
  Mestre §23.3 pede que isso fique explícito, não implícito).
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
