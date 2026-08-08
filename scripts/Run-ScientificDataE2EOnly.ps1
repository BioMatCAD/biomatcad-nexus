<#
.SYNOPSIS
    Roteiro independente para rodar SOMENTE o E2E da interface cientifica minima
    (apps/web/e2e/scientific-data.spec.ts) -- Incremento 2.3, Rodada 2, Fase R (Adendo de
    Interface Cientifica Minima) -- sem repetir a matriz geometrica completa (worker C#/PicoGK,
    vertical.spec.ts, viewer.spec.ts) e sem NENHUMA chamada real a rede PubChem.

.DESCRIPTION
    Este roteiro e deliberadamente separado de Run-E2EOnly.ps1 (que roda TODOS os specs em
    apps/web/e2e/ via 'npm run test:e2e'): aqui rodamos explicitamente apenas
    'npx playwright test e2e/scientific-data.spec.ts', para nao reexecutar vertical.spec.ts /
    viewer.spec.ts (que dependem do job geometrico pre-semeado e nao tem nenhuma relacao com a
    interface cientifica) a cada verificacao pontual desta rodada.

    O que este roteiro faz, em ordem:
      1. Confirma -RepoPath absoluto e existente (nao clona nem atualiza o repositorio -- e
         responsabilidade de quem chama garantir o commit correto, mesmo padrao de
         Run-E2EOnly.ps1).
      2. Prepara/atualiza o venv da API (pip install -e ".[dev]", idempotente) e roda
         'alembic upgrade head' (idempotente).
      3. Define um segredo JWT SINTETICO (>= 32 bytes, nunca hardcoded/real) e
         ENVIRONMENT=development, e inicia a API real (uvicorn) TRACKED (PID proprio), aguardando
         a porta responder antes de prosseguir.
      4. Define E2E_PYTHON_BIN (obrigatorio -- venv real da API, nunca o Python global do
         sistema) e CI=true (forca o Playwright a sempre iniciar um frontend NOVO e rastreado via
         'webServer' -- ver apps/web/playwright.config.ts -- nunca reaproveitar silenciosamente
         algo ja ouvindo na porta).
      5. Roda 'npx playwright install chromium' + 'npx playwright test e2e/scientific-data.spec.ts
         --project=chromium'. O globalSetup do Playwright (apps/web/e2e/global-setup.ts) semeia
         automaticamente: usuario/job E2E pre-existente (scripts/seed_e2e_user.py, reaproveitado
         por outros specs mas inofensivo aqui), usuarios sinteticos researcher/admin
         (python -m biomatcad_api.seed) e as entidades/observacoes/proveniencia/conflito
         cientificos sinteticos (python -m biomatcad_api.seed_scientific_data) -- os DOIS
         ultimos foram adicionados ao global-setup especificamente para esta Rodada 2 (Fase R).
         NENHUM desses scripts faz qualquer chamada de rede real (sao insercoes diretas via
         SQLAlchemy) -- e o proprio spec nunca inicia um dispatcher de ingestao real, entao
         NENHUMA ScientificIngestionRequest criada durante o teste (dry-run/submissao/
         cancelamento) e efetivamente processada contra o PubChem real: elas permanecem em
         'queued' ate serem canceladas pelo proprio teste, ou sao um dry-run que a API garante
         nunca persistir nenhuma entidade cientifica.
      6. Encerra a API (somente o processo PID iniciado por este script -- o frontend iniciado
         pelo webServer do Playwright e encerrado pelo proprio Playwright) e escreve um relatorio
         consolidado (JSON + Markdown) desta execucao.

    NUNCA chama a rede PubChem real. NUNCA repete vertical.spec.ts/viewer.spec.ts nem qualquer
    parte da matriz geometrica (worker C#/PicoGK, golden recipes). NUNCA depende do PicoGK.
    NUNCA usa sleep arbitrario alem de polling de porta/saude com timeout explicito.

.PARAMETER RepoPath
    Caminho ABSOLUTO local do repositorio ja clonado/atualizado no commit correto (apos importar
    o bundle biomatcad-nexus-incremento-2.3-rodada2-pubchem-wip.bundle).

.PARAMETER DatabaseUrl
    URL de conexao Postgres (SQLAlchemy) -- um Postgres real e local, dedicado ou compartilhado;
    os seeds usados aqui sao idempotentes e nunca tocam dados de outro usuario/organizacao real.

.PARAMETER ApiPort
    Porta local da API. Default: 8000.

.PARAMETER OutputDir
    Pasta onde salvar toda a evidencia desta execucao (logs, relatorio consolidado). Default:
    C:\biomatcad-runs\scientific-data-e2e-only-<timestamp>.

.EXAMPLE
    pwsh .\scripts\Run-ScientificDataE2EOnly.ps1 `
        -RepoPath C:\Users\adler\Documents\GitHub\biomatcad-nexus-incremento-2.3 `
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

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "Este roteiro requer PowerShell 7+ (pwsh). Versao atual: $($PSVersionTable.PSVersion) -- instale o PowerShell 7 e rode via 'pwsh', nunca 'powershell.exe' (5.1)."
}

if (-not (Test-Path $RepoPath)) {
    throw "RepoPath nao encontrado: $RepoPath -- este roteiro NAO clona/atualiza o repositorio; aponte para um checkout ja existente e no commit correto (apos importar o bundle da Rodada 2)."
}
if (-not [System.IO.Path]::IsPathRooted($RepoPath)) {
    throw "RepoPath deve ser um caminho ABSOLUTO (recebido: '$RepoPath')."
}
if ($OutputDir -and -not [System.IO.Path]::IsPathRooted($OutputDir)) {
    throw "OutputDir deve ser um caminho ABSOLUTO (recebido: '$OutputDir')."
}

$scientificSpecPath = Join-Path $RepoPath "apps\web\e2e\scientific-data.spec.ts"
if (-not (Test-Path $scientificSpecPath)) {
    throw "apps\web\e2e\scientific-data.spec.ts nao encontrado em $RepoPath -- confirme que o bundle importado e da Rodada 2 pos Fase R (Adendo de Interface Cientifica Minima)."
}

if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = "C:\biomatcad-runs\scientific-data-e2e-only-$timestamp"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$consolidated = [ordered]@{
    roteiro    = "Run-ScientificDataE2EOnly.ps1"
    proposito  = "Rodar SOMENTE apps/web/e2e/scientific-data.spec.ts (interface cientifica minima), sem repetir vertical.spec.ts/viewer.spec.ts nem a matriz geometrica, e sem nenhuma chamada real a rede PubChem."
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
    $jsonPath = Join-Path $OutputDir "SCIENTIFIC_DATA_E2E_ONLY_REPORT.json"
    $consolidated | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding utf8

    $md = New-Object System.Collections.Generic.List[string]
    $md.Add("# Relatorio -- E2E exclusivo da interface cientifica (scientific-data.spec.ts)")
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
    $md.Add("- Nao roda vertical.spec.ts nem viewer.spec.ts (use Run-E2EOnly.ps1 para esses).")
    $md.Add("- Nao recompila nem roda testes do worker C#/PicoGK.")
    $md.Add("- Nao roda a suite pytest completa do backend (ver comando dedicado na documentacao).")
    $md.Add("- Nao faz nenhuma chamada real ao PubChem -- toda ingestao exercitada aqui e sintetica/local (queued/cancelled), nunca processada por um dispatcher real dentro deste roteiro.")
    ($md -join "`n") | Set-Content -Path (Join-Path $OutputDir "SCIENTIFIC_DATA_E2E_ONLY_REPORT.md") -Encoding utf8

    Write-Host "`nRelatorio salvo em:`n  $jsonPath`n  $(Join-Path $OutputDir 'SCIENTIFIC_DATA_E2E_ONLY_REPORT.md')" -ForegroundColor Cyan
}

trap {
    Add-Step -Name "erro_nao_tratado" -Ok $false -Detail "Excecao nao tratada: $_"
    Save-ConsolidatedReport
    Write-Host "`n== ROTEIRO INTERROMPIDO POR ERRO NAO TRATADO -- ver $OutputDir\SCIENTIFIC_DATA_E2E_ONLY_REPORT.json ==" -ForegroundColor Red
    exit 1
}

Write-Host "== BioMatCAD Nexus -- E2E exclusivo da interface cientifica minima ==" -ForegroundColor Cyan
Write-Host "RepoPath: $RepoPath"
Write-Host "OutputDir: $OutputDir"

$apiDir = Join-Path $RepoPath "apps\api"
$webDir = Join-Path $RepoPath "apps\web"
$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"

Push-Location $RepoPath
try {
    $headLine = (git log -1 --oneline) -join ""
    Add-Step -Name "head_confirmado" -Ok $true -Detail "HEAD: $headLine (este roteiro nao clona/atualiza o repositorio -- responsabilidade de quem chama garantir o commit correto, apos importar o bundle da Rodada 2)."
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
    Add-Step -Name "alembic_upgrade_head" -Ok ($LASTEXITCODE -eq 0) -Detail "alembic upgrade head -> exit $LASTEXITCODE (idempotente; prepara o schema para os seeds sintetico/cientifico rodados pelo globalSetup do Playwright)."
    if ($LASTEXITCODE -ne 0) {
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: alembic upgrade head falhou ==" -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

# ---- 2. Iniciar a API real (tracked) com segredo sintetico valido (>= 32 bytes) ----
$syntheticApiSecretKey = "synthetic-scientific-e2e-secret-" + [guid]::NewGuid().ToString("N")
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

Add-Step -Name "api_processo_iniciado_rastreado" -Ok $true -Detail "API iniciada via Start-Process, PID $($apiProcess.Id) (rastreado -- este roteiro encerra SOMENTE este processo ao final, nunca um taskkill global)."

try {
    $ready = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $test = Test-NetConnection -ComputerName "127.0.0.1" -Port $ApiPort -WarningAction SilentlyContinue
        if ($test.TcpTestSucceeded) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    Add-Step -Name "api_disponivel" -Ok $ready -Detail "API em 127.0.0.1:${ApiPort} -- pronta: $ready (PID $($apiProcess.Id); espera por polling de porta com timeout de 60s, nunca sleep fixo arbitrario)."
    if (-not $ready) {
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: API nao ficou disponivel -- ver $apiLogFile.err ==" -ForegroundColor Red
        exit 1
    }

    # ---- 3. E2E EXCLUSIVO da interface cientifica (frontend gerenciado pelo Playwright webServer) ----
    Write-Host "`n-- Etapa 3: E2E exclusivo de scientific-data.spec.ts (Playwright + Chromium) --" -ForegroundColor Cyan
    if (-not (Test-Path $venvPython)) {
        Add-Step -Name "e2e_python_bin_venv_encontrado" -Ok $false -Detail "Venv da API nao encontrado em $venvPython -- os seeds do globalSetup (seed_e2e_user.py, biomatcad_api.seed, biomatcad_api.seed_scientific_data) nao podem rodar sem o Python correto (psycopg, sqlalchemy etc.)."
        Save-ConsolidatedReport
        Write-Host "`n== ROTEIRO INTERROMPIDO: venv da API ausente antes do E2E ==" -ForegroundColor Red
        exit 1
    }
    $env:E2E_PYTHON_BIN = $venvPython
    Add-Step -Name "e2e_python_bin_definido" -Ok $true -Detail "E2E_PYTHON_BIN=$venvPython (venv real, nunca o Python global do sistema)."

    # CI=true forca reuseExistingServer=false (ver shouldReuseExistingServer() em
    # playwright.config.ts) -- o Playwright SEMPRE inicia um frontend novo e rastreado, aguarda a
    # URL responder antes de rodar qualquer teste, e encerra apenas o que ele mesmo iniciou.
    $previousCiEnv = $env:CI
    $env:CI = "true"
    Push-Location $webDir
    try {
        npm ci 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "web-npm-ci.log") | Write-Host
        Add-Step -Name "web_npm_ci" -Ok ($LASTEXITCODE -eq 0) -Detail "npm ci -> exit $LASTEXITCODE"

        npx playwright install chromium 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "e2e-install.log") | Write-Host

        # Restrito EXPLICITAMENTE a scientific-data.spec.ts -- nunca 'npm run test:e2e' (que
        # rodaria tambem vertical.spec.ts/viewer.spec.ts, fora do escopo desta verificacao
        # pontual da Fase R).
        npx playwright test e2e/scientific-data.spec.ts --project=chromium 2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "scientific-data-e2e-output.log") | Write-Host
        Add-Step -Name "e2e_scientific_data_playwright" -Ok ($LASTEXITCODE -eq 0) -Detail "npx playwright test e2e/scientific-data.spec.ts --project=chromium -> exit $LASTEXITCODE (log: scientific-data-e2e-output.log; frontend iniciado/encerrado automaticamente pelo Playwright via webServer, com reuseExistingServer=false; NENHUMA chamada real ao PubChem foi feita -- ver docstring deste script)."
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
    Write-Host "`n== E2E DA INTERFACE CIENTIFICA CONCLUIDO: todas as etapas registradas como OK -- revise SCIENTIFIC_DATA_E2E_ONLY_REPORT.md mesmo assim ==" -ForegroundColor Green
}
else {
    Write-Host "`n== E2E DA INTERFACE CIENTIFICA REPROVADO -- ver SCIENTIFIC_DATA_E2E_ONLY_REPORT.md/json para detalhes ==" -ForegroundColor Red
    exit 1
}
