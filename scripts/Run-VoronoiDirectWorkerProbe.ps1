<#
.SYNOPSIS
    FASE A (rodada de prova direta, pos-commit d13c691): invoca o geometry-worker REAL
    DIRETAMENTE via CLI (dotnet BioMatCadGeometryWorker.dll job.json), SEM API e SEM
    dispatcher, para observar com precisao o comportamento do processo para
    block-voronoi-preview-v1 -- especificamente se ele encerra sozinho depois de produzir um
    resultado (STL + JSON) completo, ou se permanece vivo indefinidamente (o proprio sintoma
    que o WORKER_TIMEOUT externo mascarava nas rodadas anteriores).

.DESCRIPTION
    Este roteiro e deliberadamente MINIMO: nao depende de Postgres, API, dispatcher nem do
    mecanismo de timeout externo (worker_client.py) -- apenas do worker compilado e de um
    job.json construido a partir da golden recipe real e inalterada (mesma canonicalizacao que
    a API de producao usa, via build_worker_job_json.py -- nunca uma receita sintetica
    diferente, nunca um timeout/parametro alterado).

    O que este roteiro mede e registra, por execucao:
      - t_process_start: instante em que o processo dotnet foi iniciado.
      - t_library_go_returned: instante em que o worker emite o marcador de diagnostico
        "[DIAG_MARKER] library_go_returned_at_utc=..." em stderr (adicionado em Program.cs
        nesta rodada, imediatamente apos topologyProvider.BuildAndExport(...) retornar --
        ver WORKER_STATUS.md secao 13). Isolа o tempo gasto DENTRO de Library.Go/PicoGK do
        tempo gasto depois (metricas, validacao do STL, hash, serializacao do JSON final).
      - t_json_final_seen: instante em que a ULTIMA linha de stdout se torna um JSON valido
        contendo a chave "stl_path" (o resultado de sucesso completo, ver Program.cs).
      - t_result_complete: instante em que TANTO o JSON final quanto o arquivo scaffold.stl
        (tamanho > 0) existem simultaneamente.
      - stl_reopen_readable_after_result_complete: tenta reabrir o STL para LEITURA
        compartilhada assim que o resultado fica completo -- prova que o arquivo esta
        realmente fechado/gravavel-lido, nao apenas "existe" com um handle de escrita preso.
      - still_alive_after_extra_wait: apos t_result_complete, aguarda mais -ExtraWaitSeconds
        (default 15s, callable via parametro) e registra se o PROCESSO SO ainda esta vivo.
      - Se ainda estiver vivo apos essa espera extra: tenta uma amostra de diagnostico de
        threads gerenciadas via Get-Process (melhor esforco -- nao requer dotnet-dump/trace
        instalados; se disponiveis no PATH, tambem tenta capturar um dump leve, sem falhar o
        roteiro se nao estiverem), e SO ENTAO encerra a ARVORE DE PROCESSOS ESPECIFICA
        iniciada por ESTE roteiro (nunca um taskkill global, nunca processos nao rastreados).

    NUNCA altera a golden recipe, o timeout, ou qualquer parametro cientifico -- e um roteiro
    de OBSERVACAO, nao de correcao. Nunca apaga scaffold.stl/job.json apos um resultado
    completo (ao contrario do fluxo via API, que sempre limpa output_dir em qualquer falha --
    aqui, como nao ha timeout externo/dispatcher, nada e limpo automaticamente).

.PARAMETER RepoPath
    Caminho do repositorio local (ja clonado/atualizado a partir do bundle).

.PARAMETER Recipe
    Nome da golden recipe (sem .json). Default: block-voronoi-preview-v1.

.PARAMETER OutputDir
    Diretorio onde este roteiro grava seus proprios artefatos/evidencias (distinto do
    output_dir do JOB, que fica em uma subpasta deste).

.PARAMETER ExtraWaitSeconds
    Segundos adicionais a aguardar APOS o resultado (JSON+STL) ficar completo, antes de
    decidir se o processo "permanece vivo indevidamente". Default: 15 (conforme pedido).

.PARAMETER MaxTotalWaitSeconds
    Teto de seguranca absoluto para todo o roteiro, independente de resultado -- NAO e o
    "timeout" que este roteiro esta investigando (esse mecanismo nem existe aqui), apenas uma
    rede de seguranca para o proprio roteiro nao rodar para sempre se algo inesperado
    acontecer. Default: 300s (bem acima dos ~60-70s historicos do WORKER_TIMEOUT externo).

.PARAMETER DotnetBin
    Caminho do executavel dotnet. Default: "dotnet" (resolvido via PATH).

.PARAMETER PythonBin
    Caminho do Python do venv da API (para build_worker_job_json.py). Default:
    <RepoPath>/apps/api/.venv/Scripts/python.exe.

.EXAMPLE
    .\Run-VoronoiDirectWorkerProbe.ps1 -RepoPath C:\Users\adler\Documents\GitHub\biomatcad-nexus-v2.2.1-test -OutputDir C:\biomatcad-runs\voronoi-direct-probe-20260806
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,

    [string]$Recipe = "block-voronoi-preview-v1",

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [double]$ExtraWaitSeconds = 15,

    [double]$MaxTotalWaitSeconds = 300,

    [string]$DotnetBin = "dotnet",

    [string]$PythonBin = $null
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Item #168 (rodada 3): o usuario relatou uma execucao real onde t_library_go_returned ficou
# null porque o worker.dll efetivamente executado NAO continha a instrumentacao [DIAG_MARKER]
# adicionada em Program.cs no commit 7a44da4 (stderr veio vazio) -- ou seja, uma DLL nao
# recompilada apos esse commit foi usada. Alem disso, um OutputDir relativo pode resolver para
# locais diferentes dependendo do diretorio de trabalho de onde o PowerShell foi invocado,
# tornando dificil localizar/auditar evidencias depois. Para eliminar ambas as causas de
# confusao nesta rodada, exigimos explicitamente caminhos ABSOLUTOS para RepoPath e OutputDir,
# e SEMPRE reconstruimos o worker em Release (nunca reutilizamos silenciosamente uma DLL
# encontrada em disco) antes de localiza-lo.
if (-not [System.IO.Path]::IsPathRooted($RepoPath)) {
    throw "RepoPath deve ser um caminho ABSOLUTO (recebido: '$RepoPath') -- caminhos relativos podem resolver de forma ambigua dependendo do diretorio de trabalho atual."
}
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    throw "OutputDir deve ser um caminho ABSOLUTO (recebido: '$OutputDir') -- caminhos relativos tornam as evidencias dificeis de auditar/localizar depois. Use, por exemplo, C:\biomatcad-runs\voronoi-direct-probe-<timestamp>."
}
if (-not (Test-Path $RepoPath)) {
    throw "RepoPath nao encontrado: $RepoPath"
}
if (-not $PythonBin) {
    $PythonBin = Join-Path $RepoPath "apps\api\.venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonBin)) {
    throw "PythonBin nao encontrado: $PythonBin -- rode 'python -m venv .venv; .venv\Scripts\pip install -e .[dev]' em apps/api antes."
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$jobId = [guid]::NewGuid().ToString()
$jobOutputDir = Join-Path $OutputDir "job-$jobId"
New-Item -ItemType Directory -Path $jobOutputDir -Force | Out-Null

$report = [ordered]@{
    schema_version         = "voronoi-direct-worker-probe-v1"
    recipe                 = $Recipe
    repo_path              = $RepoPath
    job_id                 = $jobId
    job_output_dir         = $jobOutputDir
    extra_wait_seconds     = $ExtraWaitSeconds
    max_total_wait_seconds = $MaxTotalWaitSeconds
    started_at             = (Get-Date).ToString("o")
}

function Write-ReportAndExit {
    param([int]$ExitCode)
    $report.finished_at = (Get-Date).ToString("o")
    $reportPath = Join-Path $OutputDir "direct-worker-probe-report.json"
    $report | ConvertTo-Json -Depth 12 | Set-Content -Path $reportPath -Encoding utf8
    Write-Host ""
    Write-Host "Relatorio estruturado gravado em: $reportPath" -ForegroundColor Cyan
    exit $ExitCode
}

# ---- 0. Reconstroi o worker em Release EXPLICITAMENTE (item #168) e so entao o localiza ----
# Nunca reutiliza silenciosamente uma DLL ja existente em disco: uma DLL nao recompilada apos
# uma mudanca de codigo (por exemplo, a instrumentacao [DIAG_MARKER] adicionada em Program.cs
# no commit 7a44da4) produziria resultados enganosos (como t_library_go_returned=null por
# ausencia real do marcador no binario executado, e nao por qualquer comportamento do worker).
$workerProjDir = Join-Path $RepoPath "apps\geometry-worker"
$currentHeadShort = $null
try {
    Push-Location $RepoPath
    $currentHeadShort = (git rev-parse --short HEAD 2>$null)
}
finally {
    Pop-Location
}
$report.repo_head_short = $currentHeadShort
Write-Host "[INFO] Reconstruindo worker em Release (HEAD=$currentHeadShort) antes de localizar a DLL..." -ForegroundColor Cyan
Push-Location $workerProjDir
try {
    $buildOutput = & $DotnetBin build --configuration Release 2>&1
    $buildExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
$report.worker_build_exit_code = $buildExit
if ($buildExit -ne 0) {
    Write-Host "[FALHA] 'dotnet build --configuration Release' falhou (exit $buildExit):`n$buildOutput" -ForegroundColor Red
    $report.fatal_error = "WORKER_BUILD_FAILED"
    $report.worker_build_output = ($buildOutput -join "`n")
    Write-ReportAndExit -ExitCode 1
}
Write-Host "[OK] Build Release concluido com sucesso." -ForegroundColor Green

$workerBinDir = Join-Path $RepoPath "apps\geometry-worker\bin"
$dllCandidates = @(Get-ChildItem -Path $workerBinDir -Filter "BioMatCadGeometryWorker.dll" -Recurse -ErrorAction SilentlyContinue)
if ($dllCandidates.Count -eq 0) {
    Write-Host "[FALHA] worker nao encontrado apos build bem-sucedido -- verifique o caminho de saida do projeto." -ForegroundColor Red
    $report.fatal_error = "WORKER_BINARY_NOT_FOUND_AFTER_BUILD"
    Write-ReportAndExit -ExitCode 1
}
$dllPath = ($dllCandidates | Where-Object { $_.FullName -match "Release" } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).FullName
if (-not $dllPath) {
    Write-Host "[FALHA] build reportou sucesso mas nenhuma DLL Release foi encontrada." -ForegroundColor Red
    $report.fatal_error = "WORKER_BINARY_NOT_FOUND_AFTER_BUILD"
    Write-ReportAndExit -ExitCode 1
}
$dllLastWriteUtc = (Get-Item $dllPath).LastWriteTimeUtc
$secondsSinceBuild = ((Get-Date).ToUniversalTime() - $dllLastWriteUtc).TotalSeconds
$report.dll_path = $dllPath
$report.dll_last_write_time_utc = $dllLastWriteUtc.ToString("o")
$report.dll_seconds_since_build_at_probe_start = [math]::Round($secondsSinceBuild, 1)
Write-Host "[INFO] Worker DLL (recem-compilada ha $([math]::Round($secondsSinceBuild,1))s): $dllPath" -ForegroundColor Cyan

# ---- 1. Constroi job.json a partir da golden recipe real (canonicalizacao real, nunca alterada) ----
Write-Host "[INFO] Construindo job.json real para '$Recipe' (job_id=$jobId)..." -ForegroundColor Cyan
$buildJobScript = Join-Path $RepoPath "apps\api\scripts\build_worker_job_json.py"
$buildJobOutRaw = & $PythonBin $buildJobScript --recipe $Recipe --job-id $jobId --output-dir $jobOutputDir --repo-root $RepoPath 2>&1
$buildJobExit = $LASTEXITCODE
if ($buildJobExit -ne 0) {
    Write-Host "[FALHA] build_worker_job_json.py -> exit $buildJobExit`n$buildJobOutRaw" -ForegroundColor Red
    $report.fatal_error = "BUILD_JOB_JSON_FAILED"
    $report.build_job_json_output = ($buildJobOutRaw -join "`n")
    Write-ReportAndExit -ExitCode 1
}
$buildJobInfo = $buildJobOutRaw | Select-Object -Last 1 | ConvertFrom-Json
$jobJsonPath = $buildJobInfo.job_json_path
$report.recipe_checksum_sha256 = $buildJobInfo.recipe_checksum_sha256
$report.job_json_path = $jobJsonPath
Write-Host "[OK] job.json: $jobJsonPath (checksum receita: $($buildJobInfo.recipe_checksum_sha256))" -ForegroundColor Green

# ---- 2. Verifica isolamento ANTES (nenhum worker orfao de execucoes anteriores) ----
$strayBefore = @(Get-CimInstance Win32_Process -Filter "Name = 'dotnet.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "BioMatCadGeometryWorker\.dll" })
$report.stray_worker_processes_before = @($strayBefore | ForEach-Object { $_.ProcessId })
if ($strayBefore.Count -gt 0) {
    Write-Host "[AVISO] $($strayBefore.Count) processo(s) dotnet.exe do worker ja rodando ANTES desta prova (PIDs: $(($strayBefore | ForEach-Object { $_.ProcessId }) -join ', ')) -- nao encerrados automaticamente (nao rastreados por este roteiro)." -ForegroundColor Yellow
}

# ---- 3. Invoca o worker DIRETAMENTE, com stdout/stderr redirecionados para arquivos UTF-8 completos ----
$stlPath = Join-Path $jobOutputDir "scaffold.stl"
$stdoutPath = Join-Path $jobOutputDir "worker-stdout.utf8.log"
$stderrPath = Join-Path $jobOutputDir "worker-stderr.utf8.log"
$report.stl_path = $stlPath
$report.stdout_log_path = $stdoutPath
$report.stderr_log_path = $stderrPath

Write-Host "[INFO] Iniciando worker diretamente: $DotnetBin `"$dllPath`" `"$jobJsonPath`"" -ForegroundColor Cyan
$tProcessStart = Get-Date
$proc = Start-Process -FilePath $DotnetBin -ArgumentList "`"$dllPath`"", "`"$jobJsonPath`"" `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath `
    -NoNewWindow -PassThru
$report.process_id = $proc.Id
$report.t_process_start = $tProcessStart.ToString("o")
Write-Host "[OK] Processo iniciado. PID=$($proc.Id)" -ForegroundColor Green

# ---- 4. Loop de observacao (sem matar nada ate provarmos resultado completo + espera extra) ----
$pollIntervalSeconds = 0.5
$tLibraryGoReturned = $null
$tJsonFinalSeen = $null
$tResultComplete = $null
$tExtraWaitDeadline = $null
$processExitedNaturally = $false
$tProcessExited = $null
$naturalExitCode = $null
$stillAliveAfterExtraWait = $null
$stlSizeAtResultComplete = $null
$stlReopenReadableAfterResultComplete = $null
$finalJsonHasExpectedKeys = $null
$libraryGoReturnedUtcFromWorker = $null

while ($true) {
    Start-Sleep -Seconds $pollIntervalSeconds
    $now = Get-Date
    $elapsedSeconds = ($now - $tProcessStart).TotalSeconds

    if ($null -eq $tLibraryGoReturned -and (Test-Path $stderrPath)) {
        $stderrContent = Get-Content -Path $stderrPath -Raw -ErrorAction SilentlyContinue
        if ($stderrContent -and $stderrContent -match 'library_go_returned_at_utc=(\S+)') {
            $tLibraryGoReturned = $now
            $libraryGoReturnedUtcFromWorker = $Matches[1]
            Write-Host "[EVENTO] library_go_returned detectado em stderr aos $([math]::Round($elapsedSeconds,2))s (timestamp do worker: $libraryGoReturnedUtcFromWorker)" -ForegroundColor Cyan
        }
    }

    if ($null -eq $tJsonFinalSeen -and (Test-Path $stdoutPath)) {
        $stdoutContent = Get-Content -Path $stdoutPath -Raw -ErrorAction SilentlyContinue
        if ($stdoutContent) {
            $lines = @($stdoutContent -split "`r?`n" | Where-Object { $_.Trim() -ne "" })
            if ($lines.Count -gt 0) {
                $lastLine = $lines[-1]
                try {
                    $parsed = $lastLine | ConvertFrom-Json -ErrorAction Stop
                    if ($null -ne $parsed.stl_path -and $null -ne $parsed.metrics) {
                        $tJsonFinalSeen = $now
                        $finalJsonHasExpectedKeys = $true
                        Write-Host "[EVENTO] JSON final valido detectado em stdout aos $([math]::Round($elapsedSeconds,2))s" -ForegroundColor Cyan
                    }
                }
                catch { }
            }
        }
    }

    $stlExists = Test-Path $stlPath
    $stlSizeNow = if ($stlExists) { (Get-Item $stlPath).Length } else { 0 }

    if ($null -eq $tResultComplete -and $null -ne $tJsonFinalSeen -and $stlExists -and $stlSizeNow -gt 0) {
        $tResultComplete = $now
        $stlSizeAtResultComplete = $stlSizeNow
        try {
            $fs = [System.IO.File]::Open($stlPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
            $fs.Close()
            $stlReopenReadableAfterResultComplete = $true
        }
        catch {
            $stlReopenReadableAfterResultComplete = $false
        }
        $tExtraWaitDeadline = $now.AddSeconds($ExtraWaitSeconds)
        Write-Host "[EVENTO] RESULTADO COMPLETO (JSON + STL de $stlSizeAtResultComplete bytes) aos $([math]::Round($elapsedSeconds,2))s -- aguardando mais $ExtraWaitSeconds s para observar encerramento espontaneo..." -ForegroundColor Magenta
    }

    $hasExited = $proc.HasExited
    if ($hasExited -and -not $processExitedNaturally) {
        $processExitedNaturally = $true
        $tProcessExited = $now
        $naturalExitCode = $proc.ExitCode
    }

    if ($null -ne $tResultComplete) {
        if ($hasExited) {
            $stillAliveAfterExtraWait = $false
            Write-Host "[EVENTO] Processo encerrou-se SOZINHO apos resultado completo, aos $([math]::Round(($now - $tResultComplete).TotalSeconds,2))s (exit code $naturalExitCode)." -ForegroundColor Green
            break
        }
        if ($now -ge $tExtraWaitDeadline) {
            $stillAliveAfterExtraWait = $true
            Write-Host "[EVENTO] Processo AINDA VIVO apos $ExtraWaitSeconds s extras desde o resultado completo -- confirmando o sintoma relatado." -ForegroundColor Red
            break
        }
    }
    else {
        if ($hasExited) {
            Write-Host "[EVENTO] Processo encerrou ANTES de produzir um resultado completo (exit code $naturalExitCode)." -ForegroundColor Yellow
            break
        }
        if ($elapsedSeconds -gt $MaxTotalWaitSeconds) {
            Write-Host "[AVISO] Teto de seguranca de $MaxTotalWaitSeconds s atingido sem resultado completo nem saida do processo." -ForegroundColor Red
            break
        }
    }
}

# ---- 5. Se ainda vivo apos a espera extra: diagnostico de threads (melhor esforco) + encerramento controlado ----
$threadSnapshot = $null
$forciblyKilled = $false
$killConfirmed = $null

if ($stillAliveAfterExtraWait -eq $true) {
    try {
        $liveProc = Get-Process -Id $proc.Id -ErrorAction Stop
        $threadSnapshot = @($liveProc.Threads | ForEach-Object {
                [ordered]@{
                    thread_id    = $_.Id
                    thread_state = $_.ThreadState.ToString()
                    wait_reason  = try { $_.WaitReason.ToString() } catch { $null }
                }
            })
        Write-Host "[DIAGNOSTICO] $($threadSnapshot.Count) thread(s) do SO ativa(s) no processo PID $($proc.Id) no momento do encerramento controlado." -ForegroundColor Yellow
    }
    catch {
        Write-Host "[AVISO] Nao foi possivel amostrar threads do processo (melhor esforco, nao fatal): $_" -ForegroundColor Yellow
    }

    # Melhor esforco, totalmente opcional: se dotnet-dump/dotnet-trace estiverem instalados e
    # no PATH, tenta um snapshot leve -- nunca instala nada, nunca falha o roteiro se ausentes.
    $dotnetDumpAvailable = Get-Command "dotnet-dump" -ErrorAction SilentlyContinue
    if ($dotnetDumpAvailable) {
        try {
            $dumpPath = Join-Path $jobOutputDir "worker-diagnostic.dmp"
            & dotnet-dump collect -p $proc.Id -o $dumpPath 2>&1 | Out-Null
            if (Test-Path $dumpPath) {
                Write-Host "[DIAGNOSTICO] Dump de memoria capturado (melhor esforco): $dumpPath" -ForegroundColor Yellow
            }
        }
        catch {
            Write-Host "[AVISO] dotnet-dump presente mas falhou (melhor esforco, nao fatal): $_" -ForegroundColor Yellow
        }
    }

    # Encerra APENAS a arvore de processos iniciada por ESTE roteiro (PID $proc.Id + filhos
    # reais) -- nunca um taskkill global, nunca processos nao rastreados (item 14).
    $treeAll = @()
    $frontier = @($proc.Id)
    while ($frontier.Count -gt 0) {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($frontier[0])" -ErrorAction SilentlyContinue)
        $treeAll += $frontier[0]
        $frontier = $frontier[1..($frontier.Count - 1)]
        foreach ($c in $children) { $frontier += $c.ProcessId }
    }
    $treeAll = $treeAll | Select-Object -Unique
    foreach ($treePid in $treeAll) {
        try {
            Stop-Process -Id $treePid -Force -ErrorAction Stop
        }
        catch {
            Write-Host "[AVISO] Falha ao encerrar PID $treePid da arvore rastreada: $_" -ForegroundColor Yellow
        }
    }
    $forciblyKilled = $true
    Start-Sleep -Seconds 1
    $killConfirmed = -not ($treeAll | Where-Object { $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue) }) | ForEach-Object { $true }
    if (-not $killConfirmed) { $killConfirmed = $false }
    Write-Host "[INFO] Arvore de processos ($($treeAll -join ', ')) encerrada -- confirmado: $killConfirmed" -ForegroundColor Cyan
}

# ---- 6. Verificacao final de isolamento (nenhum orfao NOVO deixado por esta prova) ----
$strayAfter = @(Get-CimInstance Win32_Process -Filter "Name = 'dotnet.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "BioMatCadGeometryWorker\.dll" })
$report.stray_worker_processes_after = @($strayAfter | ForEach-Object { $_.ProcessId })

# ---- 7. Monta o relatorio estruturado final ----
$report.t_library_go_returned                       = if ($tLibraryGoReturned) { $tLibraryGoReturned.ToString("o") } else { $null }
$report.library_go_returned_at_utc_from_worker       = $libraryGoReturnedUtcFromWorker
$report.t_json_final_seen                           = if ($tJsonFinalSeen) { $tJsonFinalSeen.ToString("o") } else { $null }
$report.t_result_complete                           = if ($tResultComplete) { $tResultComplete.ToString("o") } else { $null }
$report.stl_size_at_result_complete_bytes           = $stlSizeAtResultComplete
$report.stl_reopen_readable_after_result_complete   = $stlReopenReadableAfterResultComplete
$report.process_exited_naturally                   = $processExitedNaturally
$report.t_process_exited                            = if ($tProcessExited) { $tProcessExited.ToString("o") } else { $null }
$report.natural_exit_code                           = $naturalExitCode
$report.still_alive_after_extra_wait                = $stillAliveAfterExtraWait
$report.thread_snapshot_before_forced_kill          = $threadSnapshot
$report.forcibly_killed                             = $forciblyKilled
$report.kill_confirmed                              = $killConfirmed

if ($tLibraryGoReturned) {
    $report.duration_process_start_to_library_go_returned_seconds = [math]::Round(($tLibraryGoReturned - $tProcessStart).TotalSeconds, 3)
}
elseif ($null -ne $tResultComplete) {
    # Item #168: t_library_go_returned ficou null em uma execucao real anterior (rodada
    # 20260806-211542) porque o stderr do worker veio COMPLETAMENTE VAZIO -- ou seja, o
    # marcador [DIAG_MARKER] (adicionado a Program.cs no commit 7a44da4) simplesmente nao
    # estava presente no binario efetivamente executado naquela rodada, quase certamente por
    # uso de uma DLL nao recompilada apos esse commit. A partir desta versao do roteiro, o
    # passo 0 sempre reconstroi o worker em Release explicitamente antes de rodar, o que deve
    # eliminar essa causa; se t_library_go_returned ainda vier null apos essa reconstrucao
    # explicita, e um achado real a investigar (nao mais atribuivel a uma DLL desatualizada).
    # IMPORTANTE: a auséncia deste marcador NUNCA invalida a conclusao ja comprovada da Fase A
    # (processo real terminando sozinho, com JSON final + STL legivel, exit code correto) --
    # essa conclusao decorre de t_json_final_seen/t_result_complete/process_exited_naturally,
    # que sao independentes deste marcador de diagnostico.
    $report.t_library_go_returned_null_explicacao = "marcador [DIAG_MARKER] ausente em stderr apesar de resultado completo -- provavel causa historica: DLL nao recompilada apos commit 7a44da4 (corrigido nesta versao do roteiro via build Release explicito no passo 0; ver dll_last_write_time_utc/dll_seconds_since_build_at_probe_start acima). Isso NAO invalida a conclusao do resultado completo (t_json_final_seen/t_result_complete/process_exited_naturally), que independe deste marcador."
}
if ($tLibraryGoReturned -and $tJsonFinalSeen) {
    $report.duration_library_go_returned_to_json_final_seconds = [math]::Round(($tJsonFinalSeen - $tLibraryGoReturned).TotalSeconds, 3)
}
if ($tResultComplete) {
    if ($processExitedNaturally -and $tProcessExited -and $tProcessExited -ge $tResultComplete) {
        $report.duration_process_alive_after_result_complete_seconds = [math]::Round(($tProcessExited - $tResultComplete).TotalSeconds, 3)
    }
    elseif ($stillAliveAfterExtraWait -eq $true) {
        $report.duration_process_alive_after_result_complete_seconds = $ExtraWaitSeconds
        $report.duration_process_alive_after_result_complete_note = "processo ainda vivo no momento do encerramento controlado -- duracao e um piso (>= ExtraWaitSeconds), nao o tempo total real que permaneceria vivo se nao tivesse sido encerrado"
    }
}

# Veredito literal e honesto desta prova (nunca "aprovado"/"reprovado" cientificamente aqui --
# apenas a constatacao factual pedida).
if ($null -eq $tResultComplete) {
    $report.veredito_fase_a = "SEM_RESULTADO_COMPLETO -- o worker nao chegou a produzir JSON final + STL simultaneamente dentro do teto de seguranca; nao prova nem refuta a hipotese do processo vivo pos-resultado."
}
elseif ($stillAliveAfterExtraWait -eq $true) {
    $report.veredito_fase_a = "CONFIRMADO: resultado (JSON final + STL legivel) ficou completo, e o processo permaneceu vivo por pelo menos os $ExtraWaitSeconds s extras solicitados, sem nenhum watchdog externo -- prova direta e isolada (sem API/dispatcher/timeout) de que o processo do worker nao encerra sozinho mesmo apos concluir todo o trabalho."
}
else {
    $report.veredito_fase_a = "REFUTADO NESTA EXECUCAO: o processo encerrou-se sozinho apos o resultado completo, sem necessidade de encerramento externo."
}

Write-Host ""
Write-Host "=== VEREDITO FASE A: $($report.veredito_fase_a) ===" -ForegroundColor Magenta

Write-ReportAndExit -ExitCode 0
