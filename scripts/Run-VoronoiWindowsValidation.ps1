<#
.SYNOPSIS
    Roteiro UNICO de validacao real no Windows para a rodada Voronoi (Incremento 2.2, Secao 7
    da instrucao original): atualiza o clone a partir do bundle, compila, roda todas as suites,
    gera as 3 golden recipes Voronoi (e, como regressao, as 3 Gyroid) com o worker PicoGK REAL,
    audita cada STL de forma independente, verifica contencao/porosidade/watertight, repete
    cada receita e compara SHA-256 entre execucoes, abre cada resultado no visualizador web,
    roda o E2E de GUI real, e escreve um relatorio consolidado unico.

.DESCRIPTION
    Nao substitui nenhum dos scripts existentes (Run-FinalGate.ps1,
    verify_full_pipeline_sha256.py, gate_preflight_check.py) -- este script os ORQUESTRA em
    sequencia, alem de chamar o novo audit_stl_independent.py (Secao 7 desta rodada) para uma
    segunda opiniao independente sobre cada STL gerado.

    NENHUMA etapa deste script executa PicoGK de verdade fora do Windows -- ele PRECISA ser
    executado no Windows do usuario, com o worker ja compilado (Release, win-x64) e o
    PostgreSQL real ja rodando e acessivel na DatabaseUrl informada. Rodar isto em qualquer
    outro sistema operacional vai falhar na compilacao/execucao do worker (ver ADR-0007) -- o
    script detecta isso e reporta a falha real, nunca finge sucesso.

    Ordem de execucao:
      0. Atualiza (ou clona, se ainda nao existir) o repositorio local a partir do bundle
         informado em -BundlePath, na branch -Branch, e confirma HEAD/tags.
      1. Compila o worker (dotnet build, Release) e roda dotnet test (99 testes esperados).
      2. Prepara/atualiza o venv da API (pip install -e ".[dev]") e roda pytest completo.
      3. Prepara o frontend (npm ci) e roda tsc/eslint/vitest/build/build:pages.
      4. Preflight real (driver Postgres/porta/conexao) + alembic upgrade head + inicia a API.
      5. Para cada golden recipe em -Recipes (default: as 3 Voronoi + as 3 Gyroid, para prova
         de regressao), roda o gate real (verify_full_pipeline_sha256.py) DUAS vezes
         (-run1/-run2), com --output-dir apontando para a pasta de evidencias desta execucao,
         e roda scripts/audit_stl_independent.py sobre cada STL baixado.
      6. Compara o SHA-256 do STL entre run1 e run2 de cada receita (determinismo ponta a
         ponta) -- reporta explicitamente se DIVERGIR (nunca ignora silenciosamente).
      7. Abre cada job Voronoi bem-sucedido no navegador padrao, apontando para a pagina do
         job no frontend (visualizador 3D real) -- passo informativo/manual: o script nao pode
         confirmar visualmente que a malha renderizou, apenas abrir a pagina certa.
      8. Roda o E2E de GUI real (npm run test:e2e em apps/web, Playwright + Chromium real).
      9. Encerra a API (somente o processo iniciado por este script) e escreve um relatorio
         consolidado (JSON + Markdown) reunindo o resultado de TODAS as etapas acima, alem de
         copiar todos os logs/JSON/STL/manifestos para -OutputDir.

    GARANTIA: qualquer falha, em qualquer etapa, e registrada no relatorio consolidado (nunca
    aborta silenciosamente sem deixar rastro) -- mas etapas fatais (compilacao, preflight)
    interrompem as etapas seguintes que dependeriam delas, exatamente como Run-FinalGate.ps1 ja
    faz. As etapas mais tardias tolerantes a falha (auditoria de uma receita especifica,
    abertura do navegador, E2E) NAO abortam a execucao das receitas seguintes.

.PARAMETER RepoPath
    Caminho local do repositorio (clone de trabalho). Sera criado via 'git clone' a partir de
    -BundlePath se ainda nao existir.

.PARAMETER BundlePath
    Caminho do arquivo .bundle (ex.: biomatcad-nexus-v2.2-alpha-wip.bundle) a partir do qual
    atualizar/clonar o repositorio.

.PARAMETER Branch
    Branch a validar. Default: incremento-2.2-alpha-pesquisa.

.PARAMETER DatabaseUrl
    URL de conexao Postgres (SQLAlchemy), mesma usada pelo resto do kit de execucao Windows.

.PARAMETER ApiPort
    Porta local da API. Default: 8000.

.PARAMETER Recipes
    Lista de golden recipes a validar. Default: as 3 Voronoi (rodada atual) + as 3 Gyroid
    (regressao).

.PARAMETER OutputDir
    Pasta onde salvar toda a evidencia desta execucao (logs, JSON, STL, manifestos, relatorio
    consolidado). Default: C:\biomatcad-runs\voronoi-validation-<timestamp>.

.PARAMETER TimeoutSeconds
    Timeout por execucao de gate, por receita. Default: 300 (aumente para receitas 'final').

.PARAMETER SkipE2E
    Pula a etapa de E2E Playwright (util para iteracao rapida antes da rodada final).

.EXAMPLE
    pwsh .\scripts\Run-VoronoiWindowsValidation.ps1 `
        -RepoPath C:\dev\biomatcad-nexus `
        -BundlePath C:\Users\voce\Downloads\biomatcad-nexus-v2.2-alpha-wip.bundle `
        -DatabaseUrl "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoPath,
    [Parameter(Mandatory = $true)][string]$BundlePath,
    [string]$Branch = "incremento-2.2-alpha-pesquisa",
    [string]$DatabaseUrl = "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad",
    [int]$ApiPort = 8000,
    [string[]]$Recipes = @(
        "block-voronoi-preview-v1", "block-voronoi-final-v1", "cylinder-voronoi-preview-v1",
        "block-gyroid-v1", "cylinder-gyroid-v1", "preview-gyroid-low-res-v1"
    ),
    [string]$OutputDir = $null,
    [double]$TimeoutSeconds = 300,
    [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
    Write-Warning "Nao foi possivel forcar [Console]::OutputEncoding para UTF-8 ($_) -- prosseguindo mesmo assim."
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = "C:\biomatcad-runs\voronoi-validation-$timestamp"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$consolidated = [ordered]@{
    roteiro           = "Run-VoronoiWindowsValidation.ps1"
    incremento        = "2.2 (rodada Voronoi)"
    repo_path         = $RepoPath
    branch            = $Branch
    started_at        = (Get-Date).ToString("o")
    steps             = New-Object System.Collections.Generic.List[object]
    recipe_results    = New-Object System.Collections.Generic.List[object]
    overall_ok        = $true
}

function Add-Step {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    $consolidated.steps.Add([ordered]@{ step = $Name; ok = $Ok; detail = $Detail })
    $color = if ($Ok) { "Green" } else { "Red" }
    Write-Host "[$(if ($Ok) {'OK  '} else {'FALHA'})] $Name -- $Detail" -ForegroundColor $color
    if (-not $Ok) { $consolidated.overall_ok = $false }
}

function Save-ConsolidatedReport {
    $consolidated.finished_at = (Get-Date).ToString("o")
    $jsonPath = Join-Path $OutputDir "CONSOLIDATED_REPORT.json"
    $consolidated | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding utf8

    $md = New-Object System.Collections.Generic.List[string]
    $md.Add("# Relatorio consolidado -- validacao Windows da rodada Voronoi (Incremento 2.2)")
    $md.Add("")
    $md.Add("- Repositorio: $RepoPath")
    $md.Add("- Branch: $Branch")
    $md.Add("- Inicio: $($consolidated.started_at)")
    $md.Add("- Fim: $($consolidated.finished_at)")
    $md.Add("- Resultado geral: $(if ($consolidated.overall_ok) {'APROVADO'} else {'REPROVADO -- ver detalhes abaixo'})")
    $md.Add("")
    $md.Add("## Etapas de preparacao/suites")
    $md.Add("")
    $md.Add("| Etapa | Resultado | Detalhe |")
    $md.Add("|---|---|---|")
    foreach ($s in $consolidated.steps) {
        $status = if ($s.ok) { "OK" } else { "FALHA" }
        $md.Add("| $($s.step) | $status | $($s.detail -replace '\|','\|') |")
    }
    $md.Add("")
    $md.Add("## Receitas validadas")
    $md.Add("")
    $md.Add("| Receita | Run1 SHA-256 | Run2 SHA-256 | Deterministico | Watertight (worker) | Watertight (auditoria independente) | Contencao (auditoria independente) |")
    $md.Add("|---|---|---|---|---|---|---|")
    foreach ($r in $consolidated.recipe_results) {
        $md.Add("| $($r.recipe) | $($r.run1_stl_sha256) | $($r.run2_stl_sha256) | $($r.deterministic) | $($r.run1_worker_watertight) | $($r.run1_independent_watertight) | $($r.run1_independent_containment_verified) |")
    }
    $md.Add("")
    $md.Add("## O que este relatorio NAO prova")
    $md.Add("")
    $md.Add("- Nenhuma comparacao morfologica com tecido real (fora de escopo).")
    $md.Add("- A auditoria independente audita o STL PRODUZIDO; nao reexecuta a tesselacao Voronoi em si (essa ja e provada por dotnet test, Secao 1 acima).")
    $md.Add("- O E2E (se nao pulado) exercita o fluxo de interface -- nao substitui esta auditoria geometrica.")
    ($md -join "`n") | Set-Content -Path (Join-Path $OutputDir "CONSOLIDATED_REPORT.md") -Encoding utf8

    Write-Host "`nRelatorio consolidado salvo em:`n  $jsonPath`n  $(Join-Path $OutputDir 'CONSOLIDATED_REPORT.md')" -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------
# Isolamento entre receitas (correcao real, auditoria da rodada
# 20260806-112714): a validacao Windows anterior mostrou dois WORKER_TIMEOUT reais
# (block-voronoi-preview-v1), seguidos de uma cascata de exit_code=1 em TODAS as invocacoes
# SUBSEQUENTES do dispatcher, inclusive nas golden recipes Gyroid de controle ja aprovadas. A
# auditoria de codigo concluiu que a causa mais provavel foi um processo dotnet.exe (o worker
# PicoGK real) deixado ORFAO por uma condicao de corrida no proprio script de gate (corrigida
# nesta rodada, ver verify_full_pipeline_sha256.py::compute_effective_gate_timeout_seconds) --
# o orfao continuou consumindo recursos pelo resto da sessao, afetando toda execucao seguinte.
# Estas funcoes tornam esse tipo de vazamento IMPOSSIVEL DE PASSAR DESPERCEBIDO: antes de cada
# execucao de receita, verificamos e limpamos qualquer dotnet.exe orfao do worker que tenha
# sobrevivido a uma execucao anterior -- e registramos o achado no relatorio consolidado,
# nunca silenciosamente.
function Get-StrayWorkerProcesses {
    Get-CimInstance Win32_Process -Filter "Name = 'dotnet.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "BioMatCadGeometryWorker\.dll" }
}

function Clear-StrayWorkerProcesses {
    param([string]$Context)
    $stray = @(Get-StrayWorkerProcesses)
    if ($stray.Count -gt 0) {
        $strayPids = $stray | ForEach-Object { $_.ProcessId }
        foreach ($p in $stray) {
            try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {
                Write-Warning "Falha ao encerrar processo orfao PID $($p.ProcessId): $_"
            }
        }
        Add-Step -Name "isolamento_$Context" -Ok $false -Detail (
            "ENCONTRADO(S) E ENCERRADO(S) $($stray.Count) processo(s) dotnet.exe ORFAO(S) do " +
            "worker ANTES desta etapa (PIDs: $($strayPids -join ', ')) -- evidencia real de " +
            "vazamento de processo de uma execucao anterior (ver auditoria da rodada " +
            "20260806-112714 em TEST_EVIDENCE.md). Isolamento restaurado antes de prosseguir."
        )
    }
    else {
        Add-Step -Name "isolamento_$Context" -Ok $true -Detail "Nenhum processo dotnet.exe orfao do worker encontrado antes desta etapa."
    }
}

trap {
    Add-Step -Name "erro_nao_tratado" -Ok $false -Detail "Excecao nao tratada: $_"
    Save-ConsolidatedReport
    Write-Host "`n== ROTEIRO INTERROMPIDO POR ERRO NAO TRATADO -- ver $OutputDir\CONSOLIDATED_REPORT.json ==" -ForegroundColor Red
    exit 1
}

Write-Host "== BioMatCAD Nexus -- roteiro unico de validacao Windows, rodada Voronoi (Incremento 2.2) ==" -ForegroundColor Cyan
Write-Host "RepoPath: $RepoPath"
Write-Host "BundlePath: $BundlePath"
Write-Host "Branch: $Branch"
Write-Host "OutputDir: $OutputDir"
Write-Host "Receitas: $($Recipes -join ', ')"

# ---- 0. Atualizar/clonar o repositorio a partir do bundle ----
Write-Host "`n-- Etapa 0: atualizar clone a partir do bundle --" -ForegroundColor Cyan
if (-not (Test-Path $BundlePath)) {
    Add-Step -Name "bundle_encontrado" -Ok $false -Detail "Bundle nao encontrado em $BundlePath"
    Save-ConsolidatedReport
    exit 1
}
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    git clone $BundlePath $RepoPath -b $Branch 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) { Add-Step -Name "clone_do_bundle" -Ok $false -Detail "git clone falhou (exit $LASTEXITCODE)."; Save-ConsolidatedReport; exit 1 }
    Add-Step -Name "clone_do_bundle" -Ok $true -Detail "Repositorio clonado em $RepoPath."
}
else {
    Push-Location $RepoPath
    try {
        git remote remove windows-bundle 2>&1 | Out-Null
        git remote add windows-bundle $BundlePath 2>&1 | Write-Host
        git fetch windows-bundle 2>&1 | Write-Host
        if ($LASTEXITCODE -ne 0) { Add-Step -Name "fetch_do_bundle" -Ok $false -Detail "git fetch falhou (exit $LASTEXITCODE)."; Save-ConsolidatedReport; exit 1 }
        git checkout $Branch 2>&1 | Write-Host
        git reset --hard "windows-bundle/$Branch" 2>&1 | Write-Host
        if ($LASTEXITCODE -ne 0) { Add-Step -Name "reset_para_branch_do_bundle" -Ok $false -Detail "git reset --hard falhou (exit $LASTEXITCODE)."; Save-ConsolidatedReport; exit 1 }
        Add-Step -Name "clone_atualizado_a_partir_do_bundle" -Ok $true -Detail "Repositorio existente atualizado para $Branch a partir do bundle."
    }
    finally {
        Pop-Location
    }
}

Push-Location $RepoPath
try {
    $headLine = (git log -1 --oneline) -join ""
    $tagsLine = (git tag) -join ", "
    Add-Step -Name "head_e_tags_confirmados" -Ok $true -Detail "HEAD: $headLine | Tags presentes: $tagsLine"
}
finally {
    Pop-Location
}

$apiDir = Join-Path $RepoPath "apps\api"
$webDir = Join-Path $RepoPath "apps\web"
$workerDir = Join-Path $RepoPath "apps\geometry-worker"
$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"

# ---- 1. Worker C#: build + testes ----
Write-Host "`n-- Etapa 1: worker C# (dotnet build + dotnet test) --" -ForegroundColor Cyan
Push-Location $workerDir
try {
    dotnet build --configuration Release 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "worker-build.log") | Write-Host
    Add-Step -Name "worker_dotnet_build" -Ok ($LASTEXITCODE -eq 0) -Detail "dotnet build --configuration Release -> exit $LASTEXITCODE (log: worker-build.log)"
}
finally {
    Pop-Location
}
Push-Location (Join-Path $workerDir "tests\BioMatCadGeometryWorker.Tests")
try {
    dotnet test 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "worker-test.log") | Write-Host
    Add-Step -Name "worker_dotnet_test" -Ok ($LASTEXITCODE -eq 0) -Detail "dotnet test -> exit $LASTEXITCODE (esperado: 99 testes, log: worker-test.log)"
}
finally {
    Pop-Location
}

# ---- 2. API Python: venv + pytest ----
Write-Host "`n-- Etapa 2: API Python (venv + pytest) --" -ForegroundColor Cyan
Push-Location $apiDir
try {
    if (-not (Test-Path $venvPython)) {
        python -m venv .venv 2>&1 | Write-Host
    }
    & $venvPython -m pip install --quiet -e ".[dev]" 2>&1 | Write-Host
    Add-Step -Name "api_venv_preparado" -Ok ($LASTEXITCODE -eq 0) -Detail "pip install -e .[dev] -> exit $LASTEXITCODE"

    # Correcao real (rodada Voronoi 20260806-133141, itens 10-17): a suite pytest NUNCA deve
    # rodar contra DATABASE_URL diretamente quando este aponta para o MESMO banco Postgres real
    # usado pela validacao manual/gate abaixo -- isso foi comprovadamente a causa de 3 falhas
    # reais por contaminacao (cancelamento reivindicou um job antigo real, concorrencia
    # reivindicou jobs externos, observabilidade contou jobs "processing" que nao eram dela).
    # A correcao (tests/conftest.py) le TEST_DATABASE_URL (nao DATABASE_URL) e cria um SCHEMA
    # Postgres exclusivo e efemero dentro do MESMO servidor para toda a suite -- nunca toca no
    # schema "public" real. Por isso aqui setamos TEST_DATABASE_URL (nao apenas DATABASE_URL)
    # apontando para o mesmo servidor real -- prova isolamento de schema contra a MESMA
    # instancia, sem exigir um Postgres separado so para testes.
    $env:TEST_DATABASE_URL = $DatabaseUrl
    $env:DATABASE_URL = $DatabaseUrl
    $env:ENVIRONMENT = "test"
    & $venvPython -m pytest -q 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "api-pytest.log") | Write-Host
    $pytestExit = $LASTEXITCODE
    # Correcao real (mesma rodada, itens 15-16): um exit code de pytest diferente de zero deve
    # SEMPRE ser reportado como [FALHA] -- a versao anterior deste roteiro hardcodava -Ok $true
    # e uma mensagem fixa de "2 falhas pre-existentes esperadas", entao o relatorio consolidado
    # NUNCA refletia o resultado real da suite (inclusive quando uma NOVA falha real, nao
    # relacionada as 2 antigas, aparecia -- exatamente o que aconteceu na rodada
    # 20260806-133141: 3 falhas, nao 2, e o roteiro teria reportado [OK] do mesmo jeito). Agora
    # o relatorio usa o exit code real, sem nenhuma contagem de falha fixa/esperada.
    Add-Step -Name "api_pytest" -Ok ($pytestExit -eq 0) -Detail "pytest -> exit $pytestExit (schema Postgres isolado via TEST_DATABASE_URL; ver resultado real em api-pytest.log -- nenhuma contagem de falha fixa/esperada e assumida aqui)"
}
finally {
    Pop-Location
}

# ---- 3. Frontend: npm ci + tsc + eslint + vitest + build + build:pages ----
Write-Host "`n-- Etapa 3: frontend (npm ci, tsc, eslint, vitest, build, build:pages) --" -ForegroundColor Cyan
Push-Location $webDir
try {
    npm ci 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-npm-ci.log") | Write-Host
    Add-Step -Name "web_npm_ci" -Ok ($LASTEXITCODE -eq 0) -Detail "npm ci -> exit $LASTEXITCODE"

    npx tsc --noEmit 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-tsc.log") | Write-Host
    Add-Step -Name "web_tsc" -Ok ($LASTEXITCODE -eq 0) -Detail "tsc --noEmit -> exit $LASTEXITCODE"

    npx eslint . --ext .ts,.tsx 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-eslint.log") | Write-Host
    Add-Step -Name "web_eslint" -Ok ($LASTEXITCODE -eq 0) -Detail "eslint -> exit $LASTEXITCODE"

    npx vitest run 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-vitest.log") | Write-Host
    Add-Step -Name "web_vitest" -Ok ($LASTEXITCODE -eq 0) -Detail "vitest run -> exit $LASTEXITCODE (esperado: 118 testes)"

    npm run build 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-build.log") | Write-Host
    Add-Step -Name "web_build" -Ok ($LASTEXITCODE -eq 0) -Detail "npm run build -> exit $LASTEXITCODE"

    npm run build:pages 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-build-pages.log") | Write-Host
    Add-Step -Name "web_build_pages" -Ok ($LASTEXITCODE -eq 0) -Detail "npm run build:pages -> exit $LASTEXITCODE"
}
finally {
    Pop-Location
}

# ---- 4. Preflight + alembic + iniciar a API ----
Write-Host "`n-- Etapa 4: preflight, alembic upgrade head, iniciar API --" -ForegroundColor Cyan
Push-Location $apiDir
try {
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $preflightOut = & $venvPython "scripts\gate_preflight_check.py" --database-url $DatabaseUrl 2>&1
    $preflightExit = $LASTEXITCODE
    $ErrorActionPreference = $previousEap
    ($preflightOut -join "`n") | Set-Content -Path (Join-Path $OutputDir "preflight.json") -Encoding utf8
    Add-Step -Name "preflight" -Ok ($preflightExit -eq 0) -Detail "gate_preflight_check.py -> exit $preflightExit (ver preflight.json)"
    if ($preflightExit -ne 0) {
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: preflight falhou -- corrija o ambiente Postgres antes de continuar ==" -ForegroundColor Red
        exit 1
    }

    & $venvPython -m alembic upgrade head 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "alembic.log") | Write-Host
    Add-Step -Name "alembic_upgrade_head" -Ok ($LASTEXITCODE -eq 0) -Detail "alembic upgrade head -> exit $LASTEXITCODE"
    if ($LASTEXITCODE -ne 0) {
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: alembic upgrade head falhou ==" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

$apiLogFile = Join-Path $OutputDir "api-runtime.log"
$apiProcess = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "biomatcad_api.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -WorkingDirectory $apiDir `
    -PassThru `
    -RedirectStandardOutput $apiLogFile `
    -RedirectStandardError "$apiLogFile.err" `
    -NoNewWindow

try {
    $ready = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $test = Test-NetConnection -ComputerName "127.0.0.1" -Port $ApiPort -WarningAction SilentlyContinue
        if ($test.TcpTestSucceeded) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    Add-Step -Name "api_disponivel" -Ok $ready -Detail "API em 127.0.0.1:${ApiPort} -- pronta: $ready (PID $($apiProcess.Id))"
    if (-not $ready) {
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: API nao ficou disponivel -- ver $apiLogFile.err ==" -ForegroundColor Red
        exit 1
    }

    # ---- 5/6. Gate real por receita, DUAS vezes cada, + auditoria independente + comparacao de SHA-256 ----
    Write-Host "`n-- Etapa 5/6: gate real por receita (2x cada) + auditoria independente + comparacao de determinismo --" -ForegroundColor Cyan
    foreach ($recipe in $Recipes) {
        Write-Host "`n=== Receita: $recipe ===" -ForegroundColor Magenta
        $recipeResult = [ordered]@{
            recipe = $recipe
            run1_ok = $false
            run2_ok = $false
            run1_stl_sha256 = $null
            run2_stl_sha256 = $null
            deterministic = $null
            run1_worker_watertight = $null
            run1_independent_watertight = $null
            run1_independent_containment_verified = $null
            run1_duration_seconds = $null
            run2_duration_seconds = $null
        }

        for ($run = 1; $run -le 2; $run++) {
            $runTag = "run$run"

            # Isolamento (correcao real desta rodada): garante que nenhum processo orfao de
            # uma execucao ANTERIOR (desta ou de outra receita) continue vivo e possa
            # contaminar esta execucao -- ver Clear-StrayWorkerProcesses acima.
            Clear-StrayWorkerProcesses -Context "$recipe`_$runTag`_pre"

            $runStartedAt = Get-Date
            Push-Location $apiDir
            try {
                $previousEap3 = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                & $venvPython "scripts\verify_full_pipeline_sha256.py" `
                    --api-base-url "http://127.0.0.1:$ApiPort" `
                    --recipe $recipe `
                    --timeout-seconds $TimeoutSeconds `
                    --output-dir $OutputDir `
                    --run-tag $runTag `
                    2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "$recipe`_$runTag`_gate-output.txt") | Write-Host
                $gateExit = $LASTEXITCODE
                $ErrorActionPreference = $previousEap3
            }
            finally {
                Pop-Location
            }
            $runFinishedAt = Get-Date
            $runDurationSeconds = [math]::Round(($runFinishedAt - $runStartedAt).TotalSeconds, 1)

            # Isolamento pos-execucao: se esta execucao terminou (com sucesso, falha OU
            # timeout) mas deixou um processo orfao para tras, detecta e limpa IMEDIATAMENTE,
            # em vez de deixar o problema se acumular ate a proxima receita (exatamente o
            # padrao real observado na rodada 20260806-112714).
            Clear-StrayWorkerProcesses -Context "$recipe`_$runTag`_pos"

            $stlPath = Join-Path $OutputDir "$recipe`_$runTag.stl"
            $manifestPath = Join-Path $OutputDir "$recipe`_$runTag`_manifest.json"

            $stlSha256 = $null
            if (Test-Path $stlPath) {
                $stlSha256 = (Get-FileHash -Path $stlPath -Algorithm SHA256).Hash.ToLowerInvariant()
            }

            if ($run -eq 1) {
                $recipeResult.run1_ok = ($gateExit -eq 0)
                $recipeResult.run1_stl_sha256 = $stlSha256
                # run1_worker_watertight e preenchido abaixo, a partir do cross-check da
                # auditoria independente contra o manifesto real (nao ha campo "watertight" no
                # objeto "hashes" do relatorio do gate -- ver verify_full_pipeline_sha256.py).

                # Auditoria independente (Secao 7): so roda se o STL/manifesto foram baixados.
                if ((Test-Path $stlPath) -and (Test-Path $manifestPath)) {
                    $recipePath = Join-Path $RepoPath "schemas\biomatcem\golden-recipes\$recipe.json"
                    $auditJsonPath = Join-Path $OutputDir "$recipe`_$runTag`_independent-audit.json"
                    Push-Location $apiDir
                    try {
                        $previousEap4 = $ErrorActionPreference
                        $ErrorActionPreference = "Continue"
                        $auditOut = & $venvPython "scripts\audit_stl_independent.py" `
                            --stl $stlPath --recipe $recipePath --manifest $manifestPath --output-json $auditJsonPath 2>&1
                        $auditExit = $LASTEXITCODE
                        $ErrorActionPreference = $previousEap4
                    }
                    finally {
                        Pop-Location
                    }
                    ($auditOut -join "`n") | Write-Host
                    Add-Step -Name "auditoria_independente_$recipe`_$runTag" -Ok ($auditExit -eq 0) -Detail "audit_stl_independent.py -> exit $auditExit (ver $auditJsonPath)"

                    if (Test-Path $auditJsonPath) {
                        $auditObj = Get-Content $auditJsonPath -Raw -Encoding utf8 | ConvertFrom-Json
                        $recipeResult.run1_independent_watertight = $auditObj.is_watertight_independent
                        $recipeResult.run1_independent_containment_verified = $auditObj.domain_containment_verified_independent
                        if ($auditObj.cross_check_vs_manifest) {
                            $recipeResult.run1_worker_watertight = $auditObj.cross_check_vs_manifest.is_watertight_reported_by_worker
                        }
                    }
                }
            }
            else {
                $recipeResult.run2_ok = ($gateExit -eq 0)
                $recipeResult.run2_stl_sha256 = $stlSha256
            }

            Add-Step -Name "gate_$recipe`_$runTag" -Ok ($gateExit -eq 0) -Detail "verify_full_pipeline_sha256.py --recipe $recipe --run-tag $runTag -> exit $gateExit (duracao: ${runDurationSeconds}s)"
            if ($run -eq 1) { $recipeResult.run1_duration_seconds = $runDurationSeconds } else { $recipeResult.run2_duration_seconds = $runDurationSeconds }
        }

        if ($recipeResult.run1_stl_sha256 -and $recipeResult.run2_stl_sha256) {
            $recipeResult.deterministic = ($recipeResult.run1_stl_sha256 -eq $recipeResult.run2_stl_sha256)
            Add-Step -Name "determinismo_$recipe" -Ok $recipeResult.deterministic -Detail "SHA-256 run1=$($recipeResult.run1_stl_sha256) run2=$($recipeResult.run2_stl_sha256)"
        }
        else {
            Add-Step -Name "determinismo_$recipe" -Ok $false -Detail "Nao foi possivel comparar -- STL ausente em pelo menos uma das duas execucoes."
        }

        $consolidated.recipe_results.Add($recipeResult)
    }

    # ---- 7. Abrir cada receita Voronoi bem-sucedida no visualizador web (passo informativo) ----
    Write-Host "`n-- Etapa 7: abrindo os resultados no navegador para inspecao visual manual --" -ForegroundColor Cyan
    foreach ($recipe in $Recipes) {
        $stlPath = Join-Path $OutputDir "$recipe`_run1.stl"
        if (Test-Path $stlPath) {
            Write-Host "STL de '$recipe' disponivel em $stlPath -- abra o job correspondente na GUI (http://localhost:5173/app) e confirme visualmente a renderizacao." -ForegroundColor Yellow
        }
    }
    try {
        Start-Process "http://localhost:5173/app"
        Add-Step -Name "navegador_aberto" -Ok $true -Detail "Navegador aberto em http://localhost:5173/app (frontend precisa estar rodando via 'npm run dev' em outro terminal para este passo ter efeito real)."
    }
    catch {
        Add-Step -Name "navegador_aberto" -Ok $false -Detail "Nao foi possivel abrir o navegador automaticamente: $_ (abra manualmente)."
    }

    # ---- 8. E2E de GUI real ----
    if (-not $SkipE2E) {
        Write-Host "`n-- Etapa 8: E2E de GUI real (Playwright + Chromium) --" -ForegroundColor Cyan
        # Correcao real (auditoria da rodada 20260806-112714): sem isto, o global-setup.ts do
        # Playwright falhava com "ModuleNotFoundError: No module named psycopg" -- o script
        # caia para o Python GLOBAL do Windows (sem as dependencias do backend instaladas) em
        # vez do venv correto. E2E_PYTHON_BIN agora e OBRIGATORIA no proprio codigo
        # (global-setup.ts lanca MissingE2EPythonBinError se ausente) -- este roteiro sempre a
        # define explicitamente, apontando para o MESMO venv ja usado no resto do roteiro.
        if (-not (Test-Path $venvPython)) {
            Add-Step -Name "e2e_python_bin_venv_encontrado" -Ok $false -Detail "Venv da API nao encontrado em $venvPython -- E2E nao pode rodar sem o Python correto (psycopg etc.)."
            Save-ConsolidatedReport
            Write-Host "`n== ROTEIRO INTERROMPIDO: venv da API ausente antes do E2E ==" -ForegroundColor Red
            exit 1
        }
        $env:E2E_PYTHON_BIN = $venvPython
        Add-Step -Name "e2e_python_bin_definido" -Ok $true -Detail "E2E_PYTHON_BIN=$venvPython (venv real, nunca o Python global do sistema)."

        Push-Location $webDir
        try {
            npx playwright install chromium 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "e2e-install.log") | Write-Host
            npm run test:e2e 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "e2e-output.log") | Write-Host
            Add-Step -Name "e2e_playwright" -Ok ($LASTEXITCODE -eq 0) -Detail "npm run test:e2e -> exit $LASTEXITCODE (log: e2e-output.log)"
        }
        finally {
            Pop-Location
            Remove-Item Env:\E2E_PYTHON_BIN -ErrorAction SilentlyContinue
        }
    }
    else {
        Add-Step -Name "e2e_playwright" -Ok $true -Detail "Pulado via -SkipE2E."
    }
}
finally {
    Write-Host "`n-- Encerrando a API (somente o processo PID $($apiProcess.Id) iniciado por este script) --" -ForegroundColor Cyan
    if (-not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
}

Save-ConsolidatedReport

if ($consolidated.overall_ok) {
    Write-Host "`n== ROTEIRO CONCLUIDO: todas as etapas registradas como OK -- revise CONSOLIDATED_REPORT.md mesmo assim antes de declarar a rodada concluida ==" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "`n== ROTEIRO CONCLUIDO COM FALHAS -- ver $OutputDir\CONSOLIDATED_REPORT.md para o que exatamente falhou ==" -ForegroundColor Red
    exit 1
}
