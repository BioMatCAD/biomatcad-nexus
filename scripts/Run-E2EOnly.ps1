<#
.SYNOPSIS
    Roteiro para reexecutar SOMENTE o E2E de GUI real (Playwright + Chromium) contra a API +
    frontend, SEM repetir a matriz geometrica completa (worker C#/PicoGK, backend pytest,
    golden recipes) -- item 7 do usuario, rodada Windows 20260806-195638.

.DESCRIPTION
    Motivacao: a execucao real `voronoi-validation-staged-20260806-195638` provou a matriz
    cientifica inteira (worker PicoGK real, 6 golden recipes 2x cada, backend, frontend) --
    SOMENTE o E2E falhou, e por um defeito de INFRAESTRUTURA do proprio roteiro
    (`net::ERR_CONNECTION_REFUSED` porque o frontend nunca era iniciado antes do Playwright),
    nao por nenhuma regressao geometrica/cientifica. Rodar a matriz inteira de novo so para
    validar a correcao do E2E seria um desperdicio de tempo e risco (chance de reintroduzir
    processos/estado inesperado) sem nenhum beneficio adicional -- este roteiro reexecuta
    SOMENTE o que mudou: preparo da API + frontend (via Playwright webServer) + E2E.

    Este roteiro assume que -RepoPath JA aponta para um checkout existente, atualizado e no
    commit correto (o mesmo usado na validacao completa) -- ele NAO clona nem atualiza o
    repositorio a partir de nenhum bundle, e NAO recompila o worker C#, NAO roda pytest
    completo, e NAO roda nenhuma golden recipe. Se voce quiser validar tambem o restante,
    use Run-VoronoiWindowsValidation.ps1 (roteiro completo).

    Ordem de execucao:
      1. Confirma HEAD do repositorio (apenas informativo, nao falha se divergir -- e
         responsabilidade de quem chama garantir que -RepoPath esta no commit certo).
      2. Prepara/atualiza o venv da API (pip install -e ".[dev]", idempotente) e roda
         'alembic upgrade head' (idempotente, seguro reexecutar).
      3. Define um segredo JWT SINTETICO (nunca um segredo real) com >= 32 bytes e
         ENVIRONMENT=development explicitamente (mesma correcao aplicada em
         Run-VoronoiWindowsValidation.ps1 -- nunca depender do bypass de ENVIRONMENT=test) e
         inicia a API real (uvicorn), rastreada (PID proprio), aguardando a porta ficar
         disponivel antes de prosseguir.
      4. Define E2E_PYTHON_BIN (obrigatorio, aponta para o venv real -- nunca o Python global)
         e CI=true (forca o Playwright a sempre iniciar um frontend NOVO e rastreado via
         `webServer`, nunca reaproveitar silenciosamente algo ja ouvindo na porta -- ver
         apps/web/playwright.config.ts).
      5. Roda 'npx playwright install chromium' + 'npm run test:e2e'. O proprio Playwright
         inicia o frontend (npm run dev), aguarda a URL responder via polling HTTP ANTES de
         rodar qualquer teste, encaminha o stdout/stderr do frontend para o log de E2E, e
         encerra SOMENTE o processo que ele mesmo iniciou ao final.
      6. Encerra a API (somente o processo iniciado por este script) e escreve um relatorio
         consolidado (JSON + Markdown) desta execucao E2E-only.

    NUNCA altera geometria, receitas, worker cientifico ou hashes -- este roteiro nao os toca
    de forma alguma.

    Atualizacao (rodada "cobertura E2E do visualizador 3D", 2026-08-06): apps/web/e2e/ agora
    tambem contem viewer.spec.ts (12 testes novos: carregamento do STL, wireframe,
    transparencia, eixos, grade, bounding box, clipping, screenshot, fullscreen, cancelamento
    real via requisicao interceptada, retomada apos cancelamento, e descarte de recursos ao
    sair da pagina -- ver apps/web/e2e/README.md). Este script NAO precisou de nenhuma mudanca
    para cobri-los: 'npm run test:e2e' roda 'playwright test', que por sua vez roda TODOS os
    arquivos '*.spec.ts' dentro de testDir ("./e2e", ver apps/web/playwright.config.ts) --
    logo, a proxima execucao real deste MESMO roteiro no Windows ja exercitara os 14 testes
    (2 de vertical.spec.ts + 12 de viewer.spec.ts) automaticamente, sem repetir a matriz
    geometrica completa (worker C#/PicoGK, golden recipes) em nenhum momento. A cobertura do
    visualizador so pode ser considerada aprovada apos essa reexecucao real retornar 0 falhas
    -- nao antes.

.PARAMETER RepoPath
    Caminho local do repositorio JA clonado/atualizado no commit correto.

.PARAMETER DatabaseUrl
    URL de conexao Postgres (SQLAlchemy) -- mesmo banco real usado pela validacao completa
    (o E2E semeia seu proprio usuario/job deterministicos via global-setup.ts, nao interfere
    com dados de outras receitas).

.PARAMETER ApiPort
    Porta local da API. Default: 8000.

.PARAMETER OutputDir
    Pasta onde salvar toda a evidencia desta execucao (logs, relatorio consolidado). Default:
    C:\biomatcad-runs\e2e-only-<timestamp>.

.EXAMPLE
    pwsh .\scripts\Run-E2EOnly.ps1 `
        -RepoPath C:\Users\adler\Documents\GitHub\biomatcad-nexus-v2.2.1-test `
        -DatabaseUrl "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoPath,
    [string]$DatabaseUrl = "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad",
    [int]$ApiPort = 8000,
    [string]$OutputDir = $null
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

if (-not (Test-Path $RepoPath)) {
    throw "RepoPath nao encontrado: $RepoPath -- este roteiro NAO clona/atualiza o repositorio; aponte para um checkout ja existente e no commit correto."
}
if (-not [System.IO.Path]::IsPathRooted($RepoPath)) {
    throw "RepoPath deve ser um caminho ABSOLUTO (recebido: '$RepoPath')."
}
if ($OutputDir -and -not [System.IO.Path]::IsPathRooted($OutputDir)) {
    throw "OutputDir deve ser um caminho ABSOLUTO (recebido: '$OutputDir')."
}

if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = "C:\biomatcad-runs\e2e-only-$timestamp"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$consolidated = [ordered]@{
    roteiro    = "Run-E2EOnly.ps1"
    proposito  = "Reexecutar SOMENTE o E2E de GUI real, sem repetir a matriz geometrica completa."
    repo_path  = $RepoPath
    started_at = (Get-Date).ToString("o")
    steps      = New-Object System.Collections.Generic.List[object]
    overall_ok = $true
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
    $jsonPath = Join-Path $OutputDir "E2E_ONLY_REPORT.json"
    $consolidated | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding utf8

    $md = New-Object System.Collections.Generic.List[string]
    $md.Add("# Relatorio -- reexecucao SOMENTE do E2E (sem matriz geometrica)")
    $md.Add("")
    $md.Add("- Repositorio: $RepoPath")
    $md.Add("- Inicio: $($consolidated.started_at)")
    $md.Add("- Fim: $($consolidated.finished_at)")
    $md.Add("- Resultado geral: $(if ($consolidated.overall_ok) {'APROVADO'} else {'REPROVADO -- ver detalhes abaixo'})")
    $md.Add("")
    $md.Add("## Etapas")
    $md.Add("")
    $md.Add("| Etapa | Resultado | Detalhe |")
    $md.Add("|---|---|---|")
    foreach ($s in $consolidated.steps) {
        $status = if ($s.ok) { "OK" } else { "FALHA" }
        $md.Add("| $($s.step) | $status | $($s.detail -replace '\|','\|') |")
    }
    $md.Add("")
    $md.Add("## O que este relatorio explicitamente NAO cobre")
    $md.Add("")
    $md.Add("- Nao recompila nem roda testes do worker C#/PicoGK.")
    $md.Add("- Nao roda a suite pytest completa do backend.")
    $md.Add("- Nao gera nem audita nenhuma golden recipe (Voronoi/Gyroid).")
    $md.Add("- Para esses itens, use Run-VoronoiWindowsValidation.ps1 (roteiro completo).")
    ($md -join "`n") | Set-Content -Path (Join-Path $OutputDir "E2E_ONLY_REPORT.md") -Encoding utf8

    Write-Host "`nRelatorio salvo em:`n  $jsonPath`n  $(Join-Path $OutputDir 'E2E_ONLY_REPORT.md')" -ForegroundColor Cyan
}

trap {
    Add-Step -Name "erro_nao_tratado" -Ok $false -Detail "Excecao nao tratada: $_"
    Save-ConsolidatedReport
    Write-Host "`n== ROTEIRO INTERROMPIDO POR ERRO NAO TRATADO -- ver $OutputDir\E2E_ONLY_REPORT.json ==" -ForegroundColor Red
    exit 1
}

Write-Host "== BioMatCAD Nexus -- reexecucao SOMENTE do E2E (sem matriz geometrica) ==" -ForegroundColor Cyan
Write-Host "RepoPath: $RepoPath"
Write-Host "OutputDir: $OutputDir"

$apiDir = Join-Path $RepoPath "apps\api"
$webDir = Join-Path $RepoPath "apps\web"
$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"

Push-Location $RepoPath
try {
    $headLine = (git log -1 --oneline) -join ""
    Add-Step -Name "head_confirmado" -Ok $true -Detail "HEAD: $headLine (este roteiro nao clona/atualiza o repositorio -- responsabilidade de quem chama garantir o commit correto)."
}
finally {
    Pop-Location
}

# ---- 1. Venv da API + alembic upgrade head (idempotente) ----
Write-Host "`n-- Etapa 1: preparar venv da API + alembic upgrade head --" -ForegroundColor Cyan
Push-Location $apiDir
try {
    if (-not (Test-Path $venvPython)) {
        python -m venv .venv 2>&1 | Write-Host
    }
    & $venvPython -m pip install --quiet -e ".[dev]" 2>&1 | Write-Host
    Add-Step -Name "api_venv_preparado" -Ok ($LASTEXITCODE -eq 0) -Detail "pip install -e .[dev] -> exit $LASTEXITCODE"

    $env:DATABASE_URL = $DatabaseUrl
    & $venvPython -m alembic upgrade head 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "alembic.log") | Write-Host
    Add-Step -Name "alembic_upgrade_head" -Ok ($LASTEXITCODE -eq 0) -Detail "alembic upgrade head -> exit $LASTEXITCODE (idempotente)"
    if ($LASTEXITCODE -ne 0) {
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: alembic upgrade head falhou ==" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

# ---- 2. Iniciar a API real com segredo sintetico valido (>= 32 bytes) ----
# Mesma correcao aplicada em Run-VoronoiWindowsValidation.ps1 (rodada 20260806-195638, item 8
# do usuario): nunca depender do bypass de ENVIRONMENT=test para o servidor real, e nunca
# deixar o app subir com o valor padrao inseguro de 31 caracteres.
$syntheticApiSecretKey = "synthetic-e2e-validation-secret-" + [guid]::NewGuid().ToString("N")
if ($syntheticApiSecretKey.Length -lt 32) {
    throw "Segredo sintetico gerado tem menos de 32 caracteres (bug no proprio roteiro) -- length=$($syntheticApiSecretKey.Length)"
}
$env:API_SECRET_KEY = $syntheticApiSecretKey
$env:ENVIRONMENT = "development"
Add-Step -Name "api_secret_key_sintetico_valido" -Ok $true -Detail "API_SECRET_KEY sintetico definido com $($syntheticApiSecretKey.Length) caracteres (>= 32 exigidos); ENVIRONMENT=development."

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

    # ---- 3. E2E de GUI real (frontend gerenciado automaticamente pelo Playwright webServer) ----
    Write-Host "`n-- Etapa 3: E2E de GUI real (Playwright + Chromium) --" -ForegroundColor Cyan
    if (-not (Test-Path $venvPython)) {
        Add-Step -Name "e2e_python_bin_venv_encontrado" -Ok $false -Detail "Venv da API nao encontrado em $venvPython -- E2E nao pode rodar sem o Python correto (psycopg etc.)."
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: venv da API ausente antes do E2E ==" -ForegroundColor Red
        exit 1
    }
    $env:E2E_PYTHON_BIN = $venvPython
    Add-Step -Name "e2e_python_bin_definido" -Ok $true -Detail "E2E_PYTHON_BIN=$venvPython (venv real, nunca o Python global do sistema)."

    # CI=true forca reuseExistingServer=false (ver shouldReuseExistingServer() em
    # playwright.config.ts) -- o Playwright SEMPRE inicia um frontend novo e rastreado, aguarda
    # a URL responder antes de rodar qualquer teste, e encerra apenas o que ele mesmo iniciou.
    $previousCiEnv = $env:CI
    $env:CI = "true"
    Push-Location $webDir
    try {
        npm ci 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-npm-ci.log") | Write-Host
        Add-Step -Name "web_npm_ci" -Ok ($LASTEXITCODE -eq 0) -Detail "npm ci -> exit $LASTEXITCODE"

        npx playwright install chromium 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "e2e-install.log") | Write-Host
        npm run test:e2e 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "e2e-output.log") | Write-Host
        Add-Step -Name "e2e_playwright" -Ok ($LASTEXITCODE -eq 0) -Detail "npm run test:e2e -> exit $LASTEXITCODE (log: e2e-output.log; frontend iniciado/encerrado automaticamente pelo Playwright via webServer, com reuseExistingServer=false)."
    }
    finally {
        Pop-Location
        Remove-Item Env:\E2E_PYTHON_BIN -ErrorAction SilentlyContinue
        if ($null -eq $previousCiEnv) { Remove-Item Env:\CI -ErrorAction SilentlyContinue } else { $env:CI = $previousCiEnv }
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
    Write-Host "`n== E2E CONCLUIDO: todas as etapas registradas como OK -- revise E2E_ONLY_REPORT.md mesmo assim ==" -ForegroundColor Green
}
else {
    Write-Host "`n== E2E REPROVADO -- ver E2E_ONLY_REPORT.md/json para detalhes ==" -ForegroundColor Red
    exit 1
}
