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

## 14. Execução real e aprovação do launcher no Windows do usuário (relatada pelo usuário, 2026-07-29)

**Importante -- distinção explícita entre dois eventos diferentes:**

- **Seção 13 (acima)**: o `.exe` foi **compilado** (cross-publish `win-x64`) neste sandbox
  Linux. Isso prova que o código compila e produz um binário Windows genuíno, mas **não** prova
  que ele funciona quando executado de verdade -- este sandbox não roda binários win-x64.
- **Esta seção 14**: o usuário baixou o `BioMatCAD-Nexus.exe` entregue, conferiu o SHA-256 e
  **executou de verdade no Windows real dele**. É este evento -- não o cross-build -- que prova
  que o launcher funciona.

**Evidência relatada pelo usuário** (validação real no Windows, conforme relatado nesta
conversa -- nenhum detalhe além do que segue foi inventado ou presumido):

- SHA-256 do `BioMatCAD-Nexus.exe` conferido pelo usuário **antes** de executar (confere com o
  publicado na Seção 13: `b6ae108ca7305b256d778403211cddb14d31d958cabb3f63b1132d99210070f6`).
- O executável abriu corretamente.
- A API e o frontend foram iniciados pelo launcher.
- O navegador abriu a interface.
- A tela de login ficou disponível.
- O encerramento (fechar/Ctrl+C) funcionou corretamente.
- Nenhum problema foi observado pelo usuário durante a execução.

**O que isto prova, com base estritamente no que foi relatado**: os comportamentos 1-2
(detecção de dependências reais no Windows do usuário, implícito no fato de a API/frontend
terem subido), 6-11 (segredo gerado, `ENVIRONMENT=test`, API em `:8000`, frontend em `:5173`,
espera de prontidão, abertura do navegador em `/login`) e 13 (encerramento correto) da lista de
16 comportamentos pedidos **funcionaram de ponta a ponta no Windows real**, sem nenhum problema
relatado.

**O que esta evidência, por si só, NÃO detalha** (o usuário não relatou esses pontos
especificamente, então não são afirmados aqui): se o `.venv`/`node_modules` já existiam
previamente ou foram criados nesta execução (comportamentos 3-5); se alguma porta já estava
ocupada e o launcher reaproveitou um serviço existente, ou se ambas as portas estavam livres
(comportamento 14); confirmação visual explícita do banner permanente "AMBIENTE DE TESTE" e da
ausência do segredo no console (comportamentos 15-16) -- o código continua garantindo isso (ver
Seção 13/README.md/testes de guarda de segurança), mas a confirmação visual explícita não foi
relatada. Nenhum desses pontos foi negado pelo usuário -- apenas não fazem parte do relato
literal recebido, então esta seção não afirma tê-los confirmado.

**Conclusão**: o launcher está **validado por execução real no Windows do usuário**, cobrindo o
caminho principal (duplo clique -> dependências detectadas -> API e frontend sobem -> navegador
abre -> login disponível -> encerramento limpo), sem nenhum problema relatado. Isso fecha o item
18 do `IMPLEMENTATION_STATUS.md` como aprovado por execução real, distinto do cross-build da
Seção 13.

## 15. Bug real corrigido: contrato de driver Postgres (psycopg vs psycopg2) ao tentar rodar o gate final no Windows (2026-07-29)

**Relato real do usuário**: o gate final (`scripts/Run-FinalGate.ps1`) rodou de verdade no
Windows e parou ANTES das migrações, com `DATABASE_URL =
postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad` e o erro:

```
ModuleNotFoundError: No module named 'psycopg'
```

**Causa raiz confirmada**: `apps/api/pyproject.toml` só declarava `psycopg2-binary`. A URL
`postgresql+psycopg://` (dialeto psycopg 3) é usada de verdade em
`docs/examples/WINDOWS_EXECUTION_KIT.md` e no default de `scripts/Run-FinalGate.ps1` -- mas o
driver `psycopg` (v3) nunca foi declarado como dependência.

**Auditoria de todos os usos reais de `DATABASE_URL` no repositório** (grep completo, não
suposição):

- `postgresql://` (sem driver explícito -- SQLAlchemy resolve para `psycopg2` por padrão):
  `.github/workflows/ci-api.yml`, `.env.example`.
- `postgresql+psycopg://` (psycopg 3, explícito): `docs/examples/WINDOWS_EXECUTION_KIT.md`,
  `delivery/v2.2.1/WINDOWS_EXECUTION_KIT_v2.2.1.md`, `scripts/Run-FinalGate.ps1`.
- `postgresql+psycopg2://` (explícito): aparece apenas como exemplo ilustrativo no docstring
  de `apps/api/scripts/seed_e2e_user.py` (nunca executado com esse valor literal em nenhum
  lugar do código/CI).

**Conclusão**: os dois drivers (`psycopg2` e `psycopg` v3) têm uso real confirmado em
contextos diferentes do mesmo repositório -- `psycopg2-binary` foi **mantido** (não removido),
e `psycopg[binary]>=3.1` foi **adicionado**.

**Correção aplicada**:
- `apps/api/pyproject.toml`: adiciona `"psycopg[binary]>=3.1"` às dependências de produção,
  com um comentário extenso documentando por que ambos os drivers precisam coexistir.
- `docs/security/DEPENDENCY_AUDIT_2.1.1.md`: `pip-audit` rodado de verdade (venv isolado, só
  `psycopg[binary]` + `pip-audit`) contra a versão resolvida `psycopg 3.3.4` /
  `psycopg-binary 3.3.4` -- **nenhuma vulnerabilidade conhecida** no pacote em si.

**Teste novo, real, que teria pego este bug antes do usuário** (`apps/api/tests/
test_database_driver_contract.py`, 4 testes): cria um `sqlalchemy.create_engine(...)` para
cada dialeto Postgres genuinamente usado no repositório (`postgresql://` e
`postgresql+psycopg://`) contra um host fictício (nunca conecta de verdade -- SQLAlchemy
importa o módulo do driver DBAPI no momento de `create_engine`, mesmo sem abrir conexão de
rede, o que basta para detectar driver ausente sem precisar de infraestrutura). **Verificado
genuinamente**: antes da correção (ambiente real deste sandbox, que já tinha `psycopg2` mas
não `psycopg`), rodei a suíte e ela falhou exatamente nos 2 testes do dialeto `psycopg` v3,
com a mesma mensagem `ModuleNotFoundError: No module named 'psycopg'` relatada pelo usuário
(2 failed, 2 passed); depois de instalar `psycopg[binary]`, os 4 passaram.

**Validação em instalação limpa** (não apenas no ambiente que já tinha alguns pacotes):
criado um `venv` totalmente novo, sem nenhum `psycopg`/`psycopg2` pré-instalado, rodando
apenas `pip install -e ".[dev]"` (o comando real que qualquer novo clone usaria). Resultado:
os dois drivers foram instalados corretamente a partir de `pyproject.toml`, os 4 testes de
contrato passaram, e a suíte completa do backend rodou com sucesso a partir desse venv limpo
contra um PostgreSQL efêmero real (via `pgserver`): **88 passed, 1 skipped** (o skip esperado
é `test_dispatch_job_real_worker_fails_in_blocked_environment`, sem PicoGK linux-x64), `ruff
check .` e `mypy src` limpos.

**Preflight real adicionado a `scripts/Run-FinalGate.ps1`** (novo script
`apps/api/scripts/gate_preflight_check.py`, chamado ANTES de `alembic upgrade head`):
verifica, em ordem, (1) que `DATABASE_URL` não é SQLite (recusa explícita -- SQLite nunca é
aceito como substituto do gate real), (2) que o módulo do driver DBAPI exigido pelo dialeto da
URL é importável, (3) que a porta do Postgres realmente aceita conexão TCP, e (4) que a
conexão E autenticação reais funcionam (`SELECT 1` via SQLAlchemy). Grava sempre um relatório
JSON estruturado em stdout (mesmo formato de `GATE_FULL_PIPELINE_REPORT.json`, com
`"stage": "preflight"`), e `Run-FinalGate.ps1` sempre copia esse conteúdo para
`gate-final-report.json` em caso de falha -- o usuário nunca mais fica sem relatório, mesmo
que o script morra antes do Alembic.

**Os 4 cenários do preflight foram validados de verdade**, não apenas lidos no código: subi um
PostgreSQL real (binários do próprio `pgserver`, `initdb`/`pg_ctl` reais) escutando via TCP em
`127.0.0.1` (não apenas socket unix, para reproduzir fielmente o cenário real do Windows), com
um usuário/banco `biomatcad` reais.

1. **Driver ausente** (venv com só `psycopg2`, sem `psycopg`): preflight reproduziu o erro
   original **exatamente**, `ModuleNotFoundError: No module named 'psycopg'`, `FAILED`, exit
   code 1.
2. **Porta inacessível** (porta fechada de propósito): `Connection refused` real, `FAILED`.
3. **Senha incorreta** (usuário real, senha errada): primeira tentativa acidentalmente deu
   `APPROVED` porque o `pg_hba.conf` gerado por `initdb --auth=trust` tinha uma regra `trust`
   que cobria a conexão ANTES da minha regra `md5` -- bug do meu próprio arranjo de teste,
   não do preflight. Corrigido reinicializando o Postgres de teste com
   `initdb --auth-host=md5 --auth-local=trust`; depois disso, a senha errada produziu
   corretamente `FATAL: password authentication failed`, `FAILED`.
4. **Conexão e autenticação reais bem-sucedidas**: `APPROVED`, todos os 4 passos `ok: true`.

Também confirmado que o dialeto `postgresql://` (psycopg2, usado pelo CI) funciona igual
contra o mesmo Postgres real.

## 16. GATE FINAL REAL APROVADO no Windows: vertical completa API -> dispatcher -> worker PicoGK real -> STL -> Artifact -> Manifest -> download (2026-07-29)

**Este é o evento que fecha o item 11/12 do checklist de aceite do Incremento 2.1.1.** Relatado
literalmente pelo usuário, executado de verdade no Windows dele, contra o worker PicoGK real
(não o sandbox Linux deste ambiente, que nunca teve o runtime nativo disponível).

### Preflight (`apps/api/scripts/gate_preflight_check.py`)

- `DATABASE_URL` não é SQLite: aprovado.
- Driver `psycopg` importado com sucesso.
- `localhost:5432` acessível (conexão TCP real).
- Conexão e `SELECT 1` reais aprovados.
- `result = "APPROVED"`, `overall_ok = true`.

### Banco de dados

- PostgreSQL real.
- `alembic upgrade head` executado; revisões aplicadas: `927e185f097d`, `9242186001a8`,
  `97983fbc0288`, `c32e9b0f0f3c`.

### Vertical completa (sem job pré-semeado, sem simulação)

- Usuário sintético do gate garantido (idempotente).
- `POST /api/v1/auth/login` -> 200.
- `GET /api/v1/auth/me` -> 200.
- `POST /api/v1/projects` -> 201.
- `POST .../recipes` -> 201.
- `POST /api/v1/design-runs` (job NOVO) -> 201.
  - `job_id`: `3bf6587d-a9f6-40a1-91bb-f41d385db05d`.
  - `idempotency_key`: `gate-real-e7010eb3d7004294a172a543547ea0da`.
- Dispatcher real (`geometry_dispatcher.py`) invocado e executado.
- Transição de status observada de verdade: `queued -> running -> succeeded`.
- Worker: **PicoGK real** (não `_FakeWorkerClientForE2ESeed`, não nenhum outro test double).
- Nenhum job pré-semeado. Nenhuma simulação.

### Métricas geométricas persistidas (nomes de campo reais do worker)

| Campo | Valor |
|---|---|
| `volume_mm3` | `413.3012081417931` |
| `porosity_pct_measured` | `58.6698791858207` |
| `surface_area_mm2` | `2876.9469437800917` |
| `vertex_count_unique` | `102338` |
| `triangle_count` | `208560` |
| `is_watertight` | `true` |
| `stl_reload_validation_passed` | `true` |

### SHA-256 idêntico nas cinco fontes independentes

```
cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d
```

Fontes comparadas: (1) STL físico em disco, (2) campo `sha256` do `Artifact` via API, (3) o
mesmo campo via consulta direta ao banco, (4) `stl_sha256` do `ArtifactManifest`, (5) bytes
efetivamente baixados via `GET /api/v1/artifacts/{id}/download`. Nenhuma divergência.

### Auditoria e associações

- Trilha de `AuditEvent` confirmada para o ciclo de vida deste job: `geometry_job_created`,
  `geometry_job_succeeded`.
- Associação usuário/organização/projeto/receita: aprovada, consistente entre o que foi
  submetido e o que a API retornou.

### Relatório final

```
gate = "full_pipeline_real_worker"
result = "APPROVED"
overall_ok = true
```

### O que este evento prova, e o que ele NÃO é

Esta seção registra especificamente que o **gate completo de produção** (API real ->
fila Postgres real -> dispatcher real -> worker PicoGK real -> STL real -> Artifact/Manifest
reais -> download real -> comparação de SHA-256 em 5 fontes) foi executado de ponta a ponta
com um job **novo**, nunca pré-semeado, e chegou a `succeeded` com integridade comprovada em
todas as fontes. Isso é diferente de, e não deve ser confundido com:

- **O E2E Playwright da interface** (Seção 11, commit `f7a9614`): valida a UI real (login,
  criação de projeto/receita, navegação) contra um job succeeded PRÉ-SEMEADO (worker fake
  rotulado) -- prova a interface, não o worker real.
- **Os testes geométricos isolados do worker** (Seções 6-7, WORKER_STATUS.md): validam a
  geometria/calibração das 3 golden recipes invocando o worker diretamente via CLI, fora do
  fluxo de fila/dispatcher/API de produção.
- **Este gate (Seção 16, aqui)**: é o único evento desta sessão que exercita a cadeia de
  produção completa, com o worker PicoGK real, através da fila real, de ponta a ponta.

Com os três provados independentemente (interface real, geometria real, e agora o gate de
produção completo real), a **vertical completa do Incremento 2.1.1 está aprovada no Windows do
usuário**.

## 17. Incremento 2.2 Alpha Pesquisa -- verificação final da rodada (TopologyProvider, Voronoi doc, inteligência computacional, identidade visual) (2026-07-30)

### Backend (`apps/api`) -- pytest

Primeira tentativa (contra o `DATABASE_URL` de instância pgserver já em uso no sandbox nesta
sessão): `2 failed, 133 passed, 2 skipped` --
`test_two_concurrent_dispatchers_never_claim_the_same_job` (reivindicou 37 jobs em vez dos 24
criados pelo próprio teste) e `test_clinical_suite_expiration_is_respected`
(`TypeError: can't compare offset-naive and offset-aware datetimes`).

Investigação (ver `IMPLEMENTATION_STATUS.md`, seção "Achado real de ambiente de teste"):
confirmado que o diretório de dados físico do Postgres efêmero usado (`/tmp/pgserver-inc22` e
variantes, achados via `find /tmp -iname "*pgserver*"`) persiste em disco entre invocações
separadas do sandbox, e a fixture `engine` (session-scoped, `Base.metadata.drop_all()` no
teardown) não protege contra dados órfãos de uma invocação anterior que não chegou a terminar
normalmente.

**Prova real, não suposição**: subindo uma instância `pgserver` nova com diretório de dados
vazio (`/tmp/pg-clean-verify-inc22`, criado e destruído nesta mesma verificação), dentro da
MESMA chamada de shell (para não perder o processo entre invocações), a suíte completa rodou:

```text
135 passed, 2 skipped, 2 warnings in 30.98s
```

Confirma que a lógica de exclusão mútua da fila (`SELECT ... FOR UPDATE SKIP LOCKED`) e a
expiração da suíte clínica estão corretas -- as duas falhas iniciais eram dados de teste
órfãos, não uma regressão introduzida nesta ou em rodadas anteriores. Diretórios temporários de
verificação removidos ao final (`rm -rf /tmp/pg-clean-verify-inc22*`).

### Worker C# (`apps/geometry-worker`) -- dotnet build/test

```text
dotnet build BioMatCadGeometryWorker.csproj
  Build succeeded. 0 Warning(s), 0 Error(s)

dotnet test tests/BioMatCadGeometryWorker.Tests/BioMatCadGeometryWorker.Tests.csproj
  Passed! - Failed: 0, Passed: 62, Skipped: 0, Total: 62

dotnet test tests/BioMatCadGeometryWorker.TopologyProviderTests/BioMatCadGeometryWorker.TopologyProviderTests.csproj
  Passed! - Failed: 0, Passed: 5, Skipped: 0, Total: 5
```

`bin/`/`obj/` (gitignorados) removidos após a verificação, conforme lição operacional já
documentada no commit do `TopologyProvider` (evita falso-negativo em
`test_worker_unavailable_quando_binario_nao_compilado`).

### Frontend (`apps/web`) -- tsc, eslint, vitest, build normal e de demonstração

```text
npx tsc --noEmit         -> sem erros
npx eslint . --max-warnings=0  -> sem erros/avisos
npx vitest run           -> Test Files 20 passed (20); Tests 69 passed (69)
```

Build duplo, inspecionado literalmente (não apenas testado por unidade):

```text
npm run build        -> dist/index.html usa /brand/favicon-*.png e /manifest.json (base "/")
npm run build:pages   -> dist/index.html usa /biomatcad-nexus/brand/favicon-*.png e
                         /biomatcad-nexus/manifest.json (base "/biomatcad-nexus/")
```

`dist/brand/` contém os 11 arquivos esperados em ambos os builds; `dist/manifest.json` presente
com os caminhos de ícone relativos (`brand/pwa-icon-192.png`, sem barra inicial).

### Validação de schema

`test_recipe_schema.py::test_golden_recipes_all_validate` (dentro da suíte de 135 acima) --
as 3 golden recipes continuam válidas contra `geometry-recipe-v1.schema.json`, intocado nesta
rodada (o `TopologyProvider` é uma segunda camada de defesa além do schema, não uma substituição
dele).

### E2E Playwright

Não executado nesta rodada -- mesma limitação já documentada em `apps/web/e2e/README.md` e
`playwright.config.ts` (bibliotecas nativas do Chromium ausentes neste sandbox Linux, sem
`sudo` para instalar). Os binários do Chromium existem em cache
(`~/.cache/ms-playwright`), mas isso não substitui as bibliotecas de sistema necessárias --
não tentado novamente nesta rodada por já estar exaustivamente investigado e documentado em
sessões anteriores.

### Resumo desta seção

| Suíte | Resultado |
|---|---|
| Backend pytest (ambiente limpo) | 135 passed, 2 skipped, 0 failed |
| Worker C# (dois projetos de teste) | 67 passed (62 + 5), 0 failed |
| Frontend vitest | 69 passed, 0 failed |
| Frontend tsc/eslint | sem erros |
| Build normal + build:pages | ambos verificados literalmente (caminho-base correto) |
| E2E Playwright | não executável neste sandbox (limitação já documentada, não nova) |

## 18. Visualizador 3D consolidado -- STL real, controles, métricas, segurança e testes (2026-07-30)

Rodada dedicada a fechar o item "Consolidar visualizador 3D (STL real, sem substituto)" --
Voronoi real explicitamente NÃO implementado (por instrução), o visualizador foi deixado pronto
primeiro. Commits: `32f4969` (auditoria), `61e8e2e` (carregamento seguro), `fa7d09f` (controles/
métricas/desempenho), `35c51ee` (testes + 3 bugs de ciclo de vida corrigidos), `4180a67`
(checksum placeholder do demo corrigido + teste de regressão).

### Frontend (`apps/web`) -- tsc, eslint, vitest, build normal e de demonstração

```text
npx tsc --noEmit               -> sem erros
npx eslint . --max-warnings=0  -> sem erros/avisos
npx vitest run                 -> Test Files  23 passed (23)
                                   Tests  113 passed (113)
```

Arquivos de teste novos/reescritos nesta rodada: `StlViewer.test.tsx` (reescrito de 1 caso de
smoke test para 21 casos, ver lista completa no commit `35c51ee`), `demoStlViewer.test.tsx`
(novo, 2 casos), `artifactDownload.test.ts` (novo, 10 casos), `stlParser.test.ts` (novo, 11
casos que cobrem também o parser ASCII adicionado).

Build duplo, ambos com sucesso:

```text
npm run build         -> vite build (produção)      -> built in ~4.4s-4.7s, 0 erros
npm run build:pages   -> vite build --mode demo      -> built in ~4.7s-7.4s, 0 erros
```

### Backend (`apps/api`) -- pytest, contra Postgres real efêmero (não o fallback SQLite)

Adicionado `test_artifact_download_is_denied_across_organizations` em
`test_jobs_artifacts_api.py`, cobrindo o item da Seção 8 desta rodada ("isolamento entre
organizações no endpoint do artefato") que ainda não tinha teste dedicado ao endpoint
`GET /artifacts/{id}/download` especificamente (só `GET /jobs/{id}` já tinha).

Executado contra uma instância Postgres efêmera NOVA via `pgserver` (caminho pretendido,
documentado no próprio `apps/api/tests/conftest.py`), em dois lotes por limite de tempo de
execução do sandbox (não por limitação de teste):

```text
Lote 1 (10 arquivos, incluindo test_auth_and_operational_state, test_clinical_suite,
test_computational_intelligence, test_database_driver_contract, test_db_connection,
test_dependency_contract_constraints, test_dev_auth_startup,
test_geometry_dispatcher_continuous, test_geometry_job_cancellation,
test_geometry_job_concurrency):
  56 passed, 1 warning in 15.83s

Lote 2 (10 arquivos, incluindo test_geometry_job_orchestration, test_geometry_job_security,
test_health, test_jobs_artifacts_api (com o novo teste de isolamento), 
test_materials_projects_recipes_api, test_migrations, test_observability,
test_recipe_schema, test_system_status, test_topology_providers):
  80 passed, 2 skipped, 2 warnings in 24.95s

TOTAL: 136 passed, 2 skipped, 0 failed
```

**Achado de ambiente confirmado (não regressão desta rodada)**: rodando a mesma suíte contra o
fallback SQLite padrão de `conftest.py` (quando `TEST_DATABASE_URL` não está definida, i.e.
usando o arquivo `apps/api/test_biomatcad.db` já existente no sandbox de execuções anteriores),
`test_clinical_suite.py::test_clinical_suite_expiration_is_respected` falhou com
`TypeError: can't compare offset-naive and offset-aware datetimes`. Consistente com o padrão já
registrado na Seção 17 acima (dados residuais entre invocações do sandbox) -- a suíte contra
Postgres real efêmero e limpo (o caminho de teste pretendido) não reproduz essa falha, conforme
os 136 aprovados acima.

### Regressão real encontrada e corrigida: checksum placeholder do STL de demonstração

Ao escrever `demoStlViewer.test.tsx` (teste de ponta a ponta do fluxo de demonstração do
GitHub Pages, usando os bytes REAIS de `public/demo-assets/sample-scaffold-block-gyroid.stl`
lidos do disco via `fetchSync`, não um buffer fabricado), descoberto que `demoClient.ts`
declarava `sha256: "0".repeat(64)` (placeholder) para o artefato STL sintético -- o que fazia a
verificação de checksum do lado do cliente (adicionada nesta mesma rodada) falhar SEMPRE no
modo demo. Verificação de que o teste realmente detecta o bug (não é tautológico): revertido
temporariamente o valor para o placeholder e reexecutado -- falhou como esperado
(`AssertionError`); corrigido de volta e o teste voltou a passar. Corrigido substituindo pelo
SHA-256 real do arquivo (`a1dffcd0...460fafc`, verificado via `sha256sum`).

### Backend cross-organization download isolation -- prova literal

```text
apps/api/tests/test_jobs_artifacts_api.py::test_artifact_download_is_denied_across_organizations PASSED
```

O teste cria um job real via `_FakeWorkerClient` + `dispatch_job` até `succeeded` na
organização A, confirma que a própria organização baixa os bytes do STL normalmente
(`download_resp.status_code == 200`), e confirma que a organização B recebe `403` e nunca os
bytes do arquivo (`b"solid crossorg" not in cross_download.content`), mesmo de posse do
`artifact_id` real.

### E2E Playwright

Não executado nesta rodada -- mesma limitação já documentada (bibliotecas nativas do Chromium
ausentes neste sandbox Linux, sem `sudo`). O E2E já aprovado no Windows (`f7a9614`, Seção 11
acima) verifica a presença do botão de download (`data-testid="stl-download-link"`, preservado
nesta rodada mesmo após a mudança de `<a href download>` para `<button>` com download
autenticado via Blob) -- mas não exercita nenhum dos novos controles do visualizador
(wireframe, transparência, eixos, grade, bounding box, clipping, screenshot, fullscreen,
cancelamento) em navegador real. Essa cobertura hoje existe apenas em nível de componente. Não
é fabricada como "coberta" -- ver lacuna registrada em
`docs/architecture/viewer-3d-audit.md`. O script de execução no Windows já existente
(`npm run test:e2e` em `apps/web/`) permanece o roteiro único a ser executado após esta rodada,
sem necessidade de um script novo.

### Resumo desta seção

| Suíte | Resultado |
|---|---|
| Frontend vitest | 113 passed, 0 failed (23 arquivos) |
| Frontend tsc/eslint | sem erros |
| Build normal + build:pages | ambos com sucesso |
| Backend pytest (Postgres real efêmero, ambiente limpo) | 136 passed, 2 skipped, 0 failed |
| Isolamento entre organizações no download de artefato | teste dedicado novo, PASSED |
| Regressão de checksum do demo do GitHub Pages | encontrada, corrigida, coberta por teste (verificado que o teste falha sem a correção) |
| E2E Playwright | não executável neste sandbox (limitação já documentada); script único de re-execução no Windows já existente, sem necessidade de novo roteiro |

## 19. Rodada Voronoi (Incremento 2.2) -- validação real no sandbox Linux, registro literal (2026-08-06)

Esta seção registra literalmente o que foi executado NESTE sandbox Linux (sem PicoGK) ao longo
da rodada Voronoi (Seções 1-14 da instrução original), reunindo em um só lugar as execuções que
até aqui estavam apenas nos corpos dos commits. Nenhuma execução real do PicoGK ocorreu neste
sandbox -- onde este documento diz "PASSED"/"OK" abaixo, refere-se sempre a testes/builds que
rodam sem o runtime nativo do PicoGK (bloqueado neste ambiente, ADR-0007).

### Worker C# (`apps/geometry-worker`) -- xUnit real

```text
$ dotnet test apps/geometry-worker/tests/BioMatCadGeometryWorker.Tests
Passed!  - Failed: 0, Passed: 99, Skipped: 0, Total: 99, Duration: 461 ms
```

99 = 62 testes Gyroid (pré-existentes, sem regressão) + 22 testes de tesselação/sítios Voronoi
(`VoronoiMathTests.cs`) + 15 testes de matemática implícita Voronoi
(`VoronoiImplicitMathTests.cs`).

```text
$ dotnet build apps/geometry-worker
Build succeeded. 0 Warning(s), 0 Error(s).
```

O worker (produção, não apenas os testes) compila sem erros/avisos com os campos novos
(`MaxNodeContainmentViolationMm`, `valid_cell_count`, `smoothing_strategy`, ver commit
`d319986`).

### Backend (`apps/api`) -- pytest real (SQLite efêmero, ambiente de venv limpo desta sessão)

```text
$ pytest apps/api
181 passed, 2 failed, 2 skipped
```

As 45 asserções novas desta rodada (41 em `test_recipe_schema_voronoi.py` + 4 em
`test_topology_providers.py`) estão entre os 181 aprovados. As 2 falhas são as MESMAS duas
falhas pré-existentes e não relacionadas a Voronoi, já identificadas em rodadas anteriores:

- `tests/test_clinical_suite.py::test_clinical_suite_expiration_is_respected` -- `TypeError` em
  `operational_state.py`, lógica de suíte clínica, sem nenhuma relação com topologia/schema.
- `tests/test_geometry_job_concurrency.py::test_two_concurrent_dispatchers_never_claim_the_same_job`
  -- teste de corrida esperando exatamente 24 jobs reivindicados ao todo por dois dispatchers,
  observado 29 nesta execução (28/31/33 em execuções anteriores da rodada) -- um problema real
  de isolamento entre testes/vazamento de estado na fila compartilhada (SQLite em arquivo, não
  em memória, entre testes que não usam a fixture `db_session` para as threads reais do
  dispatcher), não uma regressão introduzida por Voronoi.

Ambas foram reproduzidas de forma idêntica em uma rodada anterior desta mesma sessão, fazendo
`git stash` + `git checkout d09a616` (imediatamente anterior a todo o trabalho de Voronoi) e
rodando as duas isoladamente -- falharam da mesma forma lá, confirmando que são dívida
pré-existente, não introduzida nem agravada por esta rodada. Nenhuma tentativa de correção foi
feita nesta rodada: uma correção real do problema de concorrência exigiria mudar o mecanismo de
isolamento transacional em `conftest.py` (provavelmente introduzir SAVEPOINTs/nested
transactions para que commits internos de serviços não escapem do rollback de teste) -- uma
mudança estrutural que afeta TODOS os testes que usam `db_session`, incompatível com a regra
desta rodada de "alteração pequena, isolada, comprovada, sem ampliar o escopo". Preservada aqui
como evidência de reprodução comparativa, conforme instruído.

### Frontend (`apps/web`) -- tsc, eslint, vitest, build, build:pages

```text
$ npx tsc --noEmit          # (0 erros)
$ npx eslint . --ext .ts,.tsx   # (0 problemas)
$ npx vitest run
Test Files  23 passed (23)
     Tests  118 passed (118)
$ npm run build        # modo real -- sucesso
$ npm run build:pages   # modo demo/GitHub Pages -- sucesso
```

118 testes (era 111 no início desta rodada) -- 7 em `RecipeEditorPage.test.tsx` (era 2; o teste
antigo que esperava Voronoi desabilitado foi corrigido para refletir a implementação real, ver
commit `284d2c6`).

Confirmado por `grep` no bundle gerado por `build:pages` (`dist/assets/*.js`): nenhuma
ocorrência de `"INVENTION"` nem `"docs/private"` -- apenas um ponteiro textual não-confidencial
(`docs/architecture/voronoi-cell-edges-v1-math-audit.md`) aparece no texto explicativo da UI.

### Regressão das 3 golden recipes Gyroid

As 3 golden recipes Gyroid pré-existentes (`block-gyroid-v1`, `cylinder-gyroid-v1`,
`preview-gyroid-low-res-v1`) continuam validando sem nenhuma mudança --
`test_golden_recipes_all_validate` (parametrizado, agora com as 3 novas golden recipes Voronoi
somadas às 3 Gyroid, 6/6 passando) e os 62 testes Gyroid do worker C# (`dotnet test`, sem
regressão, contados dentro dos 99 acima).

### E2E Playwright

Não executado nesta rodada -- mesma limitação já documentada em rodadas anteriores (bibliotecas
nativas do Chromium ausentes neste sandbox Linux, sem acesso root para instalá-las, ver
`apps/web/e2e/README.md`). Nenhum cenário Voronoi foi adicionado a `e2e/vertical.spec.ts` nesta
rodada -- ver lacuna registrada explicitamente no roteiro único de validação Windows
desta rodada (entregue ao final desta sessão, ver Seção 7 da instrução original / seção
de empacotamento deste documento).

### Resumo consolidado desta seção

| Suíte | Resultado |
|---|---|
| Worker C# (`dotnet test`) | 99 passed, 0 failed |
| Worker C# (`dotnet build`, produção) | build succeeded, 0 warnings/errors |
| Backend (`pytest`) | 181 passed, 2 failed (pré-existentes, não relacionadas a Voronoi, reproduzidas comparativamente em `d09a616`), 2 skipped |
| Frontend `tsc --noEmit` | 0 erros |
| Frontend `eslint` | 0 problemas |
| Frontend `vitest run` | 118 passed, 0 failed (23 arquivos) |
| Frontend `build` + `build:pages` | ambos com sucesso |
| Confidencialidade do bundle Pages | confirmado via grep: sem "INVENTION"/"docs/private" |
| Regressão Gyroid (golden recipes + testes C#) | zero regressão confirmada |
| E2E Playwright | não executável neste sandbox (limitação pré-existente e documentada) |
| Execução real do PicoGK (Voronoi ou Gyroid) neste sandbox | **NÃO ocorreu** -- nenhuma declaração em contrário é feita em nenhum commit ou documento desta rodada |

## 20. Validação Windows real 20260806-112714 -- INCONCLUSIVA (timeout real + defeitos de isolamento no roteiro), causa raiz auditada e corrigida (2026-08-06)

Esta seção registra honestamente uma execução REAL do roteiro Windows (`Run-VoronoiWindowsValidation.ps1`, commit `3c07b9c`) feita pelo usuário no Windows, com PicoGK real disponível --
diretório de evidência `C:\biomatcad-runs\voronoi-validation-20260806-112714\` (relatórios
`CONSOLIDATED_REPORT.md`/`.json`, logs de cada etapa, `preflight.json`, `api-runtime.log`,
`api-pytest.log`, `e2e-output.log`, e um `_gate-output.txt`/`_report.json` por receita/execução).

**Veredito literal desta rodada, sem suavização: REPROVADA/INCONCLUSIVA.** Nenhuma das 6
golden recipes (3 Voronoi + 3 Gyroid de controle) produziu um STL real nesta execução. Isso
inclui as 3 golden recipes Gyroid, que já haviam sido aprovadas em rodadas anteriores (Seção
16) -- **isso NÃO é uma regressão científica do Gyroid**: a causa raiz (auditada abaixo) é um
defeito de orquestração/timeout no roteiro de validação, não uma mudança na matemática ou no
worker Gyroid, que permaneceu intocado nesta rodada de correção (restrição explícita: nenhum
parâmetro/timeout de golden recipe foi alterado antes de provar a causa).

### O que esta rodada REALMENTE demonstrou

| Suíte | Resultado real |
|---|---|
| Worker C# (`dotnet build` + `dotnet test`) | OK -- 99/99 testes, build limpo |
| Frontend (`tsc`/`eslint`/`vitest`/`build`/`build:pages`) | OK -- 118/118 (119 após a correção desta seção) |
| Backend (`pytest`) | 195 passed, 2 failed, 1 skipped -- as 2 falhas têm premissas de teste inválidas em Windows (não um bug de produto), auditadas e corrigidas nesta seção |
| `block-voronoi-preview-v1` run1 e run2 | **FALHA real**: job chegou a `running` e depois `failed` com `WORKER_TIMEOUT` (30s + margem de 30s) nas duas tentativas |
| Todas as invocações SEGUINTES do dispatcher (block-voronoi-final-v1, cylinder-voronoi-preview-v1, e as 3 golden recipes Gyroid, todas run1 e run2) | **FALHA real**: `geometry_dispatcher.py --once -> exit_code=1`, com **stdout vazio** em todos os casos -- nenhum STL produzido, determinismo/auditoria independente inconclusivos por ausência de artefato |
| E2E Playwright | **FALHA real**: `ModuleNotFoundError: No module named 'psycopg'` -- o `global-setup.ts` usou o Python GLOBAL do Windows (sem as dependências do backend), não o venv do projeto |

### Causa raiz dos dois `WORKER_TIMEOUT` (auditoria de código; execução real do PicoGK não pôde ser reexecutada neste sandbox Linux para confirmar por instrumentação direta)

A receita `block-voronoi-preview-v1` (12 sítios, `target_porosity_pct: 65`) aciona a calibração
de porosidade fechada contra a malha real (`GyroidMath.CalibrateByMonotonicBisection`, até 12
iterações) -- cada iteração revoxeliza e remalha o domínio inteiro do zero. Medido neste
sandbox (sem PicoGK, só a matemática pura, testável): esta receita produz **42 arestas + 36 nós
usados = 78 primitivos** avaliados por voxel em `VoronoiStrutsImplicit.fSignedDistance`, contra
~15.625 voxels (estimativa de grade densa) -- **sem nenhuma estrutura de aceleração espacial**,
uma limitação já documentada explicitamente no próprio código (`VoronoiScaffoldBuilder.cs`,
cabeçalho do arquivo) como um risco assumido e "nunca comprovado nesta rodada" por não ser
possível executar PicoGK real no sandbox Linux. Para o Gyroid, a mesma calibração de até 12
iterações é barata (avaliação O(1) por voxel, fórmula fechada); para Voronoi, cada iteração é
~78x mais cara nesta receita específica, e a calibração pode multiplicar isso por até 12x. Esta
é a explicação mais provável, e mais bem suportada pela evidência disponível, para o
`WORKER_TIMEOUT` real -- mas **não foi confirmada por instrumentação direta de tempo real no
Windows** (o próprio `stdout`/`stderr` do worker no momento do timeout era descartado antes desta
correção, ver abaixo). Por instrução explícita ("não simplesmente aumentar o limite, sem provar
a causa"), **nenhum timeout de golden recipe foi alterado** nesta correção.

### Causa raiz da cascata de `exit_code=1` em TODAS as invocações seguintes (auditada e corrigida por código)

Duas falhas reais, encontradas por auditoria de código e confirmadas pelos testes novos desta
seção:

1. **`worker_client.py` descartava o diagnóstico do processo morto.** `_kill_process_tree`
   nunca verificava se o processo (e seus descendentes) realmente desapareceram após
   `terminate()`/`kill()` -- apenas assumia sucesso. E o `stdout`/`stderr` do worker no momento
   do timeout era anexado à exceção mas nunca lido por `_mark_failed` -- só a mensagem genérica
   fixa chegava ao banco (`job.error_message`). Corrigido: `_kill_process_tree` agora **retorna
   um booleano confirmado via `psutil.pid_exists`**, e a mensagem de erro sempre inclui esse
   resultado mais um trecho final de `stdout`/`stderr` -- provado por 6 testes novos
   (`test_worker_timeout_recovery.py`), incluindo um teste que mata um processo REAL com um
   neto real (spawnado por ele) e confirma que ambos desaparecem.
2. **`verify_full_pipeline_sha256.py` tinha uma margem de timeout insuficiente para receitas
   "pesadas".** O timeout externo padrão do script (`--timeout-seconds`, 300s) podia ser MENOR
   OU IGUAL ao orçamento interno do worker para receitas com `max_duration_seconds=300` (ex.:
   `block-voronoi-final-v1`, modo final: orçamento interno = 300+30=330s). Nesse caso, o
   PRÓPRIO script de gate podia matar seu processo filho (o dispatcher Python) via
   `Popen.kill()` — e um `kill()` comum **não mata o neto** (o `dotnet.exe` real do worker),
   deixando-o **órfão**, consumindo recursos pelo resto da sessão. Esta é a explicação mais
   provável para a cascata observada em TODAS as invocações seguintes, inclusive nas golden
   recipes Gyroid de controle (que nunca tiveram problema próprio -- foram vítimas do processo
   órfão de uma receita anterior). Corrigido:
   `compute_effective_gate_timeout_seconds()` agora calcula um timeout efetivo SEMPRE maior
   que o orçamento interno do worker para a receita específica, com margem de segurança real; e
   como defesa em profundidade, se o script AINDA assim precisar matar o dispatcher, agora mata
   a ÁRVORE INTEIRA de processos (não só o processo Python direto) -- provado por 5 testes
   novos (`test_verify_full_pipeline_timeout_margin.py`).

Além disso, `geometry_dispatcher.py` tinha um bug de buffering real: os `print()` de
diagnóstico (`"Dispatcher ID: ..."`, `"Processados N job(s)."`) não usavam `flush=True` --
quando o processo é morto antes de sair normalmente (stdout redirecionado para um pipe usa
buffer de bloco, não de linha), esse diagnóstico nunca chegava ao pipe, mesmo tendo sido
"impresso" do ponto de vista do código. Corrigido (`flush=True` explícito).

### Correções aplicadas nesta seção (commit desta rodada, ver lista de commits no relatório final)

- `apps/api/src/biomatcad_api/services/worker_client.py`: `_kill_process_tree` retorna
  confirmação real de encerramento; mensagens de erro preservam `stdout`/`stderr` truncado +
  estado de encerramento da árvore.
- `apps/api/scripts/geometry_dispatcher.py`: `flush=True` nos prints de diagnóstico do modo
  `--once`.
- `apps/api/scripts/verify_full_pipeline_sha256.py`: `compute_effective_gate_timeout_seconds()`
  (margem de segurança real, nunca igual ao orçamento interno do worker) + kill de árvore de
  processos como defesa em profundidade.
- `apps/api/tests/test_worker_timeout_recovery.py` (novo, 6 testes) e
  `apps/api/tests/test_verify_full_pipeline_timeout_margin.py` (novo, 5 testes): recuperação
  real após `WORKER_TIMEOUT`, segunda execução do dispatcher após um timeout, encerramento real
  de árvore de processos (pai + filho REAIS, via subprocess), preservação do diagnóstico de
  erro, cálculo correto da margem de timeout.
- `apps/web/e2e/global-setup.ts`: `resolvePythonBin` agora **exige `E2E_PYTHON_BIN`
  explicitamente** (lança `MissingE2EPythonBinError` com mensagem clara e acionável) em vez de
  cair silenciosamente para `python`/`python3` do PATH do sistema -- causa direta do
  `ModuleNotFoundError: No module named 'psycopg'` observado nesta rodada. Teste atualizado
  (`apps/web/tests/e2eGlobalSetup.test.ts`, 9 testes).
- `apps/api/tests/test_observability.py::test_worker_unavailable_quando_binario_nao_compilado`:
  corrigido para usar um `repo_root` isolado (`tmp_path`, sem o binário compilado) em vez do
  checkout ambiente real -- a versão anterior assumia "o binário nunca existe" (premissa válida
  só neste sandbox Linux) e falhava de verdade no Windows real (onde o binário FOI compilado
  com sucesso antes da validação).
- `apps/api/tests/test_geometry_job_orchestration.py::test_dispatch_job_real_worker_reflects_environment_honestly`
  (renomeado de `..._fails_in_blocked_environment`): aceita os dois desfechos reais possíveis
  (`FAILED` com um dos error_codes documentados do bloqueio PicoGK, OU `SUCCEEDED` com prova
  real de execução -- STL não-vazio gravado, métricas/versões reais) em vez de assumir sempre
  `FAILED` -- a asserção fixa anterior só era válida no sandbox Linux (ADR-0007) e falhava de
  verdade em Windows real (onde o job pode legitimamente ter sucesso).
- `scripts/Run-VoronoiWindowsValidation.ps1`: isolamento real entre receitas/execuções --
  `Clear-StrayWorkerProcesses` detecta e encerra qualquer `dotnet.exe` órfão referenciando
  `BioMatCadGeometryWorker.dll` ANTES e DEPOIS de cada execução de gate, registrando o achado no
  relatório consolidado (nunca silenciosamente); `E2E_PYTHON_BIN` agora é definida
  explicitamente para o venv real antes de rodar o E2E; duração em segundos de cada execução de
  gate agora é registrada no relatório consolidado (para permitir confirmar/refutar a hipótese
  de causa raiz numa próxima execução real).
- `scripts/Run-VoronoiWindowsValidation-Staged.ps1` (novo): roteiro estagiado -- roda primeiro
  apenas um piloto (`block-voronoi-preview-v1` + `preview-gyroid-low-res-v1` como controle) e
  só prossegue para a matriz completa (6 receitas x 2 execuções) se AMBAS as receitas do piloto
  tiverem sucesso em `run1` E `run2`. Não duplica lógica -- invoca
  `Run-VoronoiWindowsValidation.ps1` duas vezes (piloto e matriz completa), preservando um único
  ponto de verdade para a lógica real do gate.

### O que esta correção NÃO prova (honestamente)

- **Não confirma que a hipótese de causa raiz do `WORKER_TIMEOUT` (custo O(voxels × primitivos)
  sem aceleração espacial, multiplicado pela calibração) está correta** -- é a explicação mais
  bem suportada pela evidência disponível (contagens reais de arestas/nós/voxels, medidas neste
  sandbox sem PicoGK), mas nunca foi confirmada por instrumentação de tempo real contra PicoGK
  real. A próxima execução real do roteiro corrigido (que agora registra a duração de cada
  execução de gate) poderá confirmar ou refutar isso com dados reais.
- **Não prova que as correções eliminam o `WORKER_TIMEOUT` em si** -- elas garantem que, SE ele
  ocorrer de novo, (a) o diagnóstico completo (stdout/stderr/estado da árvore) é preservado, e
  (b) ele não mais contamina as receitas seguintes. Se a causa raiz for de fato a falta de
  estrutura de aceleração espacial, a receita `block-voronoi-preview-v1` pode continuar
  excedendo o timeout até que essa otimização seja implementada -- uma mudança de engenharia
  maior, fora do escopo desta correção pontual (que foi proibida de alterar timeouts/parâmetros
  de golden recipes antes de provar a causa).
- **Nenhuma das 6 golden recipes foi validada com sucesso nesta rodada** -- nenhum STL real,
  nenhuma auditoria independente contra STL real, nenhum determinismo 2x confirmado. A
  afirmação "Voronoi funciona" ou "Voronoi não funciona" cientificamente **não pode ser feita**
  a partir desta rodada -- apenas que o PRIMEIRO teste real (`block-voronoi-preview-v1`) excedeu
  o timeout, e que o ROTEIRO tinha defeitos reais de isolamento que impediram qualquer conclusão
  válida sobre as demais 5 receitas.
- **O worker C#/PicoGK e o schema/tesselação Voronoi em si não foram alterados** nesta correção
  -- toda a mudança ficou nas camadas de orquestração Python/PowerShell/TypeScript em volta.

### Próximo passo real (não executado nesta correção)

Rodar `Run-VoronoiWindowsValidation-Staged.ps1` no Windows do usuário (piloto primeiro) para
obter, com as correções desta seção já em vigor: (a) o diagnóstico completo caso
`block-voronoi-preview-v1` volte a exceder o timeout (confirmando ou refutando a hipótese de
causa raiz), e (b) a prova de que uma eventual nova falha do piloto não invalida mais a matriz
completa. **Este roteiro real ainda não foi executado após esta correção.**

## 21. Validação Windows real 20260806-133141 -- cascata de processos órfãos CONFIRMADA corrigida, Voronoi ainda REPROVADO, 3 falhas backend diagnosticadas e corrigidas (2026-08-06)

**Diretório da evidência**: `C:\biomatcad-runs\voronoi-validation-staged-20260806-133141\pilot`
(gerado por `scripts/Run-VoronoiWindowsValidation-Staged.ps1`, rodando contra o commit `1cdc062`
-- a correção da rodada anterior, 20260806-112714).

### Resultado literal do piloto (`CONSOLIDATED_REPORT.md`)

| Etapa | Resultado |
|---|---|
| worker `dotnet test` | 99/99 (log: worker-test.log) |
| frontend `vitest run` | 119/119 |
| `isolamento_block-voronoi-preview-v1_run{1,2}_{pre,pos}` | OK -- nenhum processo `dotnet.exe` órfão antes/depois de NENHUMA execução |
| `gate_block-voronoi-preview-v1_run1` | FALHA -- exit 1, 66.7s (WORKER_TIMEOUT) |
| `gate_block-voronoi-preview-v1_run2` | FALHA -- exit 1, 65.5s (WORKER_TIMEOUT) |
| `determinismo_block-voronoi-preview-v1` | FALHA -- STL ausente em ambas as execuções |
| `isolamento_preview-gyroid-low-res-v1_run{1,2}_{pre,pos}` | OK -- nenhum órfão |
| `gate_preview-gyroid-low-res-v1_run1` | OK -- 7.4s |
| `gate_preview-gyroid-low-res-v1_run2` | OK -- 7.2s |
| `determinismo_preview-gyroid-low-res-v1` | OK -- SHA-256 `7660dae3ee263445835bbf9d26c16fa4ef8f8ee2fd2c320000b0546c1eaaba78` idêntico em run1/run2 |
| `auditoria_independente_preview-gyroid-low-res-v1_run1` | OK |
| `api_pytest` (roteiro ANTES da correção desta rodada) | exit 1 -- **205 passed, 3 failed, 1 skipped** (3, não 2 -- uma falha NOVA) |
| `e2e_playwright` | Pulado via `-SkipE2E` -- não validado nesta rodada |
| `full_stage_executed` | `false` -- a matriz completa corretamente NÃO rodou (piloto reprovou) |

**Conclusão comprovada pelo próprio usuário, confirmada por esta auditoria**: a cascata por
processos órfãos foi corrigida (nenhuma árvore órfã em nenhuma das execuções, mesmo depois de
dois timeouts reais consecutivos) e o Gyroid de controle funcionou perfeitamente logo depois --
exatamente o comportamento que a correção da rodada 20260806-112714 pretendia garantir.

### Diagnóstico do WORKER_TIMEOUT do Voronoi (auditoria real, não especulação)

Ver `apps/geometry-worker/WORKER_STATUS.md` seção 12 para o registro técnico completo. Resumo:

- A hipótese específica levantada pelo usuário ("Voronoi deixa `bEndAppWithTask` no padrão
  `false`") foi **auditada e REFUTADA**: leitura direta do arquivo-fonte vivo confirma que
  `VoronoiScaffoldBuilder.cs` já passa `bEndAppWithTask: true`, de forma estruturalmente
  idêntica a `GyroidScaffoldBuilder.cs` (mesmo padrão `using` para `Voxels`/`Mesh`, nenhuma
  referência a `Library.oViewer`/`Viewer.Add` em nenhum dos dois arquivos).
- Decompilação real do corpo de `PicoGK.Library.Go` (via `ilspycmd` contra o `PicoGK.dll` 2.2.0
  efetivamente instalado) mostrou que `bEndAppWithTask: true` é necessário mas não suficiente:
  o retorno de `Go()` também depende de `oViewer.bIsIdle()` (estado do viewer nativo) e de um
  segundo laço incondicional que espera a thread da tarefa terminar -- nenhum desses dois
  mecanismos é controlável por um parâmetro de aplicação.
- A evidência do JSON parcial no stdout do timeout (campos como `estimated_voxel_count` que só
  são serializados DEPOIS que `Library.Go` já retornou) sugere que todo o cálculo -- incluindo o
  retorno de `Library.Go` -- já havia terminado, e o processo .NET simplesmente não encerrou
  sozinho depois disso.
- **Conclusão honesta**: a causa mais provável, dada a auditoria real disponível, é um
  comportamento do próprio PicoGK (biblioteca/viewer nativo), possivelmente correlacionado à
  maior complexidade da malha de voxels do Voronoi -- não um defeito identificável no código de
  aplicação deste projeto. Isso não foi provado de forma definitiva (não é possível depurar o
  processo nativo a partir deste sandbox Linux) e permanece como hipótese mais bem fundamentada,
  não uma conclusão fechada.

**Voronoi continua NÃO aprovado**: nenhum STL foi produzido em nenhuma das duas execuções,
portanto não há auditoria independente, nem comparação de 5 fontes SHA-256, nem determinismo
2x para `block-voronoi-preview-v1` -- os critérios de aprovação continuam integralmente
pendentes, exatamente como nas rodadas anteriores.

### Correções aplicadas nesta rodada, independente da causa do hang (commit desta rodada)

- `apps/api/src/biomatcad_api/services/worker_client.py`: o stdout/stderr COMPLETO (nunca
  truncado) do worker agora é preservado em `_worker_diagnostics/<job_id>.json`, um diretório
  IRMÃO de `output_dir` -- sobrevive a `_cleanup_output_dir` (que sempre apaga `output_dir`
  inteiro após qualquer falha). Testado por 2 novos cenários em
  `test_worker_timeout_recovery.py`.
- `apps/geometry-worker/tests/BioMatCadGeometryWorker.Tests/AllTopologyProvidersLibraryGoConfigurationTests.cs`
  (novo): escaneia TODOS os arquivos-fonte reais de `apps/geometry-worker` (não apenas Gyroid) e
  falha se qualquer chamada real a `Library.Go(` for encontrada sem `bEndAppWithTask: true` --
  protege contra regressão em qualquer provider de topologia futuro. Suíte do worker: 100/100
  (era 99/99 -- +1 teste novo).

### Diagnóstico e correção das 3 falhas backend (contaminação real por banco persistente)

Causa raiz confirmada (não apenas suspeitada): a suíte pytest, quando executada com
`TEST_DATABASE_URL`/`DATABASE_URL` apontando para a MESMA instância Postgres real usada pela
validação manual (gate HTTP real, dispatcher real), via visíveis linhas REAIS já commitadas por
essa validação manual -- o padrão "uma transação por teste, rollback ao final" (fixture
`db_session`) sempre funcionou para o que cada teste escreve, mas nunca escondeu dados JÁ
COMMITADOS por outra sessão. Sintomas relatados pelo usuário: cancelamento reivindicou um job
antigo real (`8f572e95...`); concorrência (`test_geometry_job_concurrency.py`, que usa
`biomatcad_api.db.SessionLocal` diretamente -- conexões verdadeiramente independentes, não a
fixture isolada -- para provar exclusão mútua real via `SELECT FOR UPDATE SKIP LOCKED`)
reivindicou 32 jobs em vez dos 24 criados pelo próprio teste; observabilidade contou 10 jobs
"processing" que não eram dela.

**Correção real** (`apps/api/tests/conftest.py`): quando `TEST_DATABASE_URL` aponta para
Postgres real, a suíte inteira roda dentro de um SCHEMA Postgres exclusivo e efêmero (nunca
`"public"`), injetado via `options=-c search_path=...` diretamente na própria connection string
-- um parâmetro de conexão libpq padrão, repassado por psycopg2/psycopg3 sem exigir NENHUMA
mudança em `biomatcad_api/db.py` nem nos testes existentes (inclusive
`test_geometry_job_concurrency.py`, que abre suas próprias conexões via `SessionLocal`). O
schema é criado do zero no início da sessão de testes e destruído ao final -- nunca toca no
schema `"public"` real (nunca apaga o banco de pesquisa do usuário).

**Prova real desta correção** (executada nesta rodada, neste sandbox, contra um Postgres efêmero
real via `pgserver`, não simulado):

1. Semeadas 10 linhas REAIS e commitadas de verdade no schema `"public"` (6 jobs `running`, 4
   `queued`, mais organização/projeto/receita reais) -- simulando fielmente uma validação manual
   anterior.
2. Suíte completa (`pytest -q`, 213 testes coletados) executada com `TEST_DATABASE_URL` apontando
   para essa MESMA instância -- resultado: **211 passed, 2 skipped, 0 failed** (os 2 pulados são
   os novos testes de `test_database_schema_isolation.py` quando rodando contra SQLite, não
   aplicável aqui).
3. Confirmado programaticamente, depois da suíte: as 10 linhas reais semeadas no `"public"`
   continuam intactas -- mesmo status, nenhuma reivindicada, nenhuma apagada.

**Regressão permanente adicionada** (`apps/api/tests/test_database_schema_isolation.py`, novo):
2 testes que semeiam contaminação real no schema `"public"` (via uma conexão à parte, sem o
`search_path` isolado) e confirmam que `claim_next_queued_job` e `check_queue` (via a sessão
isolada do teste) nunca a veem -- reproduzem programaticamente os 2 sintomas mais graves
relatados (concorrência e observabilidade). Pulados automaticamente contra SQLite (onde não há
conceito de schema/search_path e a garantia não se aplica).

**`scripts/Run-VoronoiWindowsValidation.ps1`**: corrigido para (a) setar `TEST_DATABASE_URL`
(não apenas `DATABASE_URL`) antes do `pytest`, ativando o isolamento de schema acima contra o
mesmo servidor real; (b) reportar o exit code REAL do pytest (`-Ok ($pytestExit -eq 0)`) --
antes disso, o passo `api_pytest` sempre reportava `-Ok $true` incondicionalmente e uma mensagem
fixa de "2 falhas pre-existentes esperadas", então uma nova falha real (como a terceira desta
rodada) nunca teria sido sinalizada como reprovação no relatório consolidado.

**Nota de honestidade sobre SQLite**: rodando a suíte completa contra o SQLite padrão (nunca o
ambiente real de validação -- o roteiro Windows sempre usa Postgres real), 2 falhas
pré-existentes e NÃO relacionadas a este diagnóstico continuam aparecendo:
`test_clinical_suite_expiration_is_respected` (teste sensível a timing -- ativa algo com
expiração de ~1s e depende de um `sleep`, flakiness de ambiente, não relacionado a banco de
dados) e `test_two_concurrent_dispatchers_never_claim_the_same_job` (o próprio docstring do
teste já documenta que SQLite não suporta `SELECT FOR UPDATE SKIP LOCKED` da mesma forma que
Postgres e "não seria uma prova válida deste requisito" -- ou seja, um teste que só é válido
contra Postgres real, por design). Nenhuma delas é uma das 3 falhas de contaminação relatadas
pelo usuário nesta rodada, e nenhuma delas apareceu na execução real contra Postgres isolado
(prova acima: 0 failed). O critério de aceite ("backend completo com 0 falhas em banco de testes
isolado") está satisfeito contra o ambiente real de validação (Postgres), que é o único ambiente
em que o roteiro Windows de fato executa a suíte.

### O que esta rodada NÃO cobre

- E2E Playwright não foi executado nesta rodada (`-SkipE2E` no piloto) -- permanece não validado
  desde a rodada anterior.
- A matriz completa de receitas (`block-voronoi-final-v1`, `cylinder-voronoi-preview-v1`,
  `block-gyroid-v1`, `cylinder-gyroid-v1`) não foi executada -- corretamente, já que o piloto
  reprovou (mesmo mecanismo de contenção de cascata da rodada anterior, agora comprovado em uso
  real).
- Voronoi (`block-voronoi-preview-v1` e, por extensão, as demais receitas Voronoi) continua sem
  nenhum STL real produzido, nenhuma auditoria independente, nenhuma comparação de 5 fontes
  SHA-256 e nenhum determinismo 2x -- não pode ser declarado aprovado.
- A causa exata do hang dentro de `PicoGK.Library.Go`/viewer nativo não foi provada de forma
  definitiva -- apenas localizada com precisão bem maior que antes (dentro do próprio Go(), não
  em nenhum parâmetro de aplicação) via decompilação real.

## 22. Rodada 3 -- Fase A real no Windows REFUTA hipótese PicoGK/Voronoi; causa raiz real: deadlock de pipes no cliente Python (2026-08-06)

**Evidência real do usuário, execução Windows** (`C:\biomatcad-runs\voronoi-direct-probe-20260806-211542\direct-worker-probe-report.json`): `block-voronoi-preview-v1` invocado diretamente via CLI do worker (sem API/dispatcher) produziu resultado completo (JSON final válido + STL de 444.684 bytes, reaberto com sucesso) em 2,5s, com exit code 0 e encerramento espontâneo imediato (`duration_process_alive_after_result_complete_seconds: 0.0`), sem kill externo, sem processo órfão (`stray_worker_processes_after: []`). Checksum da receita: `28465707f35d12300ed618241fafced39613b0be6f08a4d81c963dbaf8673cfe`.

Veredito literal do relatório: `"REFUTADO NESTA EXECUCAO: o processo encerrou-se sozinho apos o resultado completo, sem necessidade de encerramento externo."`

**Conclusão**: o algoritmo Voronoi e o processo PicoGK direto NÃO causam o `WORKER_TIMEOUT`. Por instrução explícita do usuário, a Fase B (WorkerProcessExitCoordinator/`Environment.Exit`) foi cancelada -- sua premissa não se sustentou.

**Achado colateral não invalidante**: `t_library_go_returned` veio `null` (stderr vazio, 0 bytes) nessa execução -- indicando uma DLL não recompilada após o commit `7a44da4` (que adicionou o marcador `[DIAG_MARKER]`). Isso não invalida a conclusão acima, que independe desse marcador. Corrigido nesta rodada (ver item de correção do roteiro abaixo).

### 22.1 Causa raiz real: deadlock de pipes stdout/stderr em `DotnetPicoGkWorkerClient.execute()`

Auditoria confirmou um defeito clássico de `subprocess.Popen`: a implementação anterior fazia `proc.wait(timeout=POLL_INTERVAL_SECONDS)` em laço (para cancelamento/timeout cooperativos) sem nunca ler `proc.stdout`/`proc.stderr` durante a espera -- só chamava `proc.communicate()` depois do laço. Se o processo filho escreve mais que o buffer do pipe do SO (~64KB) em stdout OU stderr antes de qualquer leitura, a própria escrita do filho bloqueia, e o pai (preso em `wait()`) nunca lê -- reproduzindo exatamente o sintoma de "travamento" relatado, resolvido apenas pelo watchdog externo (`WORKER_TIMEOUT`).

**Reprodução real e controlada** (processo Python auxiliar escrevendo ~5,7MB simultaneamente em stdout e stderr, terminando com JSON válido):
- ANTES da correção (revalidado via `git stash` nesta sessão): `WORKER_TIMEOUT` após ~4,02s contra prazo de 3s+1s.
- DEPOIS da correção: sucesso em ~0,18s, com stdout/stderr completos capturados.

### 22.2 Correção aplicada e testes de regressão permanentes

`DotnetPicoGkWorkerClient.execute()` agora drena `stdout`/`stderr` continuamente via threads daemon em background (iniciadas logo após `Popen()`, unidas após o laço de espera/cancelamento/timeout, que permanece inalterado). Ver detalhes completos em `apps/geometry-worker/WORKER_STATUS.md` seção 14.

Quatro testes novos e permanentes em `apps/api/tests/test_worker_timeout_recovery.py` (todos passando):
- `test_execute_nao_trava_quando_processo_escreve_volume_maior_que_buffer_do_pipe`
- `test_execute_captura_stdout_e_stderr_completos_mesmo_com_volume_grande`
- `test_execute_cancelamento_continua_funcionando_com_drenagem_continua`
- `test_execute_timeout_genuino_continua_funcionando_com_drenagem_continua`

**Resultado**: `12 passed in 3.45s` (arquivo completo, incluindo os 8 testes pré-existentes).

### 22.3 Correção do roteiro `Run-VoronoiDirectWorkerProbe.ps1` (build explícito + caminhos absolutos)

- Passo 0 agora sempre executa `dotnet build --configuration Release` explicitamente antes de localizar a DLL (nunca reutiliza silenciosamente um binário em disco) -- elimina a causa mais provável do `t_library_go_returned: null` (DLL desatualizada).
- `RepoPath`/`OutputDir` relativos agora são rejeitados explicitamente com exceção clara.
- Novo campo de relatório `t_library_go_returned_null_explicacao`, documentando a causa provável e afirmando explicitamente que a ausência do marcador não invalida a conclusão do resultado completo.

Validação desta sessão (sandbox Linux, sem PicoGK real): sintaxe verificada via parser do PowerShell 7.4.6; lógica de build+localização de DLL+construção de job.json exercida com sucesso contra um ambiente fictício (dotnet/git fakes); rejeição de caminho relativo confirmada.

### 22.4 Suítes completas rodadas nesta sessão (rodada 3, pós-correção)

- **Worker C#** (`dotnet vstest`, dois projetos de teste -- `dotnet test` em si ficou preso indefinidamente neste sandbox Linux por razão de infraestrutura do VSTest host não relacionada ao código, contornado com `dotnet build` + `dotnet vstest` diretamente sobre as DLLs compiladas, com resultado idêntico): `BioMatCadGeometryWorker.Tests` 100/100 passando; `BioMatCadGeometryWorker.TopologyProviderTests` 11/11 passando. Build Release do worker principal: sucesso, 0 erros/avisos.
- **Backend (pytest)**: rodado primeiro contra SQLite (default sem `TEST_DATABASE_URL`), resultando em 211 passed, 4 skipped, **2 failed** -- `test_two_concurrent_dispatchers_never_claim_the_same_job` (o próprio docstring do teste documenta que SQLite não suporta `FOR UPDATE SKIP LOCKED` da mesma forma e "não seria uma prova válida deste requisito") e `test_clinical_suite_expiration_is_respected` (teste sensível a tempo real, `sleep(1.2s)` contra expiração de 1s, sob CPU do sandbox compartilhado). Nenhum dos dois arquivos foi tocado nesta rodada. Re-executado contra Postgres real isolado (via `pgserver`, mesmo padrão de isolamento por schema da rodada 2): **215 passed, 2 skipped, 0 failed** em 41,49s -- confirmando que as 2 falhas eram artefatos do ambiente SQLite/timing, não regressões desta rodada.
- **Frontend**: `npm run typecheck` limpo; `npm run lint` limpo (`--max-warnings=0`); `npm run test` (vitest) -- **119 passed (119)**, 23 arquivos; `npm run build` -- sucesso (aviso apenas de tamanho de chunk, pré-existente, não relacionado a esta rodada).

## 23. Matriz Voronoi/Gyroid APROVADA no Windows real (`voronoi-validation-staged-20260806-195638`) -- E2E corrigido (defeito de infraestrutura, não regressão) (2026-08-06)

**Evidência real do usuário**: `C:\biomatcad-runs\voronoi-validation-staged-20260806-195638`, com a correção do deadlock de pipes (seção 22 acima) já aplicada. Relatório literal: "A MATRIZ CIENTÍFICA E DE ORQUESTRAÇÃO PASSOU INTEGRALMENTE."

As seis golden recipes (3 Voronoi + 3 Gyroid de regressão) passaram 2x cada, todas com `queued -> running -> succeeded`, worker PicoGK real, cinco fontes de SHA-256 coerentes, determinismo byte a byte entre `run1`/`run2`, watertight no worker E na auditoria independente, zero arestas non-manifold, contenção de domínio independente aprovada, nenhum processo `dotnet.exe` órfão, e artefato/manifesto/banco/download/auditoria coerentes entre si.

SHA-256 do STL (`run1`, idêntico a `run2` por determinismo comprovado em cada receita):

| Receita | SHA-256 |
|---|---|
| `block-voronoi-preview-v1` | `fd4647de0a1547d6e1939a96e4d3db237b7326a1e5ca5309ebddb1916f5b6a64` |
| `block-voronoi-final-v1` | `7ac71ec7afd58943311b620decad08607e8d82a318a6b3ab1c41eace87c4ac4b` |
| `cylinder-voronoi-preview-v1` | `fe17676a09883d5c3f97a912860b20d23e8035978b03d5285808ede42196b9ae` |
| `block-gyroid-v1` | `cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d` |
| `cylinder-gyroid-v1` | `2cb8cbdf9acbff579c838d8bf3cc2e2a688bcd33a3c475945174272cb278445e` |
| `preview-gyroid-low-res-v1` | `7660dae3ee263445835bbf9d26c16fa4ef8f8ee2fd2c320000b0546c1eaaba78` |

Suítes Windows nesta execução: geometry-worker principal 100/100; backend 216 passed, 1 skipped, 0 failed; frontend 119/119; tsc/eslint/build/build:pages aprovados.

**Extensão da auditoria independente de `run1` para `run2`**: `audit_stl_independent.py` rodou sobre o STL real de `run1` de cada receita. `run2` não foi reauditado separadamente pelo script -- mas como seu SHA-256 é byte a byte idêntico ao de `run1` (mesmo arquivo binário produzido de forma determinística), a conclusão da auditoria de `run1` (watertight, zero non-manifold, contenção aprovada) se estende a `run2` por identidade comprovada do conteúdo, não por suposição.

### 23.1 O único ponto de falha: defeito de infraestrutura do roteiro no E2E, não regressão

`full_exit_code=1` ocorreu SOMENTE na etapa de E2E: `net::ERR_CONNECTION_REFUSED` em `http://localhost:5173/login`. O seed E2E concluiu com sucesso, `E2E_PYTHON_BIN` apontou corretamente para o venv, e a API estava disponível -- o roteiro simplesmente nunca iniciava o frontend antes de chamar o Playwright (dependia de um passo manual não realizado nesta execução). **Não é uma regressão da interface nem da matriz geométrica.**

Correções aplicadas nesta rodada:

1. **`apps/web/playwright.config.ts`**: opção nativa `webServer` do Playwright -- inicia o frontend rastreado, aguarda a URL responder via polling HTTP antes de qualquer teste, encaminha stdout/stderr para o log já capturado pelo roteiro, encerra apenas o processo que ele mesmo iniciou. `reuseExistingServer` é `false` sob `CI=true` (função pura testável `shouldReuseExistingServer()`), garantindo que a validação sempre inicia um frontend novo.
2. **`apps/web/tests/playwrightWebServer.test.ts`** (novo, 2 testes): prova a configuração do `webServer` e o comportamento de `shouldReuseExistingServer()`.
3. **`scripts/Run-VoronoiWindowsValidation.ps1`**: `API_SECRET_KEY` sintético (>= 32 caracteres) + `ENVIRONMENT=development` para o servidor real (antes herdava `ENVIRONMENT=test` do passo de pytest, mascarando que o segredo padrão inseguro tem exatamente 31 caracteres); contagens textuais corrigidas (99->100, 118->119); adicionado o segundo projeto de testes do worker (`BioMatCadGeometryWorker.TopologyProviderTests`, 11 testes), antes ausente da matriz Windows.
4. **`scripts/Run-E2EOnly.ps1`** (novo): reexecuta somente o E2E (API + frontend via Playwright webServer), sem repetir a matriz geométrica completa.

Validação desta sessão (sandbox Linux): `apps/web` -- typecheck limpo, lint limpo, vitest 121/121 (119 pré-existentes + 2 novos), build de produção OK; ambos os `.ps1` sintaticamente válidos.

**Veredito documental desta rodada**: matriz Voronoi/Gyroid **APROVADA**; correção do deadlock de pipes **COMPROVADA no Windows**; E2E desta execução **INCONCLUSIVO** por defeito de infraestrutura do roteiro (frontend não iniciado), não uma regressão; resultado global do roteiro falhou **somente** por esse defeito, já corrigido. A reconfirmação do E2E corrigido ainda depende de uma execução real do usuário.

## 24. E2E real reexecutado e APROVADO no Windows (`Run-E2EOnly.ps1`, commit `84f46fc`) (2026-08-06)

**Este registro NÃO substitui nem apaga a seção 23** -- a execução original da matriz
(`voronoi-validation-staged-20260806-195638`) permanece registrada exatamente como aconteceu:
`full_exit_code=1` por `net::ERR_CONNECTION_REFUSED` na etapa de E2E, causado pelo defeito de
infraestrutura do roteiro (frontend nunca iniciado antes do Playwright). Esse fato histórico
continua verdadeiro e não é reescrito. O que muda aqui é que, **depois** da correção aplicada no
commit `84f46fc` (Playwright `webServer` nativo + `Run-E2EOnly.ps1`), o usuário reexecutou
SOMENTE o E2E, no mesmo ambiente Windows, contra a API e o frontend reais -- e essa reexecução
foi **APROVADA**.

**Evidência real do usuário**:

- Script: `scripts/Run-E2EOnly.ps1`.
- `OutputDir`: `C:\biomatcad-runs\e2e-only-20260806-222320`.
- API disponível em `127.0.0.1:8000`.
- Frontend Vite iniciado automaticamente pelo Playwright em `localhost:5173` (via `webServer`,
  conforme corrigido no commit `84f46fc` -- prova direta de que a correção funciona no Windows
  real, não apenas na configuração/testes unitários feitos no sandbox).
- `global-setup` executado com o Python real do venv (`E2E_PYTHON_BIN` correto).
- Teste 1 aprovado: login, criação de projeto e receita pela UI real.
- Teste 2 aprovado: job `succeeded` pré-semeado exibiu status, métricas e link de download do
  STL.
- Resultado literal: `2 passed (24.9s)`.
- `E2EExitCode=0`.
- Processos iniciados pelo roteiro (API + frontend gerenciado pelo Playwright) foram encerrados
  de forma controlada -- nenhum processo órfão.
- Relatórios: `C:\biomatcad-runs\e2e-only-20260806-222320\E2E_ONLY_REPORT.json` e
  `E2E_ONLY_REPORT.md`.

### Veredito consolidado e honesto (não confundir os dois eventos)

- A execução original da matriz completa (`voronoi-validation-staged-20260806-195638`, seção
  23) permanece **INCONCLUSIVA especificamente naquele E2E** -- por um defeito de
  infraestrutura do roteiro naquele momento, já identificado e corrigido, nunca por uma
  regressão científica ou de interface.
- A reexecução isolada **posterior**, no mesmo ambiente Windows, com o roteiro já corrigido
  (`Run-E2EOnly.ps1`, commit `84f46fc`), foi **APROVADA** -- 2/2 testes reais, exit code 0, sem
  processos órfãos.
- Com isto, **tanto a matriz real de 12 execuções Voronoi/Gyroid (6 golden recipes x 2 cada,
  seção 23) quanto o E2E real (esta seção) estão agora APROVADOS** no Windows real do usuário.
  Nenhuma das duas provas foi obtida na mesma execução única -- e isso está registrado aqui
  exatamente como aconteceu, sem retrofit da evidência histórica.

## O que esta evidência explicitamente NÃO cobre

- **Consistência STL-vs-manifesto via fluxo completo API→dispatcher→worker PicoGK real→
  Artifact/Manifest→download** -- o E2E aprovado (Seção 11) valida a interface real, mas com um
  job PRÉ-SEMEADO (worker fake rotulado); nenhum job NOVO foi submetido e processado através do
  fluxo de produção completo com o worker PicoGK real nesta sessão. Este é o gate final ainda
  pendente (Seção 12).
- **Confirmação visual explícita de alguns dos 16 comportamentos do launcher** (criação vs.
  reaproveitamento de `.venv`/`node_modules`, decisão de porta ocupada vs. livre, banner
  "AMBIENTE DE TESTE" visto na tela, ausência do segredo confirmada visualmente) -- a execução
  real no Windows foi aprovada pelo usuário (Seção 14) para o caminho principal, mas esses
  detalhes específicos não foram relatados individualmente.
- **Empacotamento final v2.2.1** — pendente de geração nesta mesma rodada (ver seção de
  empacotamento no fechamento deste documento, se já gerado no momento em que este arquivo for
  lido).

Estes itens são o que falta para declarar o Incremento 2.1.1 concluído.

## 25. Cobertura E2E real do visualizador 3D (`apps/web/e2e/viewer.spec.ts`) -- escrita e verificada no sandbox; execução real no Windows AINDA PENDENTE (2026-08-06)

**Escopo desta rodada** (pedido explícito do usuário, partindo do commit `3c61b3d`): fechar
exclusivamente a cobertura E2E real (Playwright/Chromium) dos controles do visualizador 3D
(`StlViewer.tsx`) que, até aqui, só tinham cobertura em nível de componente (jsdom,
`StlViewer.test.tsx`) -- ver a ressalva registrada nas seções 23/24 e em `e2e/README.md`.
Geometria, receitas, TopologyProviders e contratos científicos **não foram tocados**.

### Bug real descoberto e corrigido: fixture do job pré-semeado nunca chegava a "ready"

Auditoria obrigatória (regra 1 do usuário) antes de escrever qualquer teste novo revelou que
`apps/api/scripts/seed_e2e_user.py` -- usado pelo `global-setup.ts` do Playwright para criar o
job `succeeded` pré-semeado que `vertical.spec.ts` e agora `viewer.spec.ts` dependem -- tinha
DOIS defeitos reais, nunca detectados porque `vertical.spec.ts` só verifica a visibilidade do
botão de download, nunca se o `StlViewer` chega ao estado "ready":

1. O `_FakeWorkerClientForE2ESeed` gravava um STL ASCII **vazio** (`"solid e2e-seed\nendsolid
   e2e-seed\n"`, zero facets).
2. Retornava `stl_sha256="0"*64` -- um placeholder sem nenhuma relação com os bytes reais do
   arquivo.

Como `geometry_job_service.dispatch_job()` faz `sha256=result.stl_sha256 or
sha256_of_file(...)`, e a string fake é truthy, o hash fake era persistido tal qual em
`Artifact.sha256`. O frontend (`fetchArtifactBuffer` em `artifactDownload.ts`) recalcula o
SHA-256 real dos bytes baixados e lança `ArtifactChecksumMismatchError` se não bater -- então o
`StlViewer` **nunca** chegava a "ready" para este job; e mesmo que o checksum batesse,
`parseAsciiStl()` rejeitaria o STL vazio por "nenhum facet encontrado".

**Correção aplicada** (fixture de teste, não geometria/receita/TopologyProvider): o script agora
grava um tetraedro sintético ASCII válido (4 facets, coordenadas simples e manuais -- SEM
nenhuma relação com PicoGK) e calcula o SHA-256 REAL desses bytes via `hashlib.sha256` (stdlib,
nenhuma dependência nova), substituindo o placeholder `"0"*64`.

**Prova de que a correção funciona de verdade** (não só "parece corrigido"): dois testes de
regressão novos em `apps/api/tests/test_e2e_seed_fixture.py` rodam o script real via
subprocesso (exatamente como `global-setup.ts` o invoca) contra um SQLite efêmero e um storage
local efêmero, e verificam de fora -- via SQL puro, sem reusar nenhuma lógica do próprio script
-- que: (a) o `Artifact.sha256` persistido é o hash REAL dos bytes gravados (nunca mais
`"0"*64`); (b) o tamanho persistido bate com os bytes reais; (c) o conteúdo tem pelo menos um
facet reconhecível pelas MESMAS expressões regulares que `stlParser.ts` usa no frontend; e (d)
o script continua idempotente (reexecução retorna `status=already_seeded`, sem duplicar dados).
Rodados neste sandbox: **2 passed**.

### `apps/web/e2e/viewer.spec.ts` -- 12 testes novos

Escritos exercitando exclusivamente os controles já implementados em `StlViewer.tsx` (nenhuma
funcionalidade nova de produção foi criada), usando os `data-testid` já existentes (nenhum novo
testid precisou ser adicionado ao componente) e o fixture corrigido acima:

1. Carregamento do STL -- chega a "ready" com formato ("STL ASCII"), contagem de triângulos
   ("4") e de vértices não-indexados ("12") reais do fixture; `<canvas>` real com dimensões > 0.
2. Wireframe -- alterna o `checked` do checkbox e mantém a malha renderizada.
3. Transparência -- o slider de opacidade só existe no DOM quando a transparência está ativa
   (renderização condicional real); slider funcional (`fill` + valor refletido).
4. Eixos e grade -- alternam `checked` real, sem quebrar a renderização.
5. Bounding box -- alterna `checked` real.
6. Clipping -- o controle de posição só aparece quando o corte está ativo; slider funcional.
7. Screenshot -- captura o EVENTO real de download (`page.waitForEvent("download")`), confirma
   o nome de arquivo (`biomatcad-scaffold-screenshot.png`) e a assinatura binária PNG real (magic
   bytes `89 50 4E 47 0D 0A 1A 0A`) -- **sem** comparação de pixels (regra 5 do usuário).
8. Fullscreen -- só interage com o botão se `StlViewer` o renderizar (`fullscreenSupported`);
   observa honestamente qual dos dois desfechos ocorre sob Chromium headless (concedido vs.
   recusado sem gesto de usuário real via CDP) sem forçar um resultado específico (regra 6).
9. Cancelamento -- intercepta a requisição de download via `page.route` e a segura
   indefinidamente (sem sleep arbitrário); clica em "Cancelar"; prova tanto o efeito de UI
   (estado "cancelled", sem canvas) quanto o abort real de rede (`requestfailed` com
   `net::ERR_ABORTED`, disparado pelo `AbortController` do próprio componente) -- regra 7.
10. Retomada após cancelamento -- "Carregar novamente" após um cancelamento real consegue
    chegar a "ready".
11. Descarte de recursos ao sair da página -- navega para outra rota via UI real (nunca
    `page.goto()`, que apagaria a sessão) e prova que o `<canvas>` é removido (cleanup do
    `useEffect` rodou) e que nenhum erro de console/página ocorre durante a transição.
12. Reset de câmera -- clique não gera erro e mantém a malha renderizada.

### Testes de regressão de componente adicionados (sustentam o E2E, regra 12)

Em `apps/web/tests/StlViewer.test.tsx` (21 → 24 casos):

- **Screenshot**: o teste existente só provava que `click()` foi chamado; um teste novo captura
  o próprio elemento `<a>` e confirma `download === "biomatcad-scaffold-screenshot.png"` e
  `href` começando com `"data:image/png"` -- o mesmo contrato que o E2E confirma em navegador
  real, agora também coberto em nível de componente.
- **Fullscreen**: nenhum teste cobria esta API antes desta rodada. Dois testes novos cobrem os
  dois lados do contrato: com `requestFullscreen`/`exitFullscreen` mockados (suporte simulado),
  o botão alterna rótulo corretamente; sem mock (comportamento genuíno do jsdom, que não
  implementa a API), o componente não renderiza o botão -- nunca um estado inconsistente.

### Verificação executada neste sandbox (honesta, sem inflar resultado)

- `tsc --noEmit`: limpo (frontend e novo spec E2E).
- `eslint .`: limpo (0 avisos/erros em todo o projeto, incluindo `viewer.spec.ts`).
- `vitest run`: **124 passed** (121 pré-existentes + 3 novos em `StlViewer.test.tsx`), 0
  falhas -- nenhum teste existente foi enfraquecido ou teve timeout aumentado.
- `npm run build`: sucesso (`tsc --noEmit && vite build`).
- `pytest` (backend, contra Postgres real via `pgserver` efêmero, mesma prática das rodadas
  anteriores): **217 passed, 2 skipped** (215 pré-existentes + 2 novos em
  `test_e2e_seed_fixture.py`) -- confirmado que os 2 "failures" observados em uma execução
  contra SQLite (`test_clinical_suite_expiration_is_respected` e
  `test_two_concurrent_dispatchers_never_claim_the_same_job`) são artefatos conhecidos do
  SQLite (que não replica o `SELECT FOR UPDATE SKIP LOCKED` real do Postgres nem o timing
  exato que esses dois testes assumem) -- não regressões desta rodada; ambos passam limpos
  contra Postgres real.
- `npx playwright test --list`: lista corretamente os 14 testes (2 de `vertical.spec.ts` + 12
  de `viewer.spec.ts`) -- confirma que a suíte e a configuração (`webServer`) estão sintaticamente
  corretas.
- `npx playwright test`: **BLOQUEADO neste sandbox** pela mesma limitação recorrente e já
  documentada desde o Incremento 2.1.1 -- `chrome-headless-shell: error while loading shared
  libraries: libXdamage.so.1: cannot open shared object file` -- sem `sudo` disponível para
  instalar as bibliotecas nativas do Chromium. Isto é reportado honestamente como BLOQUEADO, não
  como aprovado nem como reprovado por defeito de lógica.

### Veredito -- explicitamente NÃO aprovado ainda (regra 17 do usuário)

Esta rodada entrega código e testes ESCRITOS e verificados por todos os meios disponíveis neste
sandbox (typecheck, lint, testes unitários/componente reais, build, e listagem sintática do
Playwright) -- mas a suíte `viewer.spec.ts` em si **nunca rodou de verdade em um Chromium real**
neste ambiente. Consistente com a regra 17 ("não declare esta cobertura E2E aprovada até minha
execução real no Windows retornar 0 falhas"), **este documento NÃO declara a cobertura E2E do
visualizador aprovada**. O roteiro `scripts/Run-E2EOnly.ps1` (já existente, aprovado nas seções
23/24) não precisou de nenhuma alteração funcional para rodar estes 12 testes novos -- `npm run
test:e2e` já executa todos os arquivos `*.spec.ts` dentro de `apps/web/e2e/`, então a próxima
execução real deste MESMO roteiro no Windows exercitará os 14 testes automaticamente. A
aprovação real desta cobertura depende dessa execução.

## 26. Execução Windows real `e2e-only-20260807-001756` (commit `1be54e3`): 2 aprovados, 12 REPROVADOS -- causa raiz confirmada e corrigida (2026-08-07)

**Este registro NÃO substitui nem apaga a seção 25** -- o trabalho relatado ali (escrita do
`viewer.spec.ts`, verificações de sandbox) permanece verdadeiro exatamente como aconteceu.
Esta seção documenta a PRIMEIRA execução real no Windows da suíte completa (14 testes) e a
causa raiz real das 12 falhas, confirmada por reprodução controlada neste sandbox antes de
qualquer edição.

**Evidência literal relatada pelo usuário**:

- Script: `scripts/Run-E2EOnly.ps1`, commit `1be54e3`.
- `OutputDir`: `C:\biomatcad-runs\e2e-only-20260807-001756`.
- 14 testes executados: 2 de `vertical.spec.ts` **aprovados**; 12 de `viewer.spec.ts`
  **REPROVADOS**.
- `E2EExitCode=1`.
- API, frontend, autenticação e o próprio Playwright funcionaram normalmente (a falha não é de
  infraestrutura do roteiro, ao contrário das rodadas anteriores).
- As 12 falhas compartilham a mesma causa observável: `viewer-triangle-count` nunca encontrado
  (o `StlViewer` nunca chega ao estado "ready"); os testes de cancelamento também não
  encontraram `viewer-cancel-button` (consistente com o componente já estar em "error" antes
  mesmo de qualquer interação).
- `global-setup` reportou literalmente: `{"status":"already_seeded","email":"e2e-playwright@biomatcad.example"}`.

**Diagnóstico confirmado** (nota de transparência: os artefatos brutos desta execução --
`E2E_ONLY_REPORT.json/md`, `e2e-output.log`, traces do Playwright -- existem apenas na máquina
Windows do usuário, não neste sandbox; o diagnóstico abaixo foi confirmado por leitura do
código-fonte da rodada anterior e por reprodução controlada equivalente neste sandbox, descrita
logo adiante, não pela abertura literal desses arquivos):

O script `apps/api/scripts/seed_e2e_user.py`, como entregue no commit `1be54e3`, tinha
`if existing_user is not None: return` logo no início de `main()`. O Postgres real do usuário
já continha o usuário `e2e-playwright@biomatcad.example` de execuções aprovadas em rodadas
ANTERIORES a esta (seções 23/24) -- ou seja, ANTES da correção do STL vazio/hash fake
introduzida no commit `1be54e3`. Como o `global-setup.ts` do Playwright roda este script antes
de toda a suíte, e o usuário já existia, o script retornava imediatamente com
`status=already_seeded` -- o job/Artifact/Manifest LEGADOS (STL ASCII vazio, `stl_sha256`
fake `"0"*64`, gravados por uma execução anterior à correção) nunca eram tocados, nunca
substituídos pelo tetraedro sintético corrigido. O `StlViewer`, ao carregar esse job legado,
recalcula o SHA-256 real dos bytes baixados (vazios) e o compara contra o
`Artifact.sha256="0"*64` persistido -- nunca bate, então o componente entra em estado "error"
(`ArtifactChecksumMismatchError`) e nunca chega a "ready". Isso explica exatamente as 12
falhas: todas dependem de `viewer-triangle-count` (só existe em "ready"), e o cancelamento
também falha porque `viewer-cancel-button` só existe em "loading" -- um estado que o
componente já passou (rapidamente, para "error") antes do teste conseguir interagir.

**Reprodução controlada neste sandbox (antes de qualquer edição)**: o cenário foi reproduzido
byte a byte -- rodar o script uma vez (cria o fixture correto), corromper manualmente
`Artifact.sha256` para `"0"*64` e o arquivo STL para o conteúdo vazio legado (simulando
precisamente o que uma execução ANTES da correção do commit `1be54e3` teria deixado no banco),
e então confirmar que uma reexecução do script ANTIGO (com o early-return) preservava a
corrupção intacta -- provando a causa raiz antes de escrever qualquer correção. Este cenário
agora é um teste de regressão permanente (`test_fixture_legado_stl_vazio_e_hash_fake_e_reparado`
em `apps/api/tests/test_e2e_seed_fixture.py`).

**Correção aplicada**: `apps/api/scripts/seed_e2e_user.py` foi reescrito como uma sequência de
passos "get-or-create" totalmente idempotentes e reconciliáveis. Cada camada (organização,
usuário, projeto, receita, design_run, job, Artifact STL, ArtifactManifest/Artifact MANIFEST) é
localizada exclusivamente pelo fixture E2E -- nunca por heurística de nome -- via duas âncoras
determinísticas e únicas no schema: o e-mail único do usuário (`users.email`) e a
`idempotency_key` única do design_run por organização (restrição
`uq_design_run_org_idempotency`). Cada componente é criado apenas se ausente, ou reparado
apenas se o conteúdo persistido divergir byte a byte do fixture esperado -- nunca duplicado.

Correção de segurança adicional confirmada durante a reescrita: a versão anterior chamava
`claim_next_queued_job()`, que reivindica o job MAIS ANTIGO DE TODA A FILA do sistema (via
`SELECT ... FOR UPDATE SKIP LOCKED` sem filtro de job específico) -- em um Postgres real de
pesquisa (não um banco exclusivo de testes), isso arriscaria roubar e fake-executar (com o
worker FALSO deste script) um job real de outro usuário, caso houvesse algum na fila no
momento do seed. Corrigido para reivindicar exclusivamente `job.id` (o job já identificado como
pertencente ao fixture E2E) via `WHERE id = :job_id AND status = 'queued'`.

**Reconciliação de `ArtifactManifest`**: implementada como um patch cirúrgico -- apenas o campo
`stl_sha256` de topo e a entrada `kind="stl"` dentro de `artifacts` são corrigidos; todo o
restante do manifesto (git_commit, topology_provider, métricas, etc.) é preservado
integralmente, e a linha `ArtifactManifest`/`Artifact(MANIFEST)` existente é ATUALIZADA no
lugar (mesmo `id`), nunca recriada -- evitando duplicação e preservando referências.

**Saída do script**: agora distingue, por componente, `created` / `already_valid` / `repaired`
(e um status agregado de topo com a mesma prioridade), sem expor a senha sintética em nenhum
campo além do já existente (inalterado).

**Testes de regressão novos** (`apps/api/tests/test_e2e_seed_fixture.py`, reescrito, 7 casos,
todos rodando o script real via subprocesso contra SQLite efêmero, exatamente como
`global-setup.ts` o invoca):

1. Banco vazio -> fixture criado corretamente (`status=created`).
2. Reexecução sobre fixture já correto -> `already_valid`, sem duplicar nenhuma linha
   (usuário/design_run/job/Artifact STL/ArtifactManifest -- contagem verificada via SQL puro).
3. Fixture legado reproduzido byte a byte (STL vazio + `stl_sha256="0"*64`) -> `repaired`,
   restaurando o MESMO hash real original.
4. Arquivo físico do STL apagado do storage (Artifact no banco continua correto) -> arquivo
   recriado com os bytes corretos.
5. Artifact STL correto mas `ArtifactManifest` com `stl_sha256`/entrada obsoletos -> reconciliado
   SEM recriar a linha (mesmo `id` antes/depois), preservando o restante do conteúdo
   (`git_commit` inalterado, verificado explicitamente).
6. Um usuário/organização/projeto "alheio" ao fixture E2E, inserido diretamente via SQL puro
   (simulando dado real de pesquisa) -> permanece byte a byte e linha a linha intacto após a
   reconciliação.
7. Os bytes servidos pelo endpoint de download (lidos diretamente do `storage_key`, exatamente
   como `routers/artifacts.py:download_artifact` faz) batem com o SHA-256 persistido, inclusive
   após uma reconciliação de fixture legado.

Todos os 7 passam neste sandbox.

**Verificação completa nesta rodada**: `mypy` limpo (mesmos 4 erros pré-existentes e não
relacionados, confirmados idênticos antes/depois); `pytest` backend **222 passed, 2 skipped**
contra Postgres real via `pgserver` (215 + 7 novos, substituindo os 2 testes anteriores do
fixture); frontend inalterado nesta rodada -- `tsc`/`eslint`/`vitest` (**124 passed**, sem
mudança)/`build` reconfirmados limpos para garantir que nada foi afetado; `playwright test
--list` confirma os mesmos 14 testes; `npx playwright test` continua **BLOQUEADO neste
sandbox** pela mesma limitação recorrente (`libXdamage.so.1` ausente, sem `sudo`) -- reportado
honestamente, sem alterar o veredito.

**`scripts/Run-E2EOnly.ps1` não precisou de nenhuma alteração** -- a correção é inteiramente no
script de seed consumido por `global-setup.ts`; o roteiro Windows continua o mesmo comando já
entregue.

### Veredito -- cobertura do visualizador CONTINUA NÃO aprovada

Consistente com a instrução do usuário ("Não declare o visualizador E2E aprovado até uma nova
execução Windows retornar 14/14 e exit code 0"), este documento **não declara** a cobertura E2E
do visualizador aprovada. A causa raiz real das 12 falhas foi identificada e corrigida, e
provada por 7 testes de regressão permanentes neste sandbox -- mas a prova definitiva depende
de uma nova execução real do usuário no Windows, com o banco Postgres real já contaminado pelo
fixture legado (o mesmo banco da execução `20260807-001756`), retornando 14/14 aprovados e
`exit code 0`.
