<#
.SYNOPSIS
    Automatiza o gate final real do Incremento 2.1.1 (item 11/12): API -> fila -> dispatcher
    -> worker PicoGK real -> STL -> Artifact -> Manifest -> download -> comparacao SHA-256.

.DESCRIPTION
    Substitui o fluxo manual de dois terminais descrito em
    docs/examples/WINDOWS_EXECUTION_KIT.md (Secao 9) por um unico comando: este script
    inicia a API (uvicorn) em segundo plano, espera a porta 8000 ficar disponivel, roda
    apps/api/scripts/verify_full_pipeline_sha256.py DE VERDADE (nunca com job pre-semeado,
    nunca simulado), e entao encerra APENAS o processo da API que ele mesmo iniciou --
    nunca um taskkill generico.

    Requer: PostgreSQL real já rodando e acessível na DATABASE_URL informada (este script
    NAO sobe um Postgres -- reaproveita o que voce ja configurou nos passos anteriores do
    kit de execucao Windows); .venv da API ja preparado com as dependencias de dev
    instaladas (pip install -e ".[dev]"); worker PicoGK ja compilado (Release, win-x64).

    NAO usa job pre-semeado. NAO simula sucesso. Se o worker falhar, o script termina com
    "GATE REPROVADO" e o motivo real, exit code != 0.

.PARAMETER Recipe
    Golden recipe a submeter. Default: block-gyroid-v1.

.PARAMETER TimeoutSeconds
    Tempo maximo de espera pelo job chegar a um status terminal. Default: 300.

.PARAMETER DatabaseUrl
    URL de conexao Postgres (SQLAlchemy) usada TANTO pela API quanto pelo proprio gate --
    ambos precisam apontar para o MESMO banco. Default: o mesmo usado no restante do kit
    de execucao Windows (docs/examples/WINDOWS_EXECUTION_KIT.md).

.PARAMETER ApiPort
    Porta local da API. Default: 8000.

.EXAMPLE
    pwsh .\scripts\Run-FinalGate.ps1

.EXAMPLE
    pwsh .\scripts\Run-FinalGate.ps1 -Recipe cylinder-gyroid-v1 -TimeoutSeconds 600
#>
[CmdletBinding()]
param(
    [string]$Recipe = "block-gyroid-v1",
    [double]$TimeoutSeconds = 300,
    [string]$DatabaseUrl = "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad",
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\api"
$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$runsDir = "C:\biomatcad-runs"
$logFile = Join-Path $runsDir "gate-final-api-output.log"
$reportSrc = Join-Path $apiDir "GATE_FULL_PIPELINE_REPORT.json"
$reportDst = Join-Path $runsDir "gate-final-report.json"

if (-not (Test-Path $venvPython)) {
    throw "Nao encontrei $venvPython. Prepare o venv da API primeiro (ver docs/examples/WINDOWS_EXECUTION_KIT.md, passo do venv, incluindo 'pip install -e `".[dev]`"' para ter httpx/psycopg2 disponiveis para o gate)."
}

New-Item -ItemType Directory -Path $runsDir -Force | Out-Null

Write-Host "== BioMatCAD Nexus -- gate final real (API -> fila -> worker PicoGK real -> STL -> Artifact -> Manifest -> download) ==" -ForegroundColor Cyan
Write-Host "Repositorio: $repoRoot"
Write-Host "DATABASE_URL: $DatabaseUrl"
Write-Host "Receita: $Recipe   Timeout: ${TimeoutSeconds}s   Porta API: $ApiPort"

$env:DATABASE_URL = $DatabaseUrl
$env:ENVIRONMENT = "test"

Write-Host "`n-- Rodando 'alembic upgrade head' (idempotente, garante schema atualizado) --" -ForegroundColor Cyan
Push-Location $apiDir
try {
    & $venvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head falhou (exit code $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}

Write-Host "`n-- Iniciando a API em segundo plano (porta $ApiPort) --" -ForegroundColor Cyan
$apiProcess = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "biomatcad_api.main:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -WorkingDirectory $apiDir `
    -PassThru `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError "$logFile.err" `
    -NoNewWindow

Write-Host "API iniciada -- PID $($apiProcess.Id). Log: $logFile"

$gateExitCode = 1
try {
    Write-Host "`n-- Aguardando a API ficar disponivel em 127.0.0.1:$ApiPort --" -ForegroundColor Cyan
    $ready = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $test = Test-NetConnection -ComputerName "127.0.0.1" -Port $ApiPort -WarningAction SilentlyContinue
        if ($test.TcpTestSucceeded) {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        throw "A API nao ficou disponivel em 127.0.0.1:$ApiPort dentro de 60s. Veja $logFile / $logFile.err."
    }
    Write-Host "API disponivel." -ForegroundColor Green

    Write-Host "`n-- Rodando o gate real (verify_full_pipeline_sha256.py) -- SEM job pre-semeado, SEM simulacao --" -ForegroundColor Cyan
    Push-Location $apiDir
    try {
        & $venvPython "scripts\verify_full_pipeline_sha256.py" `
            --api-base-url "http://127.0.0.1:$ApiPort" `
            --recipe $Recipe `
            --timeout-seconds $TimeoutSeconds `
            2>&1 | Tee-Object -FilePath (Join-Path $runsDir "gate-final-output.txt")
        $gateExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if (Test-Path $reportSrc) {
        Copy-Item $reportSrc $reportDst -Force
        Write-Host "Relatorio copiado para $reportDst"
    }
}
finally {
    Write-Host "`n-- Encerrando a API (somente o processo PID $($apiProcess.Id) iniciado por este script) --" -ForegroundColor Cyan
    if (-not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
}

Write-Host ""
if ($gateExitCode -eq 0) {
    Write-Host "== GATE APROVADO (exit code 0) ==" -ForegroundColor Green
}
else {
    Write-Host "== GATE REPROVADO (exit code $gateExitCode) -- ver $runsDir\gate-final-output.txt e $reportDst para o motivo real ==" -ForegroundColor Red
}

exit $gateExitCode
