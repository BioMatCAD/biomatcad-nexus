<#
.SYNOPSIS
    Inicia o ambiente de PESQUISA do BioMatCAD Nexus (Postgres preflight + migracoes + API +
    dispatcher continuo + frontend), como substituto transparente e auditavel ao launcher
    executavel (deferido -- ver tools/windows-launcher/README.md).

.DESCRIPTION
    AMBIENTE DE PESQUISA APENAS. Nao usar com dados clinicos reais, nao usar em producao, nao
    alega prontidao clinica.

    Ordem de execucao:
      1. Impede uma segunda instancia concorrente (arquivo de trava com PID + porta).
      2. Preflight real do Postgres (apps/api/scripts/gate_preflight_check.py) -- nunca sobe um
         Postgres novo, apenas confirma que o driver DBAPI, a porta e a autenticacao estao OK.
      3. `alembic upgrade head` (idempotente).
      4. Inicia a API (uvicorn) com um API_SECRET_KEY efemero, gerado com
         RandomNumberGenerator (nunca Get-Random), nunca gravado em log nem exibido.
      5. Inicia o dispatcher geometrico em modo continuo (status-file + stop-file).
      6. Inicia o frontend (Vite dev server).
      7. Espera as portas da API e do frontend ficarem disponiveis.
      8. Abre o navegador (a menos que -NoBrowser seja passado).
      9. Grava PIDs/portas/logs em um arquivo de sessao para os scripts Stop/Status usarem.

    Este script NUNCA instala dependencias automaticamente: se o venv da API ou o
    node_modules do frontend nao existirem, ele para e mostra o comando exato para o operador
    rodar manualmente (consentimento explicito).

.PARAMETER ApiPort
    Porta local da API. Default: 8000.

.PARAMETER FrontendPort
    Porta local do frontend (Vite). Default: 5173.

.PARAMETER DatabaseUrl
    URL de conexao Postgres (SQLAlchemy), mesma convencao do Run-FinalGate.ps1.

.PARAMETER NoBrowser
    Nao abre o navegador automaticamente.

.EXAMPLE
    pwsh -File .\scripts\Start-BioMatCAD-Research.ps1

.EXAMPLE
    pwsh -File .\scripts\Start-BioMatCAD-Research.ps1 -NoBrowser -ApiPort 8010
#>
[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$DatabaseUrl = "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
    Write-Warning "Nao foi possivel forcar UTF-8 no console ($_) -- prosseguindo mesmo assim."
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\api"
$webDir = Join-Path $repoRoot "apps\web"
$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$runsDir = "C:\biomatcad-runs\research"
$lockFile = Join-Path $runsDir "session.lock"
$sessionFile = Join-Path $runsDir "session.json"
# Caminho do status file NAO customizado de proposito: usa o mesmo default que
# geometry_dispatcher.py calcula sozinho (<artifact_storage_dir>/_dispatcher/status.json,
# relativo ao working directory da API/dispatcher, ambos $apiDir) -- assim o endpoint de
# observabilidade da API encontra o arquivo sem precisar de configuracao adicional.
$dispatcherStatusFile = Join-Path $apiDir "data\artifacts\_dispatcher\status.json"
$dispatcherStopFile = Join-Path $runsDir "dispatcher-stop.request"
$apiLogFile = Join-Path $runsDir "api.log"
$apiErrLogFile = Join-Path $runsDir "api.err.log"
$dispatcherLogFile = Join-Path $runsDir "dispatcher.log"
$dispatcherErrLogFile = Join-Path $runsDir "dispatcher.err.log"
$frontendLogFile = Join-Path $runsDir "frontend.log"
$frontendErrLogFile = Join-Path $runsDir "frontend.err.log"

New-Item -ItemType Directory -Path $runsDir -Force | Out-Null

Write-Host "== BioMatCAD Nexus -- ambiente de PESQUISA (nao usar dados clinicos reais) ==" -ForegroundColor Cyan
Write-Host "Repositorio: $repoRoot"

# ---- 0. Impede uma segunda instancia concorrente ----
# Checa por PID vivo registrado no arquivo de trava -- nunca usa taskkill amplo, apenas
# recusa iniciar uma segunda sessao enquanto a primeira parecer ativa.
if (Test-Path $lockFile) {
    try {
        $lockData = Get-Content $lockFile -Raw -Encoding utf8 | ConvertFrom-Json
        $existingPid = [int]$lockData.pid
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProcess -and $existingProcess.StartTime -eq [datetime]$lockData.started_at) {
            Write-Host "`n[erro] Ja existe uma sessao de pesquisa ativa (PID $existingPid, iniciada em $($lockData.started_at))." -ForegroundColor Red
            Write-Host "        Rode Stop-BioMatCAD-Research.ps1 primeiro, ou Status-BioMatCAD-Research.ps1 para ver detalhes." -ForegroundColor Red
            exit 1
        }
    }
    catch {
        Write-Warning "Arquivo de trava existente nao pode ser lido/validado ($_) -- tratando como sessao morta e prosseguindo."
    }
}
$selfLock = [ordered]@{ pid = $PID; started_at = (Get-Process -Id $PID).StartTime.ToString("o") }
$selfLock | ConvertTo-Json | Set-Content -Path $lockFile -Encoding utf8

# ---- 1. Verificacao de dependencias (NUNCA instala automaticamente) ----
if (-not (Test-Path $venvPython)) {
    Remove-Item $lockFile -ErrorAction SilentlyContinue
    Write-Host "`n[erro] Nao encontrei $venvPython." -ForegroundColor Red
    Write-Host "        Prepare o ambiente da API primeiro (requer seu consentimento explicito):" -ForegroundColor Red
    Write-Host "            cd `"$apiDir`""
    Write-Host "            python -m venv .venv"
    Write-Host "            .\.venv\Scripts\pip install -e `".[dev]`""
    exit 1
}
$nodeModulesDir = Join-Path $webDir "node_modules"
if (-not (Test-Path $nodeModulesDir)) {
    Remove-Item $lockFile -ErrorAction SilentlyContinue
    Write-Host "`n[erro] Nao encontrei $nodeModulesDir." -ForegroundColor Red
    Write-Host "        Instale as dependencias do frontend primeiro (requer seu consentimento explicito):" -ForegroundColor Red
    Write-Host "            cd `"$webDir`""
    Write-Host "            npm ci"
    exit 1
}

# ---- 2. Preflight real do Postgres (nunca sobe um Postgres novo) ----
Write-Host "`n-- Preflight: driver DBAPI, porta do Postgres e conexao/autenticacao reais --" -ForegroundColor Cyan
$previousEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$preflightOutput = & $venvPython (Join-Path $apiDir "scripts\gate_preflight_check.py") --database-url $DatabaseUrl 2>&1
$preflightExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousEap
Write-Host ($preflightOutput -join "`n")
if ($preflightExitCode -ne 0) {
    Remove-Item $lockFile -ErrorAction SilentlyContinue
    Write-Host "`n== FALHA no preflight do Postgres (exit code $preflightExitCode) ==" -ForegroundColor Red
    exit $preflightExitCode
}
Write-Host "Preflight aprovado." -ForegroundColor Green

$env:DATABASE_URL = $DatabaseUrl
$env:ENVIRONMENT = "test"

# ---- 3. Migracoes (idempotente) ----
Write-Host "`n-- Rodando 'alembic upgrade head' --" -ForegroundColor Cyan
$alembicStdout = Join-Path $runsDir "alembic-stdout.log"
$alembicStderr = Join-Path $runsDir "alembic-stderr.log"
Push-Location $apiDir
try {
    & $venvPython -m alembic upgrade head 1>$alembicStdout 2>$alembicStderr
    $alembicExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
if ($alembicExitCode -ne 0) {
    Remove-Item $lockFile -ErrorAction SilentlyContinue
    Write-Host "`n== FALHA em 'alembic upgrade head' (exit code $alembicExitCode) -- ver $alembicStderr ==" -ForegroundColor Red
    exit 1
}
Write-Host "Migracoes em dia." -ForegroundColor Green

# ---- 4. API com segredo efemero (nunca gravado em log ou exibido) ----
Write-Host "`n-- Iniciando a API (porta $ApiPort) --" -ForegroundColor Cyan
$secretBytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
$env:API_SECRET_KEY = [Convert]::ToBase64String($secretBytes)
try {
    $apiProcess = Start-Process -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "biomatcad_api.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
        -WorkingDirectory $apiDir `
        -PassThru -NoNewWindow `
        -RedirectStandardOutput $apiLogFile `
        -RedirectStandardError $apiErrLogFile
}
finally {
    # O segredo so precisa existir no ambiente herdado no momento de Start-Process -- remove
    # da variavel de ambiente do PROPRIO script logo em seguida (defesa em profundidade;
    # nunca foi escrito em disco nem exibido).
    Remove-Item Env:\API_SECRET_KEY -ErrorAction SilentlyContinue
}
Write-Host "API iniciada -- PID $($apiProcess.Id). Log: $apiLogFile"

# ---- 5. Dispatcher geometrico continuo ----
Write-Host "`n-- Iniciando o dispatcher geometrico (modo continuo) --" -ForegroundColor Cyan
Remove-Item $dispatcherStopFile -ErrorAction SilentlyContinue
$dispatcherProcess = Start-Process -FilePath $venvPython `
    -ArgumentList @(
        "scripts\geometry_dispatcher.py",
        "--stop-file", $dispatcherStopFile
    ) `
    -WorkingDirectory $apiDir `
    -PassThru -NoNewWindow `
    -RedirectStandardOutput $dispatcherLogFile `
    -RedirectStandardError $dispatcherErrLogFile
Write-Host "Dispatcher iniciado -- PID $($dispatcherProcess.Id). Log: $dispatcherLogFile. Status: $dispatcherStatusFile"

# ---- 6. Frontend (Vite dev server) ----
Write-Host "`n-- Iniciando o frontend (porta $FrontendPort) --" -ForegroundColor Cyan
$env:VITE_API_BASE_URL = "http://localhost:$ApiPort"
$frontendProcess = Start-Process -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--port", "$FrontendPort", "--strictPort") `
    -WorkingDirectory $webDir `
    -PassThru -NoNewWindow `
    -RedirectStandardOutput $frontendLogFile `
    -RedirectStandardError $frontendErrLogFile
Write-Host "Frontend iniciado -- PID $($frontendProcess.Id). Log: $frontendLogFile"

# ---- 7. Espera as portas ficarem disponiveis (poll real de socket, nunca sleep fixo) ----
function Wait-Port {
    param([string]$Name, [int]$Port, [int]$TimeoutSeconds = 60)
    Write-Host "Aguardando $Name em 127.0.0.1:$Port ..." -NoNewline
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $test = Test-NetConnection -ComputerName "127.0.0.1" -Port $Port -WarningAction SilentlyContinue
        if ($test.TcpTestSucceeded) {
            Write-Host " disponivel." -ForegroundColor Green
            return $true
        }
        Start-Sleep -Milliseconds 300
    }
    Write-Host " TIMEOUT." -ForegroundColor Red
    return $false
}

$apiReady = Wait-Port -Name "API" -Port $ApiPort
$frontendReady = Wait-Port -Name "frontend" -Port $FrontendPort

# ---- 8. Grava a sessao (PIDs/portas/logs) para Stop/Status usarem ----
$session = [ordered]@{
    started_at             = (Get-Date).ToString("o")
    repo_root              = $repoRoot
    api_port               = $ApiPort
    frontend_port          = $FrontendPort
    api_pid                = $apiProcess.Id
    api_started_at         = $apiProcess.StartTime.ToString("o")
    api_log                = $apiLogFile
    api_err_log            = $apiErrLogFile
    dispatcher_pid         = $dispatcherProcess.Id
    dispatcher_started_at  = $dispatcherProcess.StartTime.ToString("o")
    dispatcher_log         = $dispatcherLogFile
    dispatcher_err_log     = $dispatcherErrLogFile
    dispatcher_status_file = $dispatcherStatusFile
    dispatcher_stop_file   = $dispatcherStopFile
    frontend_pid           = $frontendProcess.Id
    frontend_started_at    = $frontendProcess.StartTime.ToString("o")
    frontend_log           = $frontendLogFile
    frontend_err_log       = $frontendErrLogFile
}
$session | ConvertTo-Json | Set-Content -Path $sessionFile -Encoding utf8

Write-Host "`n== Sessao de pesquisa iniciada =="  -ForegroundColor Cyan
Write-Host ("{0,-12} {1}" -f "API:", "http://localhost:$ApiPort  (PID $($apiProcess.Id))")
Write-Host ("{0,-12} {1}" -f "Frontend:", "http://localhost:$FrontendPort  (PID $($frontendProcess.Id))")
Write-Host ("{0,-12} {1}" -f "Dispatcher:", "PID $($dispatcherProcess.Id)  status: $dispatcherStatusFile")
Write-Host ("{0,-12} {1}" -f "Sessao:", $sessionFile)
Write-Host "`nPara parar: pwsh -File `"$PSScriptRoot\Stop-BioMatCAD-Research.ps1`""
Write-Host "Para status: pwsh -File `"$PSScriptRoot\Status-BioMatCAD-Research.ps1`""
Write-Host "`nAMBIENTE DE PESQUISA -- NAO USAR DADOS CLINICOS REAIS. Nenhuma prontidao clinica e alegada." -ForegroundColor Yellow

if (-not $NoBrowser -and $frontendReady) {
    Start-Process "http://localhost:$FrontendPort/login"
}

if (-not $apiReady -or -not $frontendReady) {
    Write-Host "`n[aviso] Uma ou mais portas nao ficaram disponiveis dentro do timeout -- verifique os logs acima." -ForegroundColor Yellow
    exit 1
}
exit 0
