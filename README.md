# BioMatCAD Nexus

Plataforma integrada de engenharia computacional de biomateriais, laboratório, terapia celular
e saúde digital — projeto derivado do doutorado de Adler Lima Botelho de Azevedo
(PPGBiotec/UFBA) e do `Prompt_Mestre_BioMatCAD_Nexus.md`.

## Status real deste repositório (2026-07-29 — Incremento 2.1 da Fase 2, PARCIALMENTE BLOQUEADO)

O Incremento 2.1 entrega a primeira vertical funcional do núcleo científico: material
documentado → projeto → receita BioMatCEM → job geométrico → worker C#/PicoGK → scaffold Gyroid
→ métricas → artefatos → visualização 3D. Schema versionado, modelos de dados (9 entidades),
orquestração de job via fila Postgres, API com autorização por organização e frontend completo
(catálogo, editor de receita, visualizador 3D via Three.js) estão **reais e testados** (65
testes de backend coletados, 17 de frontend, 9 de C#). O worker C#/.NET9+PicoGK 2.2.0
**compila** mas sua **execução real está bloqueada** neste ambiente — o pacote oficial não traz
runtime nativo para linux-x64, confirmado por evidência real (`DllNotFoundException`
reproduzida, ver ADR-0007 e `apps/geometry-worker/WORKER_STATUS.md`). Por isso este incremento é
entregue **parcialmente bloqueado**, não concluído — a Fase 3 não deve começar até essa vertical
estar realmente executável. Ver `IMPLEMENTATION_STATUS.md` para o inventário completo com
evidências desta sessão.

O que existe de fato agora:

- Auditoria da Fase 0: `docs/SOURCE_DOCUMENTS.md`, `REQUIREMENTS_MATRIX.md`.
- ADRs de escopo e arquitetura: `docs/adr/0001-*.md` a `0007-*.md`.
- `apps/api`: FastAPI real, PostgreSQL via SQLAlchemy/Alembic (3 migrações), auth `DEV_AUTH`,
  estado operacional (Pesquisa/Laboratório/suíte clínica), **materiais/projetos/receitas
  BioMatCEM/jobs geométricos/artefatos (Incremento 2.1)** com autorização por organização e
  auditoria — 65 testes pytest coletados (64 executados + 1 skip esperado sem `dotnet`).
- `schemas/biomatcem/`: schema JSON versionado da receita geométrica (`geometry-recipe-v1`),
  golden recipes, validação estrita (nenhum código executável aceito) — ver ADR-0006.
- `apps/geometry-worker`: worker C#/.NET9+PicoGK 2.2.0 — **compila com sucesso**; execução real
  **bloqueada** neste ambiente (sem runtime nativo linux-x64), com evidência completa em
  `WORKER_STATUS.md` e ADR-0007. 9 testes xunit passando sobre o código independente do PicoGK.
- `apps/web`: React/TypeScript/Vite real — landing, login, dashboard, **catálogo de materiais,
  projetos, editor de receita com validação ao vivo, acompanhamento de job, visualizador 3D via
  Three.js (Incremento 2.1)**, modo demonstração para GitHub Pages com STL sintético rotulado —
  17 testes Vitest passando, build normal e build de demo executados com sucesso.
- `ARCHITECTURE.md`, `IMPLEMENTATION_STATUS.md` e `ROADMAP.md` — detalhamento técnico, evidências
  e priorização dos próximos passos (desbloqueio do worker antes da Fase 3).
- `NOTICES.md` — atribuições de terceiros (PicoGK/Apache-2.0, three.js/MIT, etc.).
- `TEST_EVIDENCE.md` — log bruto da revalidação completa desta sessão.
- Histórico Git completo preservado em `biomatcad-nexus-v2.2.bundle`, verificado com
  `git bundle verify`.
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

### Worker geométrico (`apps/geometry-worker`) — Incremento 2.1

```bash
cd apps/geometry-worker
dotnet build                                        # compila (0 erros esperados)
mkdir -p ~/Documents                                # PicoGK grava um log aqui
dotnet bin/Debug/net9.0/BioMatCadGeometryWorker.dll <job.json>
# Em linux-x64 sem runtime nativo: exit code 1, error_code=PICOGK_RUNTIME_UNAVAILABLE (esperado
# e documentado — ver apps/geometry-worker/WORKER_STATUS.md e ADR-0007).

cd tests/BioMatCadGeometryWorker.Tests
dotnet test                                          # 9/9 esperado, independe do PicoGK
```

### Dispatcher de jobs (processo separado da API) — Incremento 2.1

```bash
cd apps/api
python scripts/geometry_dispatcher.py --once         # processa jobs QUEUED uma vez e sai
python scripts/geometry_dispatcher.py                # loop contínuo (Ctrl+C para parar)
```

### Frontend (`apps/web`)

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173, espera apps/api em localhost:8000
npm run test         # Vitest
npm run build         # build de produção
npm run build:pages   # build estático para GitHub Pages (dados sintéticos apenas)
```

## Documentos de referência

- `Prompt_Mestre_BioMatCAD_Nexus.md` — especificação completa (fornecida pelo usuário).
- `docs/SOURCE_DOCUMENTS.md` — inventário e proveniência dos documentos-fonte científicos.
- `REQUIREMENTS_MATRIX.md` — matriz de requisitos rastreável.
- `docs/adr/` — decisões de arquitetura registradas.
- `ARCHITECTURE.md` — arquitetura detalhada e o que dela está implementado.
- `IMPLEMENTATION_STATUS.md` — inventário real vs. demonstrativo vs. planejado, com evidências.
