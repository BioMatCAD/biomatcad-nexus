# BioMatCAD Nexus

Plataforma integrada de engenharia computacional de biomateriais, laboratório, terapia celular
e saúde digital — projeto derivado do doutorado de Adler Lima Botelho de Azevedo
(PPGBiotec/UFBA) e do `Prompt_Mestre_BioMatCAD_Nexus.md`.

## Status real deste repositório (2026-07-27 — Incremento 1.1 da Fase 1)

Backend (`apps/api`) e frontend (`apps/web`) têm uma fundação **real e executável**: login,
dashboard autenticado, health/status da API, modelos de dados com migrações aplicadas contra
PostgreSQL de verdade, 25 testes de backend e 7 de frontend passando. O Incremento 1.1 corrigiu
um bug de semântica na chave mestra (suíte clínica vs. Laboratório, ver ADR-0004), classificou a
autenticação como `DEV_AUTH` (ADR-0005) e preservou o histórico Git completo em bundle. Nenhum
módulo científico (CAD/FEM/materiais/ML) ou clínico/laboratorial foi implementado ainda. Ver
`IMPLEMENTATION_STATUS.md` para o inventário completo (real vs. demonstrativo vs. planejado) com
os comandos e evidências de execução desta sessão — Seção 3.1 do Prompt Mestre: nada é chamado
de "completo" sem ter sido executado e testado.

O que existe de fato agora:

- Auditoria da Fase 0: `docs/SOURCE_DOCUMENTS.md`, `REQUIREMENTS_MATRIX.md`.
- ADRs de escopo e arquitetura: `docs/adr/0001-*.md` a `0005-*.md`.
- `apps/api`: FastAPI real, PostgreSQL via SQLAlchemy/Alembic (2 migrações), auth `DEV_AUTH`
  (JWT, com recusa de startup fora de teste se o segredo for inseguro), contrato de chave mestra
  corrigido — Pesquisa/Laboratório independentes, suíte clínica (teste+piloto+produção) atômica
  — seed sintético (pesquisador + admin) — 25 testes pytest passando.
- `apps/web`: React/TypeScript/Vite real — landing, login, dashboard autenticado mostrando
  Laboratório e suíte clínica separadamente, tema claro/escuro, modo demonstração para GitHub
  Pages — 7 testes Vitest passando, build normal e build de demo executados com sucesso.
- `ARCHITECTURE.md` e `IMPLEMENTATION_STATUS.md` — detalhamento técnico e evidências.
- `TEST_EVIDENCE.md` — log bruto da revalidação completa do Incremento 1.1.
- Histórico Git completo preservado em `biomatcad-nexus-v2.1.bundle` (13 commits, verificado
  com `git bundle verify`).
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
preservado em `biomatcad-nexus-v2.1.bundle`:

```bash
git clone biomatcad-nexus-v2.1.bundle biomatcad-nexus
cd biomatcad-nexus
git log --oneline
```

Verifique a integridade do bundle antes de restaurar (opcional, mas recomendado):

```bash
git bundle verify biomatcad-nexus-v2.1.bundle
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
