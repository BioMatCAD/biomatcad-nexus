# NOTICES — atribuições de software de terceiros

Este arquivo consolida, a nível de repositório, os componentes de terceiros incorporados ou
referenciados pelo código do BioMatCAD Nexus até o Incremento 2.1.1 (corretivo sobre o
Incremento 2.1 — ver `IMPLEMENTATION_STATUS.md`). A escolha da licença do próprio projeto
BioMatCAD Nexus permanece pendente — ver `LICENSE_PENDENTE.md`. Este arquivo trata apenas das
dependências de terceiros, que têm suas próprias licenças, independentemente da decisão de
licenciamento do projeto.

## apps/geometry-worker (C#/.NET)

- **PicoGK 2.2.0** — LEAP 71 — Apache License 2.0 —
  https://github.com/leap71/PicoGK — geometry kernel (voxelização, malha, formas implícitas).
  Referenciado via NuGet `PackageReference`, sem modificação nem redistribuição de binários
  neste repositório Git. O BioMatCAD Nexus **não** usa nem faz referência ao "Noyron" (software
  proprietário distinto, também da LEAP 71). No Incremento 2.1.1, o código dependente de PicoGK
  ficou ainda mais isolado: `GyroidScaffoldBuilder.cs` (dependente) usa exclusivamente o núcleo
  matemático de `GyroidMath.cs` (independente, sem qualquer referência a `PicoGK.*`).
- **SkiaSharp** (dependência transitiva do PicoGK) — MIT — https://github.com/mono/SkiaSharp.
- **xunit / xunit.runner.visualstudio / Microsoft.NET.Test.Sdk** — testes do worker
  (`tests/BioMatCadGeometryWorker.Tests`, 62 testes no Incremento 2.1.1) — Apache License 2.0
  (xunit) / MIT (Test SDK).

Ver `apps/geometry-worker/NOTICE` para o detalhamento local deste componente.

## apps/api (Python)

- **FastAPI**, **Pydantic v2**, **SQLAlchemy 2.0**, **Alembic**, **PyJWT**, **passlib** — MIT.
- **jsonschema** (validação do schema BioMatCEM, `Draft202012Validator`) — MIT —
  https://github.com/python-jsonschema/jsonschema.
- **pgserver** (PostgreSQL real sem Docker/root, usado apenas em desenvolvimento/teste nesta
  sessão, não em produção) — MIT — https://pypi.org/project/pgserver/.
- **psutil** (novo no Incremento 2.1.1, encerramento real de árvore de processos do worker em
  timeout/cancelamento) — BSD 3-Clause — https://github.com/giampaolo/psutil. Auditado em
  `docs/security/DEPENDENCY_AUDIT_2.1.1.md`, sem vulnerabilidades conhecidas.

## apps/web (TypeScript/React)

- **React**, **React Router** (atualizado para 6.30.4 no Incremento 2.1.1 — correção
  não-quebradora de vulnerabilidade, ver `docs/security/DEPENDENCY_AUDIT_2.1.1.md`), **Vite** —
  MIT.
- **three** 0.169.0 (novo no Incremento 2.1 — visualizador 3D de STL, `StlViewer.tsx`;
  consolidado no Incremento 2.2 Alpha Pesquisa com controles completos, carregamento seguro e
  descarte de recursos — ver `docs/architecture/viewer-3d-audit.md`) — MIT —
  https://github.com/mrdoob/three.js. Integração direta (`WebGLRenderer`, `OrbitControls`),
  sem `@react-three/fiber`. Parser STL próprio (`src/lib/stlParser.ts`), estendido no
  Incremento 2.2 Alpha Pesquisa para também ler STL ASCII (além do binário original), sem
  nenhuma dependência externa de loader.
- **ajv** (novo no Incremento 2.1.1 — validação de receita BioMatCEM no frontend contra o schema
  real, `recipeValidationOffline.ts`) — MIT — https://github.com/ajv-validator/ajv. Substitui
  ~15 regras de validação manuais que divergiam do schema oficial.
- **@playwright/test** (novo no Incremento 2.1.1, dependência de desenvolvimento apenas — E2E,
  `apps/web/e2e/`) — Apache License 2.0 — https://github.com/microsoft/playwright.

## Documentos científicos-fonte

O algoritmo da superfície mínima periódica Gyroid (`apps/geometry-worker/GyroidMath.cs`,
aplicado via `GyroidDomainImplicit` em `GyroidScaffoldBuilder.cs`;
`schemas/biomatcem/geometry-recipe-v1.schema.json`) é a fórmula matemática clássica publicada
por Alan Schoen (1970), de domínio público — não é derivada de nenhum software proprietário. As
formulações de distância assinada de bloco/cilindro e a técnica de interseção booleana implícita
por `max()` (`GyroidMath.cs`) seguem a técnica padrão e amplamente publicada de "campos de
distância" para modelagem implícita (ex.: Inigo Quilez, "distance functions") — técnica pública,
não proprietária, não atribuída a nenhum software específico.

## Como manter este arquivo

Toda nova dependência de terceiros com licença própria (backend, frontend, worker) deve ser
adicionada aqui no incremento em que for introduzida, com nome, versão, licença e origem —
nunca deixado implícito no `package.json`/`.csproj`/`pyproject.toml` sozinho.
