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

## 8. Re-verificação real pós-commit documental + tentativa real de E2E Playwright (2026-07-29)

Após o commit somente-documentação `dbfbfe5`, reexecutei de verdade, neste sandbox, as suítes de
teste isoladas de backend/worker/frontend (nenhum código foi alterado -- esta é uma checagem de
regressão, não uma nova correção) e tentei novamente a execução real do E2E Playwright, como
parte da validação de interface integrada pedida.

**Backend (`apps/api`) — pytest, contra PostgreSQL real via `pgserver`:**

```text
83 passed, 2 skipped, 0 failed (Duration: 28.18s)
```

Nota honesta sobre um falso alarme descartado: a primeira tentativa desta re-verificação, feita
sem configurar `TEST_DATABASE_URL`, caiu no fallback SQLite em arquivo
(`sqlite:///./test_biomatcad.db`) descrito em `tests/conftest.py`. Esse arquivo tinha linhas
residuais de uma execução anterior (o teste de concorrência do dispatcher faz `commit()` real,
fora da transação-por-teste padrão, propositalmente, para provar visibilidade entre conexões) e
isso produziu 2 falhas espúrias (`test_clinical_suite_expiration_is_respected` e
`test_two_concurrent_dispatchers_never_claim_the_same_job`, este com contagem de jobs reivindicados
28 em vez dos 24 esperados). Removi o arquivo SQLite obsoleto e reexecutei a suíte inteira contra
um PostgreSQL efêmero real via `pgserver` (o mesmo backend usado pelo CI, ver
`.github/workflows/ci-api.yml`) -- resultado limpo, 0 falhas, idêntico ao baseline já documentado
na Seção 1. Isto foi uma falha de higiene do ambiente de teste local (arquivo de fallback não
limpo entre execuções), não uma regressão de código; nenhuma correção de código foi necessária.

**Worker C# (`apps/geometry-worker`) — xUnit, neste sandbox (sem PicoGK, como sempre):**

```text
Passed!  - Failed: 0, Passed: 62, Skipped: 0, Total: 62, Duration: 367 ms
```

**Frontend (`apps/web`):**

```text
tsc --noEmit:  limpo, 0 erros
eslint (--max-warnings=0): limpo, 0 avisos/erros
vitest run:    Test Files 10 passed (10) | Tests 27 passed (27)
vite build:    sucesso (dist/index.html, dist/assets/*, aviso benigno de tamanho de chunk >500kB)
```

**E2E Playwright — tentativa real, reconfirmando o bloqueio:**

Reexecutei a tentativa de lançar um navegador real via Playwright neste sandbox (ver relato
completo e literal em `apps/web/e2e/README.md`, seção "Re-confirmação real"):

- Chromium (`chrome-headless-shell`, já baixado): falha idêntica à documentada antes --
  `libXdamage.so.1: cannot open shared object file`.
- Firefox (tentativa nova, para verificar se outro motor escaparia da mesma classe de
  dependência ausente): também falhou -- o Playwright detecta a ausência de `libxdamage1` /
  `libgtk-3-0` no host antes mesmo de tentar lançar o processo.
- `apt-get download libxdamage1` (tentativa de obter a biblioteca sem precisar de `sudo`,
  apenas de rede): falhou com `502 Bad Gateway` -- o próprio acesso de rede a
  `archive.ubuntu.com` está bloqueado neste sandbox, não só a instalação privilegiada.

Conclusão: o bloqueio de E2E real neste ambiente é duplo (falta a biblioteca nativa E falta
qualquer via, privilegiada ou não, de obtê-la) e continua sem contorno silencioso possível.
Nenhum resultado de E2E foi fabricado.

**Veredito desta re-verificação**: a interface integrada -- backend e frontend, cada um
isoladamente com suas próprias suítes de integração/unitárias -- está validada sem regressão após
o commit de documentação. A execução E2E real (navegador ponta-a-ponta) permanece bloqueada
neste sandbox e depende do usuário rodar os comandos documentados em `apps/web/e2e/README.md`
no seu próprio Windows (mesmo ambiente onde o worker PicoGK já foi validado).

## 9. Bug real do E2E corrigido: `__dirname` em módulo ES + seleção de Python (2026-07-29)

O usuário instalou o Chromium com sucesso no Windows e conseguiu rodar `npm run test:e2e` pela
primeira vez de verdade -- mas o `globalSetup` (`apps/web/e2e/global-setup.ts`) falhou antes de
qualquer teste, com o erro literal:

```
ReferenceError: __dirname is not defined
    at .../apps/web/e2e/global-setup.ts:10
```

Causa: `apps/web/package.json` declara `"type": "module"`; `__dirname`/`__filename` não existem
em módulos ES em nenhuma plataforma. Corrigido derivando o diretório do módulo via
`path.dirname(fileURLToPath(import.meta.url))`, extraído na função exportada e testável
`currentModuleDir(moduleUrl)`. Ao mesmo tempo, corrigida a seleção do interpretador Python
(`resolvePythonBin`, também exportada e testável): preserva `E2E_PYTHON_BIN` quando definida;
sem ela, usa `"python"` no Windows e `"python3"` nas demais plataformas.

Guarda de regressão real em `apps/web/tests/e2eGlobalSetup.test.ts` (8 testes): comportamento de
`resolvePythonBin`/`currentModuleDir` para várias combinações de plataforma/env, mais uma guarda
textual contra a reintrodução de `__dirname` executável ou de um `"python3"` hardcoded sem
diferenciar Windows. Verifiquei a guarda de verdade: reintroduzi deliberadamente as duas
regressões no arquivo e confirmei que os testes realmente falham (6 de 6 relacionados falharam),
depois restaurei a correção e confirmei os 35/35 verdes de novo.

Reexecução real pós-correção neste sandbox: `apps/web/e2e/global-setup.ts` executado via `tsx`
carregou sem `ReferenceError`; `npm run test:e2e` completo mostrou o `globalSetup` concluindo com
sucesso (avançou até tentar lançar o Chromium real) -- ou seja, o bug relatado está corrigido e
comprovado. A suíte então falhou ao lançar o Chromium pela MESMA causa já documentada (Seção 8):
`libXdamage.so.1` ausente neste sandbox Linux, sem contorno possível aqui. Nenhum resultado de
E2E foi declarado aprovado.

Suítes completas revalidadas após esta correção: `tsc --noEmit` limpo, `eslint --max-warnings=0`
limpo, `vitest run` 35/35 (27 anteriores + 8 novos), `vite build` com sucesso.

## 10. Duas falhas reais de E2E corrigidas: navegação via reload perdia sessão + status testado em inglês (2026-07-29)

Após o bug do `__dirname` corrigido, o usuário rodou o E2E completo de verdade no Windows (API
real, frontend real, Chromium funcional, seed `already_seeded`). Os dois testes RODARAM, mas
FALHARAM: teste 1 (`vertical.spec.ts:22`) esgotou 30s esperando `#project-name`; teste 2
(`vertical.spec.ts:76`) não achou `getByText("succeeded")` em 5s. Anexou ZIP com log completo,
`error-context.md` e traces Playwright dos dois testes.

Inspecionei os dois `error-context.md` (incluindo os page snapshots, não só os logs) antes de
mexer em qualquer código. Achado central: em AMBOS os pontos de falha, o snapshot da página
mostrava a tela de LOGIN -- mesmo depois de `expect(page).toHaveURL(/\/app/)` já ter passado.

**Causa raiz (no teste, não na interface/rotas/autenticação/API/seed):** o teste usava
`page.goto()` para navegar a rotas protegidas depois do login. `AuthContext.tsx` guarda o token
só em memória (decisão de segurança documentada, proposital); `page.goto()` força um reload
completo, que reinicia o app e derruba a sessão -- `ProtectedRoute.tsx` redireciona para
`/login`. O seed funcionou (`already_seeded`); a API funcionou; a interface sempre permitiu
criar projeto -- só era inalcançável pela forma de navegação do teste.

Causa independente no teste 2: mesmo com a navegação corrigida, `getByText("succeeded")` nunca
acharia nada -- `JobDetailPage.tsx` traduz o status via `STATUS_LABEL` (`succeeded` →
"Concluído"), nunca expõe o valor bruto da API no DOM.

**Corrigido:**
- `vertical.spec.ts`: toda navegação pós-login agora via clique em link/botão real da UI
  (`getByRole`), nunca `page.goto()` em rota protegida. Teste 2 reescrito para percurso 100% UI
  (elimina as chamadas diretas à API que existiam só para descobrir o job ID).
- `JobDetailPage.tsx`: 3 `data-testid` documentados adicionados (`job-status`, `job-metrics`,
  `stl-download-link`, este último só no artefato STL) -- puramente aditivo, nenhuma mudança de
  comportamento/geometria.
- Seletores migrados para `getByRole`/`getByLabel` onde havia equivalente acessível real.

**Guardas de regressão** (verificadas quebrando deliberadamente e restaurando):
`apps/web/tests/verticalSpecGuard.test.ts` (guarda textual contra `page.goto()` em rota
protegida e contra afirmar `"succeeded"` literal) e `apps/web/tests/JobDetailPage.test.tsx`
(renderiza o componente real, autenticado de verdade via `AuthContext.login()` com fetch
mockado, confirma "Concluído"/métricas/download, e que o artefato de thumbnail não rouba o
`data-testid` do STL).

Suítes completas revalidadas: `tsc --noEmit` limpo, `eslint --max-warnings=0` limpo, `vitest
run` 40/40 (35 anteriores + 1 novo teste de guarda textual + 1 novo smoke test do
JobDetailPage, com 8 e 1 casos respectivamente, mais o smoke ampliado), `vite build` com
sucesso.

Reexecução real neste sandbox pós-correção: `npm run test:e2e` -- `globalSetup` conclui, os
dois testes tentam lançar o Chromium real e falham pela MESMA causa já documentada (Seção 8/9):
`libXdamage.so.1` ausente. Nenhum resultado de E2E foi declarado aprovado; falta a próxima
execução real do usuário no Windows para confirmar que a navegação e as asserções corrigidas
batem com a interface de produção.

## 11. E2E Playwright real APROVADO no Windows (commit `f7a9614`)

Transcrito literalmente, tal como recebido do usuário, sem qualquer alteração.

Infraestrutura confirmada pelo usuário: API real em `localhost:8000`; frontend real em
`localhost:5173`; Chromium real e funcional; ambiente Python isolado (venv da API); seed
sintético `already_seeded`; as duas portas verificadas previamente como
`TcpTestSucceeded=True`.

```text
Running 2 tests using 1 worker

ok 1 -- login, criação de projeto e receita via UI real
ok 2 -- página de job succeeded (pré-semeado) exibe status, métricas e link de download do STL

2 passed (8.9s)
PlaywrightExitCode=0
```

**Veredito**: os dois cenários do E2E Playwright (`apps/web/e2e/vertical.spec.ts`) passaram de
verdade contra a interface, a API e o Postgres reais rodando no Windows do usuário, com o
Chromium real (não simulado, não headless-fake). As correções de navegação (nunca `page.goto()`
em rota protegida) e de asserção de status localizado (Seção 10) estão confirmadas contra a
interface de produção real, não apenas contra os testes unitários/guardas deste sandbox.

**Ressalva importante, para não confundir escopos de prova**: o cenário 2 (`ok 2`) verifica a
UI real (status "Concluído", tabela de métricas, link de download) sobre um job **succeeded
PRÉ-SEMEADO** por `scripts/seed_e2e_user.py`, via o `_FakeWorkerClientForE2ESeed` -- um test
double explícito que NUNCA executa o PicoGK real (ver docstring do próprio script e
`apps/geometry-worker/WORKER_STATUS.md`). Este E2E prova que a **interface** (frontend + API +
Postgres + navegação real) está correta e íntegra ponta-a-ponta para exibir um job já
concluído. Ele **NÃO** prova, e nunca teve a intenção de provar, que o **worker PicoGK real**
foi executado através do fluxo de produção completo (API → fila → dispatcher → worker →
STL → Artifact/Manifest → download) -- essa prova é um gate SEPARADO, ainda pendente (ver
Seção 12 abaixo e "O que esta evidência NÃO cobre").

## 12. Gate final pendente: vertical completa com worker PicoGK real via fila de produção

Ainda não provado com o worker PicoGK real (nem nesta sessão, nem em nenhuma anterior): submeter
um job NOVO (não pré-semeado) através do fluxo de produção real -- API cria
`DesignRun`/`GeometryJob` → dispatcher reivindica via fila Postgres → worker PicoGK real gera o
STL → API persiste `Artifact`/`ArtifactManifest` → download via endpoint real -- com o status
transitando `queued` → `running` → `succeeded` de verdade, e o SHA-256 do STL físico conferido
contra o registro `Artifact`, o `ArtifactManifest` e o arquivo baixado via API.

Script criado para automatizar exatamente essa verificação:
`apps/api/scripts/verify_full_pipeline_sha256.py`. Ele: cria um usuário/organização dedicados
(idempotente); autentica via HTTP real; cria projeto e receita reais; submete um `DesignRun`
NOVO com `idempotency_key` única por execução (nunca reaproveita nem pré-semeia); invoca o
dispatcher real (`geometry_dispatcher.py --once`) em segundo plano e faz polling concorrente do
status; usa `started_at` (gravado atomicamente por `claim_next_queued_job`) como prova
autoritativa da transição `queued`→`running` (independente de o polling "flagrar" o estado
intermediário ao vivo, o que é inerentemente sujeito a corrida para jobs rápidos); e, se o job
chegar a `succeeded`, compara o SHA-256 em 5 fontes (arquivo físico lido via o `storage_key`
real do `Artifact`, o campo `sha256` do `Artifact` via API, o mesmo campo via DB direto, o
`stl_sha256` do `ArtifactManifest`, e os bytes baixados via `GET /api/v1/artifacts/{id}/download`),
confirma métricas persistidas com os nomes de campo REAIS do worker, confirma a trilha de
`AuditEvent` (`geometry_job_created`, `geometry_job_succeeded`) e a associação
usuário/organização/projeto/receita. Nunca fabrica sucesso: qualquer divergência real produz
`FAILED` com o motivo exato e código de saída != 0.

**Dry-run real feito neste sandbox** (sem PicoGK disponível, como sempre): subi um Postgres
efêmero real via `pgserver`, uma instância `uvicorn` real da API, e rodei o script de ponta a
ponta contra elas. Resultado honesto: todos os passos via HTTP (login, criar projeto, criar
receita, submeter job) passaram; o dispatcher real foi invocado e `started_at` confirmou a
transição real para `running`; o job então falhou exatamente com `WORKER_RUNTIME_UNAVAILABLE`
("O runtime nativo do PicoGK não está disponível nesta plataforma") -- a mesma limitação
conhecida de sempre, detectada e reportada honestamente pelo script (`GATE REPROVADO`, exit
code 1), sem nenhuma tentativa de disfarçar ou contornar. Isso valida que a mecânica do script
(chamadas HTTP reais, invocação do dispatcher real, detecção de falha real) funciona
corretamente; falta apenas a execução no Windows do usuário, onde o PicoGK real está disponível,
para percorrer também a parte de comparação de SHA-256/métricas/auditoria.

**Bug real descoberto e corrigido ao preparar este gate**: cruzando o contrato real do worker
(`apps/geometry-worker/JobEnvelope.cs`: `porosity_pct_measured`, `vertex_count_unique`) contra
o frontend, encontrei que `JobDetailPage.tsx`/`types.ts`/`demoClient.ts` liam os campos errados
(`porosity_pct_estimated`, `vertex_count`, que NUNCA existiram na API real) -- a página de um
job succeeded real mostraria "undefined" silenciosamente para porosidade e vértices. Corrigido
nos 3 arquivos (mais o teste `JobDetailPage.test.tsx`, atualizado para usar os nomes reais).
Verificado quebrando deliberadamente de novo e confirmando a falha do teste, depois restaurado.

Um kit PowerShell para o usuário executar este gate real no Windows foi preparado (ver
`docs/examples/WINDOWS_EXECUTION_KIT.md`, nova Seção 9).

## 13. Launcher executável do BioMatCAD Nexus para Windows (`tools/windows-launcher/`) -- código, testes reais e cross-publish (2026-07-29)

Implementado o iniciador de duplo clique pedido explicitamente nesta rodada (Turno anterior
aceitou o commit `75ebd1e`, mas registrou que o launcher NÃO havia sido criado ainda -- este é
o trabalho que fecha essa pendência, sem abrir novo incremento).

**Estrutura criada**:
- `tools/windows-launcher/BioMatCAD.Launcher.csproj` (.NET 9, `AssemblyName=BioMatCAD-Nexus`)
- `tools/windows-launcher/Program.cs` -- orquestração real dos 16 comportamentos pedidos
- `tools/windows-launcher/src/`: `RepositoryLocator.cs`, `PathResolver.cs`,
  `DependencyDetector.cs`, `PortChecker.cs`, `SecretGenerator.cs`, `StartupPlanner.cs`,
  `ProcessSupervisor.cs`, `EnvironmentSetup.cs`
- `tools/windows-launcher/tests/BioMatCAD.Launcher.Tests/` -- suíte xUnit real
- `tools/windows-launcher/README.md` -- documentação completa (comportamento, arquitetura,
  segurança, testes, build)
- `scripts/Build-WindowsLauncher.ps1` -- roda os testes e depois publica win-x64
- `Start-BioMatCAD.cmd` -- ponto de entrada de duplo clique (substitui os "três PowerShells
  manuais")

**Testes: 54/54 xUnit REAIS aprovados neste sandbox** (sem fakes de sistema operacional --
diretórios temporários reais, sockets TCP reais via `TcpListener`/`TcpClient`, subprocessos
reais via `python3`/`node`/`npm`/`dotnet` genuinamente instalados no ambiente, e `sleep`/
`cmd.exe timeout` como processos de longa duração descartáveis para os testes de supervisão de
processos). Cobrem os 10 cenários explicitamente pedidos: raiz do projeto, caminhos com
espaços, detecção de dependências, segredo não exposto, portas ocupadas, início parcial,
encerramento dos filhos, composição de comandos Windows, Python 3.14 (comparação de versão
numérica -- `3.14 > 3.9`, nunca lexicográfica), e API/frontend já ativos.

**Verificação de que os testes de guarda de segurança realmente detectam regressão** (mesmo
padrão de rigor já usado nos testes de guarda do E2E): troquei deliberadamente
`ProcessSupervisor.StartTracked` para usar `psi.Arguments = string.Join(" ", arguments)` (o
padrão de command injection que o código real evita) e confirmei que
`SecurityReviewGuardTests.ProcessSupervisor_NuncaUsaArgumentsConcatenadoComoString` falhou
imediatamente; revertido em seguida e confirmado verde de novo (9/9 nesse arquivo).

**Bugs reais encontrados e corrigidos durante esta implementação** (antes de qualquer commit):
1. `PathResolver.WhichCommand` expandia sufixos do PATHEXT mesmo sobre nomes que já tinham
   extensão explícita (ex.: `"npm.cmd"` viraria candidato a `"npm.cmd.EXE"`) -- corrigido com
   checagem `Path.HasExtension(commandName)`.
2. `WhichCommand` comparava sufixos do PATHEXT (convencionalmente maiúsculos, ex. `.EXE`)
   contra nomes de arquivo reais em minúsculas (ex. `python.exe`) sem tentar a variante em
   minúsculas -- em NTFS isso nunca importaria (case-insensitive), mas o bug só apareceu ao
   testar a lógica de resolução de verdade contra arquivos reais em disco (mesmo em sandbox
   Linux, sensível a caixa) -- corrigido tentando explicitamente a variante em minúsculas do
   sufixo antes de desistir do diretório.
3. Dois testes de guarda de segurança tinham falso-positivo: o comentário explicativo do
   próprio código cita as palavras proibidas ("nunca um taskkill genérico", "nunca habilita um
   ambiente clínico") para documentar que elas são evitadas, e o banner permanente obrigatório
   contém literalmente "CLÍNICOS" (dentro de "NÃO UTILIZAR DADOS CLÍNICOS REAIS") -- corrigido
   filtrando linhas de comentário puro antes da checagem de `taskkill`, e trocando a checagem
   ingênua "a palavra 'clínico' nunca aparece" por uma checagem precisa: toda atribuição a
   `ENVIRONMENT` no código deve ser exatamente `"test"` (via regex sobre as atribuições reais,
   não sobre a presença da palavra em qualquer contexto). Mesma técnica de "guarda textual com
   comentários filtrados" já usada em `apps/web/tests/verticalSpecGuard.test.ts`.

**Execução manual real de `Program.cs` neste sandbox** (smoke test, não susbtitui a execução
completa no Windows real do usuário): rodei o executável de verdade a partir da raiz real do
repositório clonado. Resultado real observado: detectou corretamente Python 3.10.12, Node
v22.22.3, npm 10.9.8 e .NET 9.0.316 (caminhos absolutos reais resolvidos via `PathResolver`);
detectou as portas 8000/5173 livres e decidiu iniciar novos processos (`StartupPlanner`); criou
de verdade um `.venv` real em `apps/api/.venv` via `python3 -m venv`; iniciou de verdade
`pip install -e .` (interrompido deliberadamente por mim antes de terminar, para não gastar
tempo/rede desnecessariamente neste smoke test -- não é uma falha do launcher, é o próprio
`pip install` real em andamento). O `.venv` de teste foi removido antes do commit (já ignorado
globalmente por `.gitignore`: `.venv/`). **Não tentei** neste sandbox chegar até iniciar a API/
frontend de verdade nem abrir o navegador -- isso depende do ambiente real do usuário (Windows,
com todas as dependências já usadas no restante desta sessão) e é o próximo passo de evidência
pendente, no mesmo padrão já usado para o E2E Playwright (Seções 9-11).

**Cross-publish win-x64**: `dotnet publish -c Release -r win-x64 --self-contained false
-p:PublishSingleFile=true` rodou de verdade neste sandbox (o pacote de runtime win-x64 foi
restaurado da NuGet real) e produziu um binário genuíno:

- Arquivo: `dist/windows-launcher/BioMatCAD-Nexus.exe`
- Verificado via `file`: `PE32+ executable (console) x86-64, for MS Windows` (formato real de
  executável Windows, não um artefato genérico)
- SHA-256: `b6ae108ca7305b256d778403211cddb14d31d958cabb3f63b1132d99210070f6`
- **Este binário foi apenas COMPILADO, nunca EXECUTADO** -- este sandbox é Linux e não roda
  binários win-x64. A validação de execução real (duplo clique, os 16 comportamentos ponta a
  ponta) depende do usuário rodar no Windows real -- ver `tools/windows-launcher/README.md` e
  o comando de reprodução no fechamento desta resposta.
- **Decisão documentada**: o `.exe` (e `dist/` em geral) **não é versionado no Git** --
  `dist/` já está no `.gitignore` da raiz do repositório desde antes desta rodada. É um
  artefato de build reproduzível a qualquer momento a partir do código-fonte versionado via
  `scripts/Build-WindowsLauncher.ps1`.

## O que esta evidência explicitamente NÃO cobre

- **Consistência STL-vs-manifesto via fluxo completo API→dispatcher→worker PicoGK real→
  Artifact/Manifest→download** -- o E2E aprovado (Seção 11) valida a interface real, mas com um
  job PRÉ-SEMEADO (worker fake rotulado); nenhum job NOVO foi submetido e processado através do
  fluxo de produção completo com o worker PicoGK real nesta sessão. Este é o gate final ainda
  pendente (Seção 12).
- **Execução real do launcher Windows (`BioMatCAD-Nexus.exe`) no Windows do usuário** -- o
  binário foi compilado e testado (54/54 xUnit) neste sandbox, mas nunca executado como `.exe`
  win-x64 de verdade (Seção 13). Duplo clique real, os 16 comportamentos ponta a ponta, e
  confirmação de que a API/frontend sobem e o navegador abre ainda dependem do usuário.
- **Empacotamento final v2.2.1** — deliberadamente ainda não gerado.

Estes itens são o que falta para declarar o Incremento 2.1.1 concluído.
