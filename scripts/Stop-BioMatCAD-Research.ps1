<#
.SYNOPSIS
    Encerra a sessao de PESQUISA do BioMatCAD Nexus iniciada por Start-BioMatCAD-Research.ps1.

.DESCRIPTION
    Encerra SOMENTE os processos que a propria sessao registrou em
    C:\biomatcad-runs\research\session.json (API, dispatcher, frontend) -- nunca um
    `taskkill` generico por nome ou por porta, e nunca afeta processos de outra sessao ou de
    outro programa.

    Ordem de encerramento (graciosa antes de forcada):
      1. Dispatcher: pede parada graciosa via arquivo sentinela (stop_file), espera o estado
         "stopped" no status file por um tempo limitado, so entao forca (Stop-Process) se
         necessario.
      2. Frontend e API: Stop-Process direto (Vite/uvicorn nao tem um mecanismo de shutdown
         gracioso via arquivo equivalente) -- mas SEMPRE validando, antes de encerrar, que o
         PID registrado ainda corresponde ao mesmo processo que a sessao iniciou (checagem de
         StartTime, para nunca matar um processo diferente que por acaso reuse o mesmo PID).

    Remove o arquivo de trava (session.lock) ao final, permitindo uma nova sessao.

.EXAMPLE
    pwsh -File .\scripts\Stop-BioMatCAD-Research.ps1
#>
[CmdletBinding()]
param(
    [int]$GracefulTimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"

$runsDir = "C:\biomatcad-runs\research"
$sessionFile = Join-Path $runsDir "session.json"
$lockFile = Join-Path $runsDir "session.lock"

if (-not (Test-Path $sessionFile)) {
    Write-Host "Nenhuma sessao de pesquisa registrada em $sessionFile -- nada a encerrar." -ForegroundColor Yellow
    exit 0
}

$session = Get-Content $sessionFile -Raw -Encoding utf8 | ConvertFrom-Json

function Stop-TrackedProcess {
    param([string]$Name, [int]$ProcessId, [string]$ExpectedStartTime)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-Host "$Name (PID $ProcessId): ja nao esta rodando." -ForegroundColor DarkGray
        return
    }
    # Validacao de identidade: so encerra se o horario de inicio bater com o que a sessao
    # registrou -- protege contra o PID ter sido reciclado pelo SO para outro processo
    # totalmente diferente entre o Start e o Stop.
    if ($ExpectedStartTime) {
        $actualStartTime = $proc.StartTime.ToString("o")
        if ($actualStartTime -ne $ExpectedStartTime) {
            Write-Host "$Name (PID $ProcessId): horario de inicio nao confere (esperado $ExpectedStartTime, encontrado $actualStartTime) -- NAO vou encerrar um processo que pode ser outro (PID reciclado pelo SO)." -ForegroundColor Yellow
            return
        }
    }
    Write-Host "Encerrando $Name (PID $ProcessId)..." -NoNewline
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        Write-Host " ok." -ForegroundColor Green
    }
    catch {
        Write-Host " falhou ($_)." -ForegroundColor Red
    }
}

# ---- 1. Dispatcher: pede parada graciosa primeiro ----
if ($session.dispatcher_pid) {
    $dispatcherProc = Get-Process -Id $session.dispatcher_pid -ErrorAction SilentlyContinue
    if ($dispatcherProc -and $dispatcherProc.StartTime.ToString("o") -eq $session.dispatcher_started_at) {
        Write-Host "Pedindo parada graciosa do dispatcher (arquivo sentinela)..." -NoNewline
        New-Item -ItemType File -Path $session.dispatcher_stop_file -Force | Out-Null
        $deadline = (Get-Date).AddSeconds($GracefulTimeoutSeconds)
        $stoppedGracefully = $false
        while ((Get-Date) -lt $deadline) {
            if (Test-Path $session.dispatcher_status_file) {
                try {
                    $status = Get-Content $session.dispatcher_status_file -Raw -Encoding utf8 | ConvertFrom-Json
                    if ($status.state -eq "stopped") {
                        $stoppedGracefully = $true
                        break
                    }
                }
                catch {
                    # status file pode estar sendo escrito neste instante -- tenta de novo no
                    # proximo poll, nao e um erro fatal.
                }
            }
            Start-Sleep -Milliseconds 300
        }
        if ($stoppedGracefully) {
            Write-Host " ok (estado 'stopped' confirmado)." -ForegroundColor Green
        }
        else {
            Write-Host " timeout -- forcando encerramento." -ForegroundColor Yellow
        }
    }
    Stop-TrackedProcess -Name "Dispatcher" -ProcessId $session.dispatcher_pid -ExpectedStartTime $session.dispatcher_started_at
}

# ---- 2. Frontend e API ----
if ($session.frontend_pid) {
    Stop-TrackedProcess -Name "Frontend" -ProcessId $session.frontend_pid -ExpectedStartTime $session.frontend_started_at
}
if ($session.api_pid) {
    Stop-TrackedProcess -Name "API" -ProcessId $session.api_pid -ExpectedStartTime $session.api_started_at
}

Remove-Item $lockFile -ErrorAction SilentlyContinue
Remove-Item $sessionFile -ErrorAction SilentlyContinue

Write-Host "`nSessao de pesquisa encerrada. Logs preservados em $runsDir." -ForegroundColor Cyan
