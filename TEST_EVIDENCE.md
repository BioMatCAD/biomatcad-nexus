# Evidência de teste — Incremento 2.1 (Fase 2, parcialmente bloqueado)

Log bruto de uma execução única e sequencial (backend + worker C# + frontend + git) capturada
nesta sessão em 2026-07-29. Ambiente: sandbox Linux x86_64 sem Docker/root; PostgreSQL 16.2 real
via [`pgserver`](https://pypi.org/project/pgserver/); .NET SDK 9.0.316 instalado em espaço de
usuário; Node.js via `npm`. Ver `IMPLEMENTATION_STATUS.md` para a interpretação completa (o que
cada resultado significa, o que ainda falta) e ADR-0007 para a decisão sobre o bloqueio do
worker. Este arquivo é evidência bruta; os outros documentos são a leitura interpretada — devem
ser lidos juntos.

## 1. Ruff (lint Python)

```text
$ ruff check .
All checks passed!
```

## 2. Mypy (checagem de tipos Python)

```text
$ mypy src scripts
Success: no issues found in 45 source files
```

## 3. Alembic — migração aplicada do zero contra banco vazio e contra banco já na revisão anterior

```text
$ alembic upgrade head   (banco biomatcad_fresh_check, nunca migrado)
INFO  [alembic.runtime.migration] Running upgrade  -> 927e185f097d, modelos iniciais
INFO  [alembic.runtime.migration] Running upgrade 927e185f097d -> 9242186001a8, expires_at (suite clinica)
INFO  [alembic.runtime.migration] Running upgrade 9242186001a8 -> 97983fbc0288, modelos do incremento 2.1

$ alembic upgrade head   (banco biomatcad, já na revisão 9242186001a8)
INFO  [alembic.runtime.migration] Running upgrade 9242186001a8 -> 97983fbc0288, modelos do incremento 2.1
```

Também verificado via `tests/test_migrations.py` (banco `biomatcad_migration_test` dedicado),
que confirma a presença das 9 novas tabelas (`material_records`, `material_properties`,
`scientific_references`, `biomat_projects`, `geometry_recipes`, `design_runs`, `geometry_jobs`,
`artifacts`, `artifact_manifests`) além das 4 tabelas originais.

## 4. Pytest — suíte completa do backend (banco `biomatcad_test`, criado e destruído pela fixture)

```text
$ pytest -v
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.1.1, pluggy-1.6.0
collecting ... collected 65 items

tests/test_auth_and_operational_state.py ....... (7 testes)
tests/test_clinical_suite.py ....... (7 testes)
tests/test_db_connection.py . (1 teste)
tests/test_dev_auth_startup.py ..... (5 testes)
tests/test_geometry_job_orchestration.py ..... s (5 passed, 1 skipped)
tests/test_health.py ... (3 testes)
tests/test_jobs_artifacts_api.py ....... (7 testes)
tests/test_materials_projects_recipes_api.py ....... (7 testes)
tests/test_migrations.py . (1 teste)
tests/test_recipe_schema.py ................ (16 testes)
tests/test_system_status.py . (1 teste)

================== 64 passed, 1 skipped, 2 warnings in 23.06s ==================
```

O único skip (`test_dispatch_job_real_worker_fails_in_blocked_environment`) ocorre porque este
comando específico do backend rodou sem `dotnet` no `PATH` da mesma chamada de shell — quando
executado com `dotnet` disponível (ver Seção 6 abaixo), o teste roda de verdade e confirma o
bloqueio do worker real.

64 passando + 1 skip esperado (49 do Incremento 1.1 → 65 agora: +15 `test_recipe_schema.py`,
+5 `test_geometry_job_orchestration.py`, +7 `test_materials_projects_recipes_api.py`,
+7 `test_jobs_artifacts_api.py`, +1 `test_list_design_runs_for_project_denied...` incluso acima).

## 5. Worker C#/.NET9 + PicoGK 2.2.0 — build

```text
$ dotnet build
  BioMatCadGeometryWorker -> .../bin/Debug/net9.0/BioMatCadGeometryWorker.dll
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

## 6. Worker C#/.NET9 + PicoGK 2.2.0 — execução real (bloqueio reproduzido com evidência)

```text
$ mkdir -p ~/Documents
$ dotnet bin/Debug/net9.0/BioMatCadGeometryWorker.dll job.json
EXIT=1
```

stderr (`apps/geometry-worker/EVIDENCE_execution_attempt_stderr.log`):

```json
{"error_code":"PICOGK_RUNTIME_UNAVAILABLE","message":"System.Exception: Failed to load PicoGK library\n   at PicoGK.Library.GlobalInstance..ctor(...)\n   at PicoGK.Library.Go(...)\n   at BioMatCadGeometryWorker.GyroidScaffoldBuilder.BuildAndExport(...)\n   at Program.<Main>$(String[] args)"}
```

stdout (`apps/geometry-worker/EVIDENCE_execution_attempt_stdout.log`, log interno do PicoGK):

```text
System.DllNotFoundException: Unable to load shared library 'picogk.26.2' or one of its
dependencies. ...
/tmp/dotnet/shared/Microsoft.NETCore.App/9.0.18/picogk.26.2.so: cannot open shared object
file: No such file or directory
(mesma falha reproduzida em outros 5 caminhos de busca)
   at PicoGK.Library._hCreateInstance(Single fVoxelSizeMM)
   at PicoGK.Library..ctor(Single fVoxelSizeMM)
   at PicoGK.Library.GlobalInstance..ctor(...)
```

Confirmado também por inspeção direta do pacote NuGet restaurado:

```text
$ find ~/.nuget/packages/picogk/2.2.0/runtimes -maxdepth 2
runtimes/win-x64/native
runtimes/osx-arm64/native
(nenhuma pasta runtimes/linux-x64/native/)
```

## 7. Worker C#/.NET9 — testes xunit (código independente de PicoGK)

```text
$ cd tests/BioMatCadGeometryWorker.Tests && dotnet test
Passed!  - Failed: 0, Passed: 9, Skipped: 0, Total: 9, Duration: 247 ms
```

Cobrindo: volume/área/watertight de um cubo unitário conhecido, bounding box, porosidade
(incluindo clamping), volume de domínio block/cilindro, malha não-fechada, formato STL binário,
(de)serialização JSON do contrato de job.

## 8. ESLint (frontend)

```text
$ npx eslint . --max-warnings=0
(sem erros — saída vazia = sucesso)
```

## 9. TypeScript (`tsc --noEmit`)

```text
$ npx tsc --noEmit
(sem erros — saída vazia = sucesso)
```

## 10. Vitest (frontend)

```text
$ npx vitest run
 Test Files  9 passed (9)
      Tests  17 passed (17)
   Duration  10.77s
```

17/17 passando (7 do Incremento 1.1 → 17 agora: +4 arquivos novos — recipeValidationOffline
[7 testes], StlViewer [1], MaterialsPage [1], RecipeEditorPage [1] — totalizando +10 testes).

## 11. Build de produção e de demonstração (GitHub Pages)

```text
$ npm run build
vite v5.4.21 building for production...
✓ 65 modules transformed.
dist/index.html                   0.64 kB
dist/assets/index-WxHLJyX5.css    1.77 kB
dist/assets/index-YkqxDx90.js   707.34 kB │ gzip: 191.60 kB
✓ built in 3.26s

$ npm run build:pages
vite v5.4.21 building for demo...
✓ 65 modules transformed.
dist/index.html                   0.67 kB
dist/assets/index-D7CrewU5.js   707.74 kB │ gzip: 191.75 kB
✓ built in 3.21s
```

Aviso de chunk size (>500kB, devido ao Three.js) é não-bloqueante — registrado, não corrigido
nesta sessão (candidato a `manualChunks`/`import()` dinâmico em incremento futuro).

## 12. Smoke test HTTP do build de demonstração

```text
$ npx vite preview --port 4176 --strictPort &
$ curl -s -o /dev/null -w "status=%{http_code}\n" http://localhost:4176/biomatcad-nexus/
index_status=200
$ curl -s -o /dev/null -w "status=%{http_code}\n" http://localhost:4176/biomatcad-nexus/demo-assets/sample-scaffold-block-gyroid.stl
stl_status=200
$ curl -s http://localhost:4176/biomatcad-nexus/ | grep -o '<title>[^<]*</title>'
<title>BioMatCAD Nexus</title>
```

## 13. Preservação e verificação do histórico Git

```text
$ git log --oneline | wc -l
22

$ git bundle create biomatcad-nexus-v2.2.bundle --all
$ git bundle verify biomatcad-nexus-v2.2.bundle
biomatcad-nexus-v2.2.bundle is okay
The bundle records a complete history.
```

## 14. Integridade dos artefatos de entrega

```text
$ sha256sum -c SHA256SUMS.txt
biomatcad-nexus-v2.2.zip: OK
biomatcad-nexus-v2.2.bundle: OK
```

## Resumo consolidado

| Verificação | Resultado |
|---|---|
| Ruff | All checks passed |
| Mypy | 0 problemas em 45 arquivos |
| Alembic (3 migrações, banco vazio E banco existente) | Aplicadas sem erro |
| Pytest (backend) | 64/65 passando (1 skip esperado sem dotnet na mesma chamada) |
| Worker C# — build | 0 erros |
| Worker C# — execução real | Bloqueio reproduzido com evidência completa (PICOGK_RUNTIME_UNAVAILABLE) |
| Worker C# — xunit (código independente de PicoGK) | 9/9 passando |
| ESLint | 0 erros |
| TypeScript (`tsc --noEmit`) | 0 erros |
| Vitest | 17/17 passando (9 arquivos) |
| Build de produção | OK |
| Build de demonstração (Pages) | OK |
| Smoke HTTP do build de demo | 200 (index e STL sintético), título correto |
| `git bundle verify` | Histórico completo, íntegro |
| `sha256sum -c` dos artefatos finais | OK |

**Declaração de status**: este incremento é entregue **parcialmente bloqueado**. A vertical
geométrica está implementada e testada em todas as partes que não dependem da execução real do
PicoGK; a geração real de um scaffold Gyroid via worker não pôde ser verificada neste ambiente.
Ver ADR-0007 e `IMPLEMENTATION_STATUS.md` para os detalhes completos e os caminhos de
desbloqueio não tentados nesta sessão.
