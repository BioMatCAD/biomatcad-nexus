# Guia rápido de execução no Windows -- Incremento 2.2 Alpha Pesquisa

Este guia cobre como restaurar e executar o BioMatCAD Nexus no Windows para fins de pesquisa.
**Sistema exclusivamente de pesquisa: nunca use dados clínicos reais, nunca use para
diagnóstico ou decisão de tratamento.**

## 1. Restaurar o repositório a partir do bundle

```powershell
git clone biomatcad-nexus-v2.2-final.bundle biomatcad-nexus
cd biomatcad-nexus
git checkout incremento-2.2-alpha-pesquisa
git log --oneline -5
git tag
# deve listar: incremento-2.1-base, incremento-2.1.1-final,
#              incremento-2.1.1-v2.2.1, incremento-2.2-alpha-pesquisa-final
```

## 2. Pré-requisitos

- .NET 9 SDK (worker de geometria, PicoGK)
- Python 3.10+ (API)
- Node.js 18+ (frontend)
- PostgreSQL real acessível via `DATABASE_URL` (não SQLite fora de testes)
- PowerShell 7+ (scripts em `scripts/`)

## 3. Backend (API)

```powershell
cd apps\api
pip install -e ".[dev]"
alembic upgrade head
python -m biomatcad_api.seed
uvicorn biomatcad_api.main:app --reload
```

Variáveis mínimas: `DATABASE_URL`, `API_SECRET_KEY` (>= 32 caracteres, nunca o valor padrão de
desenvolvimento fora de `ENVIRONMENT=test`), `ENVIRONMENT`.

## 4. Worker de geometria (C#/PicoGK)

```powershell
cd apps\geometry-worker
dotnet build -c Release
dotnet test  # BioMatCadGeometryWorker.Tests + BioMatCadGeometryWorker.TopologyProviderTests
```

A execução real de geometria (`Library.Go` do PicoGK) só funciona em Windows x64 com o runtime
nativo do PicoGK disponível -- é o único caminho que não pode ser reproduzido no sandbox Linux
usado para desenvolver este incremento.

## 5. Frontend

```powershell
cd apps\web
npm install
npm run dev
```

## 6. Gate final real (opcional, confirmatório)

O gate final real (`scripts/Run-FinalGate.ps1`) já foi executado e aprovado em rodadas
anteriores deste incremento (ver `TEST_EVIDENCE.md`). Reexecutá-lo **não é obrigatório** para
aceitar o Incremento 2.2 (ver `ROADMAP.md` seção "Fase G" para a justificativa completa), mas
está disponível como confirmação adicional de que as correções de resiliência da Fase D
(checksum recalculado, tratamento de STL vazio) não alteraram o caminho feliz já aprovado:

```powershell
.\scripts\Run-FinalGate.ps1 -RepoPath <caminho-do-repo-clonado> -BundlePath <caminho-do-bundle>
```

## 7. Executar os testes de resiliência/segurança/DesignAdvisor novos desta rodada

Já cobertos pela suíte padrão do backend (`pytest`, dentro de `apps/api`, com `TEST_DATABASE_URL`
apontando para um Postgres real). Não requerem nada específico do Windows -- são testes Python
puros com dublês de worker, já verificados no sandbox Linux com 259 testes passando.

## 8. Limitações conhecidas neste incremento

- Launcher/instalador clínico completo: deliberadamente **não implementado** nesta rodada
  (protótipo técnico deferido para a fase clínica).
- RBAC/ABAC completo (17 perfis, OIDC, MFA, revogação de sessão): fora de escopo
  (`PM-ONLY-04e/f/g/h`).
- 7 dos 11 avisos de `npm audit` permanecem, todos exigindo migração major
  (Vitest 4, Vite 8, React Router 7) -- planejada, não urgente, ver
  `docs/security/DEPENDENCY_AUDIT_2.2.md`.
- FEM, DICOM, banco de dados científico populado, módulo farmacêutico customizado,
  integração hospitalar, validação clínica: fora de escopo deste incremento.
- Sistema nunca deve ser usado com dados clínicos reais, independentemente do estado
  operacional de qualquer módulo.
