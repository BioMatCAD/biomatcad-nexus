<#
.SYNOPSIS
    Mostra o status real da sessao de PESQUISA do BioMatCAD Nexus (API, dispatcher, frontend).

.DESCRIPTION
    Le exclusivamente o que Start-BioMatCAD-Research.ps1 registrou em
    C:\biomatcad-runs\research\session.json e o status file do dispatcher -- nunca inventa um
    estado "saudavel": cada linha reportada vem de uma verificacao real (processo vivo? porta
    aceitando conexao? status file atualizado ha pouco tempo?).

    Nao encerra nem inicia nada -- somente leitura.

.EXAMPLE
    pwsh -File .\scripts\Status-BioMatCAD-Research.ps1
#>
[CmdletBinding()]
param(
    [int]$DispatcherStaleAfterSeconds = 30
)

$runsDir = "C:\biomatcad-runs\research"
$sessionFile = Join-Path $runsDir "session.json"

Write-Host "== BioMatCAD Nexus -- status da sessao de pesquisa ==" -ForegroundColor Cyan

if (-not (Test-Path $sessionFile)) {
    Write-Host "Nenhuma sessao registrada em $sessionFile." -ForegroundColor Yellow
    Write-Host "Rode: pwsh -File .\scripts\Start-BioMatCAD-Research.ps1"
    exit 1
}

$session = Get-Content $sessionFile -Raw -Encoding utf8 | ConvertFrom-Json
Write-Host "Sessao iniciada em: $($session.started_at)"
Write-Host "Repositorio: $($session.repo_root)`n"

function Test-TrackedProcess {
    param([int]$ProcessId, [string]$ExpectedStartTime)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    if ($ExpectedStartTime -and $proc.StartTime.ToString("o") -ne $ExpectedStartTime) { return $false }
    return $true
}

function Test-PortOpen {
    param([int]$Port)
    $test = Test-NetConnection -ComputerName "127.0.0.1" -Port $Port -WarningAction SilentlyContinue -InformationLevel Quiet
    return [bool]$test
}

# ---- API ----
$apiProcAlive = Test-TrackedProcess -ProcessId $session.api_pid -ExpectedStartTime $session.api_started_at
$apiPortOpen = Test-PortOpen -Port $session.api_port
$apiState = if ($apiProcAlive -and $apiPortOpen) { "healthy" } elseif ($apiProcAlive -and -not $apiPortOpen) { "degraded" } else { "stopped" }
$apiColor = @{ healthy = "Green"; degraded = "Yellow"; stopped = "Red" }[$apiState]
Write-Host ("API".PadRight(12)) -NoNewline
Write-Host $apiState.ToUpper() -ForegroundColor $apiColor -NoNewline
Write-Host ("  PID {0}  porta {1}  log {2}" -f $session.api_pid, $session.api_port, $session.api_log)

# ---- Frontend ----
$feProcAlive = Test-TrackedProcess -ProcessId $session.frontend_pid -ExpectedStartTime $session.frontend_started_at
$fePortOpen = Test-PortOpen -Port $session.frontend_port
$feState = if ($feProcAlive -and $fePortOpen) { "healthy" } elseif ($feProcAlive -and -not $fePortOpen) { "degraded" } else { "stopped" }
$feColor = @{ healthy = "Green"; degraded = "Yellow"; stopped = "Red" }[$feState]
Write-Host ("Frontend".PadRight(12)) -NoNewline
Write-Host $feState.ToUpper() -ForegroundColor $feColor -NoNewline
Write-Host ("  PID {0}  porta {1}  log {2}" -f $session.frontend_pid, $session.frontend_port, $session.frontend_log)

# ---- Dispatcher (via status file real, nao so "processo vivo") ----
$dispProcAlive = Test-TrackedProcess -ProcessId $session.dispatcher_pid -ExpectedStartTime $session.dispatcher_started_at
$dispState = "unknown"
$dispDetail = ""
if (-not $dispProcAlive) {
    $dispState = "stopped"
}
elseif (Test-Path $session.dispatcher_status_file) {
    try {
        $status = Get-Content $session.dispatcher_status_file -Raw -Encoding utf8 | ConvertFrom-Json
        $lastPoll = [datetime]$status.last_poll_at
        $ageSeconds = ((Get-Date).ToUniversalTime() - $lastPoll.ToUniversalTime()).TotalSeconds
        if ($status.state -eq "stopped") {
            $dispState = "stopped"
        }
        elseif ($ageSeconds -gt $DispatcherStaleAfterSeconds) {
            $dispState = "stale"
            $dispDetail = "  (heartbeat ha ${ageSeconds}s, limite ${DispatcherStaleAfterSeconds}s)"
        }
        else {
            $dispState = "healthy"
            $dispDetail = "  (fase: $($status.phase), jobs processados: $($status.jobs_processed_total))"
        }
    }
    catch {
        $dispState = "unavailable"
        $dispDetail = "  (status file ilegivel: $_)"
    }
}
else {
    $dispState = "unavailable"
    $dispDetail = "  (status file ainda nao existe -- pode estar iniciando)"
}
$dispColor = @{ healthy = "Green"; stale = "Yellow"; unavailable = "Yellow"; stopped = "Red"; unknown = "DarkGray" }[$dispState]
Write-Host ("Dispatcher".PadRight(12)) -NoNewline
Write-Host $dispState.ToUpper() -ForegroundColor $dispColor -NoNewline
Write-Host ("  PID {0}  status {1}{2}" -f $session.dispatcher_pid, $session.dispatcher_status_file, $dispDetail)

Write-Host "`nAMBIENTE DE PESQUISA -- NAO USAR DADOS CLINICOS REAIS. Nenhuma prontidao clinica e alegada." -ForegroundColor Yellow
