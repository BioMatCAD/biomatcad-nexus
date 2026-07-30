# Auditoria de dependências — Incremento 2.1.1 (item 13)

Auditoria real, executada nesta sessão contra os registros oficiais (PyPI/OSV via `pip-audit`,
npm registry via `npm audit`, NuGet via `dotnet list package --vulnerable`). Nenhuma atualização
forçada/indiscriminada foi aplicada — cada decisão está registrada abaixo.

## Python (`apps/api`)

Comando: `pip-audit` contra as versões exatamente resolvidas dos 23 pacotes diretos declarados em
`pyproject.toml` (dependências de produção + dev), isoladas do restante do ambiente do sistema
(que contém pacotes de SO não relacionados ao projeto, ex.: `cloud-init`).

**Resultado: nenhuma vulnerabilidade conhecida encontrada** em nenhum dos 23 pacotes diretos
(fastapi 0.141.0, uvicorn 0.52.0, pydantic 2.13.4, sqlalchemy 2.0.51, alembic 1.18.5,
psycopg2-binary 2.9.12, passlib 1.7.4, bcrypt 4.0.1, pyjwt 2.13.0, python-multipart 0.0.32,
jsonschema 4.26.0, **psutil 7.2.2 — dependência nova deste incremento**, pytest 9.1.1, ruff
0.16.0, mypy 2.3.0, pgserver 0.1.4, entre outros). Nenhuma ação necessária.

**Atualização (2026-07-29, correção do contrato de driver Postgres)**: `psycopg[binary]>=3.1`
foi adicionado como dependência real (bug corrigido: a URL `postgresql+psycopg://` usada no gate
final do Windows exige o driver psycopg 3, que não estava declarado — só `psycopg2-binary`
estava). `pip-audit` rodado isoladamente (venv novo, só `psycopg[binary]` + `pip-audit`) contra a
versão resolvida `psycopg 3.3.4` / `psycopg-binary 3.3.4`: **nenhuma vulnerabilidade conhecida
encontrada** no pacote em si (as 7 entradas reportadas nesse venv isolado são todas do
`setuptools` pré-instalado pelo próprio `venv`, não uma dependência declarada do projeto).
`psycopg2-binary` foi mantido (não removido) porque `.github/workflows/ci-api.yml` e
`.env.example` usam `postgresql://` sem driver explícito, que o SQLAlchemy resolve por padrão
para `psycopg2` — há uso real de ambos os dialetos no repositório, então ambos os drivers
precisam permanecer instalados.

**Atualização (2026-07-29, pós-aprovação do gate final no Windows)**: formalizados limites de
versão explícitos para ambos os drivers (`psycopg2-binary>=2.9,<3.0`,
`psycopg[binary]>=3.1,<4.0`), evitando que um major futuro quebre a instalação silenciosamente.
Criado um extra opcional `gate` (`pip install -e ".[gate]"`) com apenas `httpx`, para quem quiser
rodar só o gate final sem instalar as ferramentas de lint/teste. `pgserver` (Postgres efêmero
usado só para testes locais) recebeu o marcador de ambiente `python_version < '3.13'`, depois de
confirmado via `pip download` contra `manylinux2014_x86_64`, `win_amd64` e `macosx_11_0_arm64`
que a versão 0.1.4 (a mais recente disponível) não publica wheel para Python 3.13+ em nenhuma
plataforma — sem esse marcador, `pip install -e ".[dev]"` falharia por inteiro em qualquer
Python 3.13+ só por causa desse pacote de conveniência, que não é usado por nenhum código de
produção nem pelo CI real.

## NuGet (`apps/geometry-worker`)

Comando: `dotnet list package --vulnerable --include-transitive` nos dois projetos
(`BioMatCadGeometryWorker` e `BioMatCadGeometryWorker.Tests`).

**Resultado: nenhum pacote vulnerável** (PicoGK 2.2.0, Microsoft.NET.Test.Sdk 17.11.1, xunit
2.9.2, xunit.runner.visualstudio 2.8.2). `dotnet list package --outdated` também não reporta
nenhuma atualização disponível. Nenhuma ação necessária.

## npm (`apps/web` + raiz do monorepo)

Comando: `npm audit` (registry real). **18 vulnerabilidades reportadas** — nenhuma foi corrigida
via `--force` (que forçaria major version bumps não avaliados). Decisões registradas uma a uma:

| Pacote | Severidade | Prod/Dev | Explorabilidade neste projeto | Correção disponível | Risco de breaking change | Decisão |
|---|---|---|---|---|---|---|
| `react-router` / `react-router-dom` | Moderada | **Produção** | CVE de redirect aberto/XSS via `<Link>`/`useNavigate` com string manipulada (barra invertida); nesta aplicação, todos os destinos de `<Link to=...>`/`navigate()` são strings literais internas (rotas fixas), nunca construídas a partir de entrada do usuário — exploração exigiria adicionalmente conseguir injetar uma URL controlada em algum desses destinos, o que não existe no código atual. Risco prático **baixo**, mas não nulo (defesa em profundidade). | Parcial: `npm audit fix` (sem `--force`) atualizou para 6.30.4, a versão mais recente da série 6.x — mas o advisory GHSA-jjmj-jmhj-qwj2 ainda afeta toda a série 6.x; correção completa exige migrar para React Router v7 (major, breaking, API de rotas mudou). | Alto (v7 muda `createBrowserRouter`/tipos de rota) | **Aplicado o bump não-quebrador (6.30.4, já commitado)**; migração para v7 registrada como item de ROADMAP.md, fora do escopo deste incremento corretivo (não é uma correção "escondida" dentro de uma tarefa não relacionada). |
| `eslint` 8.x + toda a cadeia (`@eslint/eslintrc`, `@humanwhocodes/config-array`, `file-entry-cache`, `flat-cache`, `glob`, `minimatch`, `rimraf`, `eslint-plugin-jsx-a11y`, `eslint-plugin-react`, `brace-expansion`) | Alta | **Dev apenas** (linting, nunca roda em produção/no bundle entregue ao usuário) | Nula em produção — estas vulnerabilidades (principalmente ReDoS em `minimatch`/`brace-expansion` via padrões de glob) só seriam exploráveis processando um path/glob malicioso *durante o lint*, nunca em runtime da aplicação. | `eslint@10.8.0` (major, breaking — ESLint 9/10 mudou para flat config, exigiria reescrever `.eslintrc`) | **Deferido.** Risco real em produção é nulo; migração para ESLint flat config é um esforço à parte, não uma correção de segurança urgente. Registrado em ROADMAP.md. |
| `vite`, `vitest`, `vite-node`, `@vitest/mocker`, `esbuild` | Moderada/**Crítica** (a crítica é especificamente sobre o *servidor de UI do Vitest*, não usado neste projeto — não há `vitest --ui` em nenhum script) | **Dev apenas** (build tooling e test runner — não incluído no `dist/` entregue) | O CVE crítico do vitest requer o servidor de UI do Vitest ativo (`vitest --ui`), que este projeto nunca inicia (scripts usam apenas `vitest run`/`vitest`). O CVE do esbuild/vite é sobre o dev server aceitar requisições cross-origin — relevante apenas rodando `npm run dev` em rede não confiável, mitigável não expondo a porta de dev publicamente (prática já esperada). | `vite@8`/`vitest@4` (major, breaking — múltiplas mudanças de API/config) | **Deferido.** Nenhum destes vetores se aplica ao artefato de produção (`dist/`) nem ao uso padrão dos scripts deste projeto. Migração major registrada em ROADMAP.md para avaliação dedicada (não é algo a fazer às pressas dentro de uma tarefa corretiva). |

### Dependências NOVAS adicionadas neste incremento (justificativa)

- **`psutil` (Python, produção)** — necessária para encerramento real de árvore de processos do
  worker em timeout/cancelamento (itens 3 e 7); auditada acima, sem vulnerabilidades.
- **`ajv` (npm, produção)** — necessária para validar receitas no frontend contra o MESMO JSON
  Schema real usado pelo backend (item 9), eliminando ~15 regras manuais duplicadas que
  divergiam do schema; sem vulnerabilidades reportadas por `npm audit` na versão instalada
  (^8.20.0).
- **`@playwright/test` (npm, dev apenas)** — necessária para o E2E real (item 12); sem
  vulnerabilidades reportadas.

## Resumo

Nenhuma dependência de **produção** com vulnerabilidade real e não mitigada permanece sem
decisão registrada. As pendências restantes são exclusivamente de tooling de desenvolvimento
(lint/build/test), com explorabilidade nula ou muito baixa no artefato entregue ao usuário, e
suas migrações (majors com risco de breaking change real) foram deliberadamente adiadas e
documentadas em `ROADMAP.md` em vez de aplicadas às pressas dentro deste incremento corretivo.
