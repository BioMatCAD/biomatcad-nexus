# NOTICES — atribuições de software de terceiros

Este arquivo consolida, a nível de repositório, os componentes de terceiros incorporados ou
referenciados pelo código do BioMatCAD Nexus até o Incremento 2.1. A escolha da licença do
próprio projeto BioMatCAD Nexus permanece pendente — ver `LICENSE_PENDENTE.md`. Este arquivo
trata apenas das dependências de terceiros, que têm suas próprias licenças, independentemente
da decisão de licenciamento do projeto.

## apps/geometry-worker (C#/.NET)

- **PicoGK 2.2.0** — LEAP 71 — Apache License 2.0 —
  https://github.com/leap71/PicoGK — geometry kernel (voxelização, malha, formas implícitas).
  Referenciado via NuGet `PackageReference`, sem modificação nem redistribuição de binários
  neste repositório Git. O BioMatCAD Nexus **não** usa nem faz referência ao "Noyron" (software
  proprietário distinto, também da LEAP 71).
- **SkiaSharp** (dependência transitiva do PicoGK) — MIT — https://github.com/mono/SkiaSharp.
- **xunit / xunit.runner.visualstudio / Microsoft.NET.Test.Sdk** — testes do worker
  (`tests/BioMatCadGeometryWorker.Tests`) — Apache License 2.0 (xunit) / MIT (Test SDK).

Ver `apps/geometry-worker/NOTICE` para o detalhamento local deste componente.

## apps/api (Python)

- **FastAPI**, **Pydantic v2**, **SQLAlchemy 2.0**, **Alembic**, **PyJWT**, **passlib** — MIT.
- **jsonschema** (validação do schema BioMatCEM, `Draft202012Validator`) — MIT —
  https://github.com/python-jsonschema/jsonschema.
- **pgserver** (PostgreSQL real sem Docker/root, usado apenas em desenvolvimento/teste nesta
  sessão, não em produção) — MIT — https://pypi.org/project/pgserver/.

## apps/web (TypeScript/React)

- **React**, **React Router**, **Vite** — MIT.
- **three** 0.169.0 (novo no Incremento 2.1 — visualizador 3D de STL, `StlViewer.tsx`) — MIT —
  https://github.com/mrdoob/three.js. Integração direta (`WebGLRenderer`, `OrbitControls`),
  sem `@react-three/fiber`. Parser STL binário próprio (`src/lib/stlParser.ts`), sem
  dependência externa de loader.

## Documentos científicos-fonte

O algoritmo da superfície mínima periódica Gyroid (`GyroidImplicit.cs`,
`schemas/biomatcem/geometry-recipe-v1.schema.json`) é a fórmula matemática clássica publicada
por Alan Schoen (1970), de domínio público — não é derivada de nenhum software proprietário.

## Como manter este arquivo

Toda nova dependência de terceiros com licença própria (backend, frontend, worker) deve ser
adicionada aqui no incremento em que for introduzida, com nome, versão, licença e origem —
nunca deixado implícito no `package.json`/`.csproj`/`pyproject.toml` sozinho.
