<#
.SYNOPSIS
    Automatiza o gate final real do Incremento 2.1.1 (item 11/12): API -> fila -> dispatcher
    -> worker PicoGK real -> STL -> Artifact -> Manifest -> download -> comparacao SHA-256.

.DESCRIPTION
    Substitui o fluxo manual de dois terminais descrito em
    docs/examples/WINDOWS_EXECUTION_KIT.md (Secao 9) por um unico comando.

    Ordem de execucao:
      1. Preflight real (apps/api/scripts/gate_preflight_check.py): confirma que o driver
         DBAPI exigido pela DATABASE_URL esta instalado, que a porta do Postgres esta
         acessivel, e que a conexao/autenticacao realmente funcionam -- ANTES de rodar
         Alembic ou iniciar a API.
      2. `alembic upgrade head` (idempotente).
      3. Inicia a API (uvicorn) em segundo plano.
      4. Espera a porta da API ficar disponivel.
      5. Roda apps/api/scripts/verify_full_pipeline_sha256.py DE VERDADE (nunca com job
         pre-semeado, nunca simulado).
      6. Encerra APENAS o processo da API que este script iniciou -- nunca um taskkill
         generico.

    GARANTIA: qualquer falha, em QUALQUER uma das etapas acima, sempre grava um relatorio
    JSON estruturado em C:\biomatcad-runs\gate-final-report.json antes de terminar. NUNCA usa
    SQLite como alternativa para aprovar o gate.

    NOTA (correcao 2026-07-29): este script foi corrigido para nao mais abortar erroneamente
    quando um comando nativo bem-sucedido (ex.: "alembic upgrade head", exit code 0) escreve
    linhas INFO em stderr -- comportamento padrao do logging do Python, mas que o PowerShell,
    quando a saida de erro e misturada ao pipeline via "2>&1" com $ErrorActionPreference=Stop,
    converte em um "NativeCommandError" terminante mesmo sem nenhuma falha real ter ocorrido.
    Corrigido combinando duas medidas: (a) $PSNativeCommandUseErrorActionPreference=$false
    (desliga o mecanismo do PowerShell 7.3+ que respeita $ErrorActionPreference para o exit
    code de comandos nativos -- os exit codes continuam sendo checados manualmente via
    $LASTEXITCODE em cada chamada, como sempre); (b) o Alembic agora redireciona stdout/stderr
    para ARQUIVOS (nunca "2>&1" misturado ao pipeline de sucesso), o que evita por completo a
    conversao de stderr em objetos ErrorRecord. Para as chamadas que precisam de saida ao vivo
    (preflight e o gate real), $ErrorActionPreference e temporariamente relaxado para
    "Continue" só durante a chamada, e restaurado a "Stop" logo em seguida.

    Também corrigida nesta mesma rodada: mojibake (acentos corrompidos) nos relatórios/logs
    gerados no Windows -- forcado UTF-8 de ponta a ponta (ver bloco de configuracao de
    encoding logo abaixo).

    Requer: PostgreSQL real já rodando e acessível na DATABASE_URL informada (este script
    NAO sobe um Postgres -- reaproveita o que voce ja configurou nos passos anteriores do
    kit de execucao Windows); .venv da API ja preparado com as dependencias necessarias
    instaladas (pip install -e ".[dev]", ou pip install -e ".[gate]" se quiser só o mínimo
    para rodar este gate sem as ferramentas de lint/teste); worker PicoGK ja compilado
    (Release, win-x64).

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

# Ver nota de correcao no cabecalho: desliga o mecanismo do PowerShell 7.3+ que trata o exit
# code de comandos nativos como um erro terminante respeitando $ErrorActionPreference -- os
# exit codes continuam sendo checados manualmente ($LASTEXITCODE) em cada chamada nativa deste
# script, exatamente como antes. Atribuir esta variavel e inofensivo em versoes do PowerShell
# que nao a reconhecem (vira apenas uma variavel de script comum, sem efeito).
$PSNativeCommandUseErrorActionPreference = $false

# Forca UTF-8 de ponta a ponta para evitar mojibake de caracteres acentuados nos relatorios e
# logs. As duas pontas precisam concordar: [Console]::OutputEncoding controla como o
# PowerShell DECODIFICA bytes lidos de processos filhos; PYTHONUTF8/PYTHONIOENCODING
# controlam como o Python CODIFICA o que escreve. $env:PYTHONUTF8/$env:PYTHONIOENCODING,
# definidos aqui no processo do proprio script, sao herdados por TODOS os processos filhos
# iniciados depois (alembic, o preflight, o gate real, e a API via Start-Process).
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
    Write-Warning "Nao foi possivel forcar [Console]::OutputEncoding para UTF-8 ($_) -- prosseguindo mesmo assim."
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\api"
$venvPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$runsDir = "C:\biomatcad-runs"
$logFile = Join-Path $runsDir "gate-final-api-output.log"
$reportSrc = Join-Path $apiDir "GATE_FULL_PIPELINE_REPORT.json"
$reportDst = Join-Path $runsDir "gate-final-report.json"

New-Item -ItemType Directory -Path $runsDir -Force | Out-Null

# Grava SEMPRE um relatorio estruturado em $reportDst antes de terminar por qualquer falha
# anterior ao proprio gate real (preflight, alembic, ou a API nunca ficar pronta) -- garante
# que o usuario NUNCA fica sem gate-final-report.json.
function Write-EarlyFailureReport {
    param(
        [string]$Stage,
        [string]$FailureReason,
        [array]$Steps = @()
    )
    $report = [ordered]@{
        gate            = "full_pipeline_real_worker"
        stage           = $Stage
        steps           = $Steps
        result          = "FAILED"
        failure_reason  = $FailureReason
        overall_ok      = $false
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -Path $reportDst -Encoding utf8
    Write-Host "Relatorio estruturado gravado em $reportDst (falha na etapa '$Stage')." -ForegroundColor Yellow
}

if (-not (Test-Path $venvPython)) {
    $msg = "Nao encontrei $venvPython. Prepare o venv da API primeiro (ver docs/examples/WINDOWS_EXECUTION_KIT.md, incluindo 'pip install -e `".[dev]`"')."
    Write-EarlyFailureReport -Stage "venv_nao_encontrado" -FailureReason $msg
    Write-Host "== GATE REPROVADO: $msg ==" -ForegroundColor Red
    exit 1
}

Write-Host "== BioMatCAD Nexus -- gate final real (API -> fila -> worker PicoGK real -> STL -> Artifact -> Manifest -> download) ==" -ForegroundColor Cyan
Write-Host "Repositorio: $repoRoot"
Write-Host "DATABASE_URL: $DatabaseUrl"
Write-Host "Receita: $Recipe   Timeout: ${TimeoutSeconds}s   Porta API: $ApiPort"

# ---- 1. Preflight real: driver DBAPI instalado, porta acessivel, conexao/autenticacao reais ----
# $ErrorActionPreference relaxado para "Continue" apenas durante esta chamada (precisamos ver a
# saida ao vivo e usar "2>&1" para juntar stdout/stderr) -- restaurado logo em seguida. Isso
# evita que uma linha eventual em stderr vire um NativeCommandError terminante mesmo quando o
# preflight termina com exit code 0.
Write-Host "`n-- Preflight: driver DBAPI, porta do Postgres e conexao/autenticacao reais --" -ForegroundColor Cyan
$previousEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$preflightJsonRaw = & $venvPython (Join-Path $apiDir "scripts\gate_preflight_check.py") --database-url $DatabaseUrl 2>&1
$preflightExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousEap
Write-Host ($preflightJsonRaw -join "`n")

if ($preflightExitCode -ne 0) {
    # O proprio gate_preflight_check.py ja imprime um JSON estruturado em stdout -- gravamos
    # esse mesmo conteudo diretamente como o relatorio final, em vez de reconstruir um novo.
    try {
        ($preflightJsonRaw -join "`n") | Set-Content -Path $reportDst -Encoding utf8
    }
    catch {
        Write-EarlyFailureReport -Stage "preflight" -FailureReason "Preflight falhou (exit code $preflightExitCode) e a saida nao pôde ser gravada como JSON: $_"
    }
    Write-Host "`n== GATE REPROVADO no preflight (exit code $preflightExitCode) -- ver $reportDst para o motivo real ==" -ForegroundColor Red
    exit $preflightExitCode
}
Write-Host "Preflight aprovado." -ForegroundColor Green

$env:DATABASE_URL = $DatabaseUrl
$env:ENVIRONMENT = "test"

# ---- 2. Alembic ----
# Redireciona stdout/stderr para ARQUIVOS (nunca "2>&1" misturado ao pipeline de sucesso) --
# isso evita por completo que as linhas INFO que o Alembic escreve em stderr (comportamento
# padrao do logging do Python) sejam convertidas em objetos ErrorRecord pelo PowerShell, o que
# abortaria o script mesmo com exit code 0 (o bug real relatado nesta rodada).
Write-Host "`n-- Rodando 'alembic upgrade head' (idempotente, garante schema atualizado) --" -ForegroundColor Cyan
$alembicStdoutFile = Join-Path $runsDir "alembic-stdout.log"
$alembicStderrFile = Join-Path $runsDir "alembic-stderr.log"
Push-Location $apiDir
try {
    & $venvPython -m alembic upgrade head 1>$alembicStdoutFile 2>$alembicStderrFile
    $alembicExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
$alembicOutputLines = @()
if (Test-Path $alembicStdoutFile) { $alembicOutputLines += Get-Content -Path $alembicStdoutFile -Encoding utf8 }
if (Test-Path $alembicStderrFile) { $alembicOutputLines += Get-Content -Path $alembicStderrFile -Encoding utf8 }
Write-Host ($alembicOutputLines -join "`n")

if ($alembicExitCode -ne 0) {
    Write-EarlyFailureReport -Stage "alembic_upgrade_head" `
        -FailureReason "alembic upgrade head falhou (exit code $alembicExitCode). Saida: $($alembicOutputLines -join ' | ')" `
        -Steps @(
            [ordered]@{ step = "preflight"; ok = $true; detail = "Preflight aprovado." }
            [ordered]@{ step = "alembic_upgrade_head"; ok = $false; detail = "exit code $alembicExitCode" }
        )
    Write-Host "`n== GATE REPROVADO: alembic upgrade head falhou -- ver $reportDst ==" -ForegroundColor Red
    exit 1
}
Write-Host "alembic upgrade head concluido com sucesso (exit code 0)." -ForegroundColor Green

# ---- 3. Iniciar a API em segundo plano ----
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
    # ---- 4. Esperar a API ficar disponivel ----
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
        $apiLogTail = ""
        if (Test-Path "$logFile.err") {
            $apiLogTail = (Get-Content "$logFile.err" -Tail 40 -Encoding utf8) -join "`n"
        }
        Write-EarlyFailureReport -Stage "api_nao_ficou_disponivel" `
            -FailureReason "A API nao ficou disponivel em 127.0.0.1:$ApiPort dentro de 60s. Log: $apiLogTail" `
            -Steps @(
                [ordered]@{ step = "preflight"; ok = $true; detail = "Preflight aprovado." }
                [ordered]@{ step = "alembic_upgrade_head"; ok = $true; detail = "ok" }
                [ordered]@{ step = "api_disponivel"; ok = $false; detail = "timeout de 60s" }
            )
        Write-Host "`n== GATE REPROVADO: API nao ficou disponivel -- ver $logFile / $logFile.err / $reportDst ==" -ForegroundColor Red
        exit 1
    }
    Write-Host "API disponivel." -ForegroundColor Green

    # ---- 5. Gate real (sem job pre-semeado, sem simulacao) ----
    # Mesma tecnica do preflight: relaxa $ErrorActionPreference so durante a chamada, para nao
    # abortar por causa de uma linha eventual em stderr (ex.: avisos de depreciacao de alguma
    # biblioteca) mesmo quando o script termina com sucesso.
    Write-Host "`n-- Rodando o gate real (verify_full_pipeline_sha256.py) -- SEM job pre-semeado, SEM simulacao --" -ForegroundColor Cyan
    Push-Location $apiDir
    try {
        $previousEap2 = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $venvPython "scripts\verify_full_pipeline_sha256.py" `
            --api-base-url "http://127.0.0.1:$ApiPort" `
            --recipe $Recipe `
            --timeout-seconds $TimeoutSeconds `
            2>&1 | Tee-Object -FilePath (Join-Path $runsDir "gate-final-output.txt")
        $gateExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousEap2
    }
    finally {
        Pop-Location
    }

    if (Test-Path $reportSrc) {
        # Copia de arquivo para arquivo (Copy-Item) -- nunca passa pelo pipeline de texto do
        # PowerShell, entao preserva os bytes UTF-8 exatos que o proprio script Python gravou
        # (report_path.write_text(..., encoding="utf-8")), sem nenhum risco de mojibake.
        Copy-Item $reportSrc $reportDst -Force
        Write-Host "Relatorio copiado para $reportDst"
    }
    else {
        Write-EarlyFailureReport -Stage "gate_real_sem_relatorio_proprio" `
            -FailureReason "verify_full_pipeline_sha256.py terminou (exit code $gateExitCode) sem gravar $reportSrc. Ver gate-final-output.txt para a saida bruta." `
            -Steps @(
                [ordered]@{ step = "preflight"; ok = $true; detail = "Preflight aprovado." }
                [ordered]@{ step = "alembic_upgrade_head"; ok = $true; detail = "ok" }
                [ordered]@{ step = "api_disponivel"; ok = $true; detail = "ok" }
                [ordered]@{ step = "gate_real_gravou_relatorio_proprio"; ok = $false; detail = "arquivo nao encontrado" }
            )
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
