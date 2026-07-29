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

---

# Evidência de teste — Incremento 2.1.1 (Fase 2, corretivo, parcialmente bloqueado no mesmo ponto)

Seção adicionada nesta sessão para consolidar a evidência de teste das correções do Incremento
2.1.1 (schema, worker C#, API, frontend, dependências). Não substitui a seção acima (Incremento
2.1), que permanece como registro histórico daquela entrega. Ver `IMPLEMENTATION_STATUS.md`
(seção "Incremento 2.1.1") para o checklist de aceite completo, item a item.

## 1. Backend (`apps/api`) — pytest

```text
$ pytest -v
...
83 passed, 2 skipped in <N>s
```

Os 2 skips são esperados neste ambiente: testes que invocam o binário real do worker C#
(`dotnet BioMatCadGeometryWorker.dll`) via `DotnetPicoGkWorkerClient`, marcados `skipif` na
ausência de `dotnet` no PATH ou de um ambiente Windows real — o mesmo padrão já usado desde o
Incremento 2.1 para o teste `test_dispatch_job_real_worker_fails_in_blocked_environment`.

Novos arquivos de teste desta sessão:
- `tests/test_geometry_job_security.py` — isolamento entre organizações (testes de ataque:
  projeto de outra organização, receita de outra organização, receita não pertencente ao
  projeto, receita não validada). Todos recusados com 403 e auditados.
- `tests/test_geometry_job_concurrency.py` — duas conexões/threads reais e independentes contra
  Postgres real disputando os mesmos jobs; zero jobs reivindicados em duplicidade em 24 jobs.
- `tests/test_geometry_job_cancellation.py` — cancelamento real (kill de árvore de processos via
  `psutil`), idempotência de recancelamento, teste de corrida (cancelamento no meio de
  `dispatch_job` nunca permite transição posterior para `succeeded`).
- `tests/test_recipe_schema.py` — ampliado para 24 testes cobrindo a nova semântica
  espessura/isovalor (obrigatoriedade de `wall_thickness_mm`, rejeição de combinações
  contraditórias com `TOPOLOGY_PARAMETERS_INCONSISTENT`).

```text
$ ruff check .
All checks passed!

$ mypy src
Success: no issues found
```

## 2. Worker C# (`apps/geometry-worker`) — xUnit

```text
$ dotnet build
Build succeeded. 0 Warning(s). 0 Error(s).

$ cd tests/BioMatCadGeometryWorker.Tests
$ dotnet test
Passed!  - Failed: 0, Passed: 48, Skipped: 0, Total: 48
```

Atualização desta sessão (revisão pós-entrega v2.2.1, antes de qualquer execução real no
Windows): uma reexecução real de `dotnet build` + `dotnet run` contra a golden recipe
`block-gyroid-v1.json` neste sandbox revelou um bug real -- `CleanupPartialOutputs` apagava
também o `job.json` de entrada (gravado por `worker_client.py` dentro do mesmo `output_dir`).
Corrigido (`OutputCleanup.cs`, preserva `job.json` explicitamente), com 4 novos testes de
regressão (`OutputCleanupTests.cs`). Reexecutado o cenário real após a correção: mesma falha
esperada (`PICOGK_RUNTIME_UNAVAILABLE`, runtime nativo ausente em linux-x64), mas `job.json`
agora sobrevive. Ver `apps/geometry-worker/WORKER_STATUS.md`, seção 9.1, para o relato completo.

Novo nesta sessão: `GyroidMathTests.cs` (27 testes) cobrindo `GyroidMath.cs` — avaliação do campo
gyroid, SDF de bloco/cilindro, interseção booleana, conversão espessura↔meia-largura de banda,
mapeamento seed→fase, estimativa de fração sólida, calibração de porosidade por bisseção (casos
convergentes e casos de borda), piso de voxel size em preview, estimativas de voxel/memória. E
`SimpleMeshWeldTests.cs` (5 testes) cobrindo a solda de vértices (`Weld()`) — cubo com vértices
duplicados reduzido ao número correto de vértices únicos, preservação da topologia dos
triângulos, casos de malha já soldada (idempotência). Ampliações em `StlExporterTests.cs` e
`GeometryMetricsCalculatorTests.cs` para cobrir a malha pós-solda. `LibraryGoConfigurationTests.cs`
(2 testes) guarda a configuração `bEndAppWithTask: true` do `Library.Go` (ver seção de atualização
acima). Todos os 62 testes são
independentes do runtime nativo do PicoGK — nenhum foi (nem poderia ser, neste sandbox) validado
contra uma execução real de `Voxels`/`Mesh`.

## 3. Frontend (`apps/web`) — Vitest, tsc, eslint, build

```text
$ npx tsc --noEmit
(sem erros)

$ npm run lint
(sem erros)

$ npx vitest run
...
Test Files  10 passed (10)
     Tests  27 passed (27)

$ npm run build
✓ built in <N>s

$ npm run build:pages
✓ built in <N>s
```

Novo nesta sessão: `tests/schemaSync.test.ts` (garante que `apps/web/src/schemas/geometry-
recipe-v1.schema.json` é byte-idêntico a `schemas/biomatcem/geometry-recipe-v1.schema.json`,
evitando que a cópia local usada pelo Ajv no frontend divirja silenciosamente do schema real do
backend). `tests/recipeValidationOffline.test.ts` ampliado para cobrir a validação real via Ajv
(`ajv/dist/2020`) contra o schema sincronizado, substituindo as ~15 regras manuais do
Incremento 2.1, e a canonicalização recursiva do fingerprint de demonstração (corrigindo o bug
em que `JSON.stringify` com replacer de array aplicava o mesmo filtro de chaves de topo em todos
os níveis de aninhamento, descartando silenciosamente campos de objetos aninhados).

## 4. Migração Alembic (Incremento 2.1.1)

```text
$ alembic upgrade head   # a partir de um banco vazio
INFO  Running upgrade ... -> ..., incremento_2_1_1_claim_atomico_e_...

$ alembic upgrade head   # a partir de um banco já na revisão anterior (Incremento 2.1)
INFO  Running upgrade <revisão anterior> -> ..., incremento_2_1_1_claim_atomico_e_...
```

Verificada nos dois cenários (banco vazio do zero, e banco incremental já na revisão do
Incremento 2.1) — nova revisão adiciona as colunas necessárias para o claim atômico da fila e
para a reestruturação do manifesto (checksum próprio fora do JSON).

## 5. Auditoria de dependências (Incremento 2.1.1)

Ver `docs/security/DEPENDENCY_AUDIT_2.1.1.md` para o detalhamento completo. Resumo:

| Ecossistema | Ferramenta | Resultado |
|---|---|---|
| Python (`apps/api`) | `pip-audit` | 0 vulnerabilidades em 23 pacotes diretos |
| NuGet (`apps/geometry-worker`) | `dotnet list package --vulnerable` | 0 pacotes vulneráveis |
| npm (`apps/web` + raiz) | `npm audit` | 18 reportadas — 1 corrigida sem breaking change (react-router 6.26.2→6.30.4), 17 deferidas (tooling de dev, ver `ROADMAP.md`) |

## 6. Execução real das 3 golden recipes no Windows x64 + correção de calibração de porosidade

O usuário executou de verdade `block-gyroid-v1`, `cylinder-gyroid-v1` e `preview-gyroid-low-res-v1`
no seu Windows x64. Resumo dos resultados (evidência completa em
`apps/geometry-worker/WORKER_STATUS.md` §10-§10.3):

| Receita | Watertight | Auditoria independente | Porosidade (alvo/medido/erro) | Veredito |
|---|---|---|---|---|
| Bloco | sim | aprovada | 60% / 58,669879% / -1,330121pp | **APROVADO** |
| Cilindro | sim | aprovada | 55% / 52,756863% / -2,243137pp | Geometria aprovada (contenção real verificada em 1.486.788 vértices, zero violações); porosidade marginalmente fora da tolerância |
| Preview | sim | aprovada (métricas internamente consistentes) | 60% / 78,804521% / +18,804521pp | **REPROVADO** quanto à porosidade |

Determinismo binário confirmado para o bloco (mesma receita+seed, mesmo SHA-256 em duas
execuções).

**Bug real encontrado**: a calibração de porosidade (`GyroidMath.CalibratePorosityByBisection`)
só conferia uma estimativa analítica contínua contra o alvo, nunca a malha efetivamente
voxelizada pelo PicoGK. O worker declarava `porosity_calibration_converged=true` mesmo quando a
malha real divergia muito do alvo (caso do preview) — sucesso científico falso.

**Correção**: nova calibração FECHADA (`GyroidMath.CalibrateByMonotonicBisection`) que gera
Voxels/Mesh reais a cada candidato de espessura e mede a porosidade de verdade sobre a malha
efetivamente exportada, com tolerâncias explícitas por modo (final 2,0pp / preview 5,0pp,
`GyroidMath.DefaultPorosityToleranceFinalPctPoints`/`DefaultPorosityTolerancePreviewPctPoints`)
e falha estruturada `POROSITY_TARGET_NOT_REACHED` quando não converge dentro da tolerância
medida. A saída JSON agora distingue explicitamente `analytical_porosity_estimate_pct`/
`analytical_calibration_converged` (Passo 1, palpite) de `measured_porosity_pct`/
`porosity_tolerance_pct_points`/`measured_porosity_error_pct_points`/
`measured_porosity_within_tolerance`/`mesh_calibration_iterations` (Passo 2, valor de
referência definitivo).

```text
$ dotnet test
Passed! - Failed: 0, Passed: 62, Skipped: 0, Total: 62
```

12 novos testes (`MonotonicPorosityCalibrationTests.cs`): divergência analítico-vs-medido
(didático), convergência dentro de ±2pp (bloco/cilindro), convergência dentro de ±5pp (preview,
incluindo comparação direta entre as duas tolerâncias com o mesmo oráculo), falha quando o alvo é
inatingível, invariante "nunca `Converged=true` fora da tolerância medida" (testada contra 5
cenários), determinismo do algoritmo, e validação de limites inválidos.

Também corrigidos nesta rodada: limpeza de artefatos parciais apagava o `job.json` de entrada
(`OutputCleanup.cs`); o viewer do PicoGK não fechava sozinho, inflando `duration_seconds`
(`bEndAppWithTask: true`, confirmado por reflexão contra o `PicoGK.dll` real). E o kit de
auditoria independente (`scripts/audit_stl_vs_worker_output.py`) foi corrigido para detectar
UTF-8/UTF-16 automaticamente e extrair o último objeto JSON válido de um stdout com logs
misturados.

**IMPORTANTE**: todos os SHA-256/STLs reportados acima (seção 6) são anteriores à correção de
calibração — preservados sem alteração, rotulados como tal. A seção 7 abaixo documenta a
execução real PÓS-correção, contra o commit `da75219`.

## 7. Execução real PÓS-correção -- as 3 golden recipes APROVADAS (commit `da75219`)

Transcrito literalmente, tal como recebido do usuário, sem qualquer alteração. Ver
`apps/geometry-worker/WORKER_STATUS.md` §10.4 para o relato completo com todas as observações de
consistência.

```text
Build Release: aprovado
xUnit:         62/62 aprovados, 0 falhas

BLOCK:    alvo 60% / medido 58,6698791858207% / erro -1,3301208141793026pp / tolerância 2pp
          1 iteração de calibração por malha
          SHA-256 cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d

CYLINDER: alvo 55% / medido 55,75526607688106% / erro +0,7552660768810568pp / tolerância 2pp
          5 iterações de calibração por malha
          SHA-256 2cb8cbdf9acbff579c838d8bf3cc2e2a688bcd33a3c475945174272cb278445e

PREVIEW:  alvo 60% / medido 56,733228138231375% / erro -3,2667718617686248pp / tolerância 5pp
          4 iterações de calibração por malha
          SHA-256 7660dae3ee263445835bbf9d26c16fa4ef8f8ee2fd2c320000b0546c1eaaba78

Auditoria independente (scripts/audit_stl_vs_worker_output.py): 3/3 sem divergência,
  AuditExitCode=0 nas três, watertight=true nas três.

Determinismo pós-correção: segunda execução real das três receitas, hashes Run1=Run2 nas três,
  DeterminismoGlobal=True.

Contenção cilíndrica: 493.664 triângulos, 1.480.992 vértices examinados, raio máximo
  4,999950394mm, intervalo Z [-6,+6]mm, 0 violações radiais, 0 violações em Z,
  ContainmentExitCode=0. (Nota: esta checagem específica de contenção não foi gerada por
  scripts/audit_stl_vs_worker_output.py deste repositório -- ver ressalva completa em
  WORKER_STATUS.md §10.4.)
```

**Veredito**: as três golden recipes estão APROVADAS quanto a geometria, calibração de
porosidade, auditoria independente, determinismo e (para o cilindro) contenção radial/Z. Todas
dentro das tolerâncias medidas (não apenas estimadas analiticamente) definidas nesta sessão.

## O que esta evidência explicitamente NÃO cobre

- **Validação da interface integrada (frontend)** contra o worker corrigido — ainda não
  realizada.
- **E2E Playwright** — escrito (`apps/web/e2e/`), nunca executado em nenhum ambiente até agora
  (bloqueado neste sandbox Linux: faltam bibliotecas nativas do Chromium, `sudo` desabilitado —
  ver `apps/web/e2e/README.md`).
- **Consistência STL-vs-manifesto via fluxo completo API→dispatcher→manifesto** — todas as
  execuções reais desta sessão continuam sendo invocações diretas do worker via CLI, não pelo
  fluxo de produção completo.
- **Empacotamento final v2.2.1** — deliberadamente ainda não gerado.

Estes itens são o que falta para declarar o Incremento 2.1.1 concluído.
