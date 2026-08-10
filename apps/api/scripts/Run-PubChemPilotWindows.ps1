<#
.SYNOPSIS
    Incremento 2.3, Rodada 2, Fase I: piloto REAL controlado de ingestao PubChem, rodando no
    Windows do usuario -- a UNICA execucao capaz de provar que o conector PubChem funciona
    contra a rede oficial (o sandbox de desenvolvimento bloqueia pubchem.ncbi.nlm.nih.gov com
    "SSL: WRONG_VERSION_NUMBER", confirmado repetidamente via curl e via o proprio codigo de
    producao -- ver docs/data/connectors/PUBCHEM_CONNECTOR.md).

.DESCRIPTION
    Este roteiro NUNCA importa em massa: no maximo 3 CIDs explicitos (parametro -Cids), cada um
    CONFIRMADO contra a resposta oficial do PubChem antes de qualquer persistencia -- nunca
    escolhidos de memoria por este roteiro sem essa confirmacao em tempo real. Se -Cids nao for
    informado, usa 3 CIDs demonstrativos bem conhecidos (2244=aspirina, 702=etanol,
    5090=ibuprofeno) -- mas mesmo esses so avancam para persistencia depois que a resposta real
    da API confirma que o CID retornado bate com o solicitado (ver
    services/connectors/pubchem.py::fetch, erro estruturado "cid_mismatch").

    Sequencia executada (cada passo aborta o roteiro com relatorio de falha se nao for bem
    sucedido):
      1. Verifica PostgreSQL acessivel na -DatabaseUrl informada (teste de conexao real).
      2. Roda 'alembic upgrade head' (idempotente).
      3. Garante o usuario administrador sintetico (biomatcad_api.seed -- reaproveita as
         credenciais sinteticas JA EXISTENTES do Incremento 1.1, NUNCA cria uma senha nova).
      4. Garante um ScientificSource real "PubChem" (scripts/ensure_pubchem_source.py,
         idempotente -- nunca duplica).
      5. Submete um DRY RUN dos CIDs informados (scripts/pubchem_ingest_cli.py --dry-run).
      6. Acompanha o request_id EXATO do dry run ate estado terminal via
         scripts/pubchem_pilot_wait_and_validate.py --kind dry_run (drena a fila -- e o que de
         fato bate na rede oficial do PubChem -- repetidamente ate esse request especifico
         terminar ou ate -TimeoutSeconds esgotar; NUNCA aceita queued/running como sucesso e
         NUNCA se contenta com "algum" request ter sido processado pelo dispatcher, apenas
         com o request submetido neste passo).
      7. Exibe o diff do dry run (nenhuma entidade cientifica foi persistida neste passo) e
         valida (scripts/pubchem_pilot_validation.py::validate_dry_run_report) que o estado
         terminal e succeeded, started_at/finished_at estao preenchidos e ZERO
         RawSourceRecord foi persistido para qualquer CID esperado.
      8. Submete a MESMA lista de CIDs como solicitacao REAL (dry_run=false).
      9. Acompanha esse request_id ate estado terminal (--kind real) e valida
         (validate_real_report) que o estado e succeeded, sem erro, e que existe exatamente 1
         RawSourceRecord por CID esperado com pelo menos 1 versao e SHA-256 nao vazio -- desta
         vez persiste de fato (RawSourceRecord + ScientificEntity/PropertyObservation em
         rascunho, nunca revisado).
     10. Submete a MESMA lista de CIDs UMA SEGUNDA VEZ (para provar idempotencia).
     11. Acompanha esse segundo request_id ate estado terminal e valida da mesma forma.
     12. Compara os relatorios das rodadas 9 e 11 via
         scripts/pubchem_pilot_check_idempotency.py::validate_idempotency: o SHA-256 do
         payload de cada CID esperado deve ser IDENTICO, nenhuma nova versao de
         RawSourceRecord deve ter sido criada, e a lista de CIDs comparados nunca pode ser
         vazia -- prova de idempotencia real, nao apenas assumida.

    Ao final, uma agregacao FAIL-CLOSED releitura todos os passos registrados no relatorio:
    so declara final_status=SUCCEEDED e exit code 0 se LITERALMENTE TODOS os passos tiverem
    ok=true. Isto substitui o comportamento anterior (Run 2, ver
    docs/data/connectors/PUBCHEM_CONNECTOR.md, INVALID_FALSE_POSITIVE) em que o roteiro so
    processava "algum" request via dispatcher --once/--limit 1 (nao necessariamente o
    submetido pelo proprio roteiro, dado que a fila e FIFO global sem escopo por request_id) e
    aceitava fail-open qualquer status != "failed", incluindo "queued", como sucesso.

    NUNCA imprime segredos (senha do usuario sintetico, DATABASE_URL com credenciais) no
    console ou no relatorio -- apenas o e-mail do usuario administrador e a URL do banco com a
    senha mascarada. Encerra apenas processos que ELE MESMO iniciou (cada chamada Python e de
    vida curta e termina sozinha -- nunca inicia um processo em segundo plano de longa duracao
    que precisaria ser morto depois).

.PARAMETER RepoPath
    Caminho ABSOLUTO do repositorio local (ja clonado/atualizado a partir do bundle
    biomatcad-nexus-incremento-2.3-rodada2-pubchem-wip.bundle).

.PARAMETER OutputDir
    Diretorio ABSOLUTO onde este roteiro grava seu relatorio JSON e log de texto.

.PARAMETER DatabaseUrl
    Connection string do PostgreSQL real a usar (deve ja existir e estar acessivel). Default:
    postgresql+psycopg2://biomatcad:biomatcad@localhost:5432/biomatcad (mesmas credenciais
    sinteticas de desenvolvimento ja documentadas em .env.example -- nunca uma senha nova).

.PARAMETER Cids
    Lista explicita de ate 3 CIDs do PubChem. Default: 2244, 702, 5090 (demonstrativos --
    CONFIRMADOS contra a resposta oficial durante a execucao, nunca assumidos).

.PARAMETER PythonBin
    Caminho do Python do venv da API. Default: <RepoPath>\apps\api\.venv\Scripts\python.exe.

.PARAMETER PollIntervalSeconds
    Intervalo (segundos) entre tentativas de drenar a fila e reconsultar o estado do request_id
    exato sendo acompanhado. Default: 3.0.

.PARAMETER TimeoutSeconds
    Tempo maximo (segundos) para um request_id especifico atingir estado terminal antes de o
    roteiro declarar falha (queued/running indefinidamente nunca e aceito). Default: 300.0.

.EXAMPLE
    .\Run-PubChemPilotWindows.ps1 -RepoPath C:\Users\adler\Documents\GitHub\biomatcad-nexus -OutputDir C:\biomatcad-runs\pubchem-pilot-20260810
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [string]$DatabaseUrl = "postgresql+psycopg2://biomatcad:biomatcad@localhost:5432/biomatcad",

    [string[]]$Cids = @("2244", "702", "5090"),

    [string]$PythonBin = $null,

    [double]$PollIntervalSeconds = 3.0,

    [double]$TimeoutSeconds = 300.0
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ---- Validacoes de caminho absoluto (nunca ambiguo dependendo do diretorio de trabalho) ----
if (-not [System.IO.Path]::IsPathRooted($RepoPath)) {
    throw "RepoPath deve ser um caminho ABSOLUTO (recebido: '$RepoPath')."
}
if (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    throw "OutputDir deve ser um caminho ABSOLUTO (recebido: '$OutputDir')."
}
if (-not (Test-Path $RepoPath)) {
    throw "RepoPath nao encontrado: $RepoPath"
}
if ($Cids.Count -eq 0) {
    throw "Pelo menos 1 CID deve ser informado."
}
if ($Cids.Count -gt 3) {
    throw "No maximo 3 CIDs por execucao deste piloto (recebidos: $($Cids.Count)) -- nunca importacao em massa. Ver docs/data/connectors/PUBCHEM_CONNECTOR.md."
}
if (-not $PythonBin) {
    $PythonBin = Join-Path $RepoPath "apps\api\.venv\Scripts\python.exe"
}
if (-not (Test-Path $PythonBin)) {
    throw "PythonBin nao encontrado: $PythonBin -- rode 'python -m venv .venv; .venv\Scripts\pip install -e .[dev]' em apps\api antes."
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$apiDir = Join-Path $RepoPath "apps\api"
$logPath = Join-Path $OutputDir "pubchem-pilot-log.txt"
$reportPath = Join-Path $OutputDir "pubchem-pilot-report.json"

function Write-Log {
    param([string]$Message)
    $line = "[$((Get-Date).ToString('o'))] $Message"
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding utf8
}

# Mascara a senha em qualquer connection string antes de logar/gravar no relatorio -- nunca
# imprime segredos, mesmo os sinteticos de desenvolvimento.
function Get-MaskedDatabaseUrl {
    param([string]$Url)
    return [regex]::Replace($Url, '://([^:@/]+):([^@]*)@', '://$1:***@')
}

$maskedDbUrl = Get-MaskedDatabaseUrl -Url $DatabaseUrl
Write-Log "== Piloto PubChem real (Incremento 2.3, Rodada 2, Fase I) =="
Write-Log "RepoPath=$RepoPath"
Write-Log "OutputDir=$OutputDir"
Write-Log "DatabaseUrl=$maskedDbUrl"
Write-Log "Cids=$($Cids -join ', ')"

$report = [ordered]@{
    schema_version   = "pubchem-pilot-windows-v1"
    repo_path        = $RepoPath
    database_url     = $maskedDbUrl
    cids_requested   = $Cids
    started_at       = (Get-Date).ToString("o")
    steps            = New-Object System.Collections.ArrayList
}

function Add-Step {
    param([string]$Name, [bool]$Ok, [string]$Detail, $Extra = $null)
    $step = [ordered]@{ name = $Name; ok = $Ok; detail = $Detail }
    if ($null -ne $Extra) { $step.extra = $Extra }
    [void]$report.steps.Add($step)
}

function Write-ReportAndExit {
    param([int]$ExitCode, [string]$FinalStatus)
    $report.finished_at = (Get-Date).ToString("o")
    $report.final_status = $FinalStatus
    $report | ConvertTo-Json -Depth 20 | Set-Content -Path $reportPath -Encoding utf8
    Write-Log "Relatorio JSON gravado em: $reportPath"
    Write-Log "Log de texto gravado em: $logPath"
    exit $ExitCode
}

function Invoke-PythonJson {
    # Roda um script Python do venv e devolve (exitCode, stdoutText, stderrText). Nunca lanca
    # excecao por conta propria -- o chamador decide como tratar exit code != 0.
    param([string[]]$ScriptArgs)
    Push-Location $apiDir
    try {
        $stdout = & $PythonBin $ScriptArgs 2>"$OutputDir\_last_stderr.tmp"
        $exitCode = $LASTEXITCODE
        $stderr = ""
        if (Test-Path "$OutputDir\_last_stderr.tmp") {
            $stderr = Get-Content -Path "$OutputDir\_last_stderr.tmp" -Raw -Encoding utf8
            Remove-Item "$OutputDir\_last_stderr.tmp" -Force -ErrorAction SilentlyContinue
        }
        return @{ ExitCode = $exitCode; Stdout = ($stdout -join "`n"); Stderr = $stderr }
    }
    finally {
        Pop-Location
    }
}

# ---- 1. PostgreSQL real acessivel -----------------------------------------------------------
Write-Log "-- Passo 1: verificando conexao real com PostgreSQL --"
$env:DATABASE_URL = $DatabaseUrl
# Delegado a scripts/pubchem_pilot_preflight_check.py (nunca mais um replace() textual embutido
# aqui -- ver docstring do script para o defeito real da Run 1 que motivou essa extracao). Esse
# script aceita postgresql://, postgresql+psycopg2:// e postgresql+psycopg:// via
# scripts/db_url_normalization.py::to_psycopg2_dsn, normalizando SOMENTE a copia isolada que ele
# passa a psycopg2.connect() -- a DATABASE_URL usada por todos os passos seguintes (alembic,
# seed, dispatcher) continua exatamente como fornecida, sem nenhuma conversao (o SQLAlchemy ja
# resolve os dois dialetos nativamente).
$dbCheck = Invoke-PythonJson -ScriptArgs @("scripts/pubchem_pilot_preflight_check.py")
if ($dbCheck.ExitCode -ne 0 -or $dbCheck.Stdout.Trim() -ne "OK") {
    # Mascara qualquer credencial que porventura apareca no stderr (o script Python ja mascara
    # por conta propria, mas mascarar de novo aqui e barato e evita que uma mudanca futura no
    # script perca essa garantia silenciosamente -- nunca confie em uma unica camada para nao
    # expor senha em log/relatorio).
    $maskedStderr = Get-MaskedDatabaseUrl -Url $dbCheck.Stderr
    Add-Step -Name "postgres_connectivity" -Ok $false -Detail "Falha ao conectar em $maskedDbUrl. stderr: $maskedStderr"
    Write-Log "[FALHA] PostgreSQL nao acessivel -- ver detalhes no relatorio."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_PREFLIGHT"
}
Add-Step -Name "postgres_connectivity" -Ok $true -Detail "Conexao real estabelecida com sucesso."
Write-Log "[OK] PostgreSQL acessivel."

# ---- 2. alembic upgrade head -----------------------------------------------------------------
Write-Log "-- Passo 2: alembic upgrade head --"
Push-Location $apiDir
try {
    $alembicOut = & $PythonBin -m alembic upgrade head 2>&1
    $alembicExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
Write-Log ($alembicOut -join "`n")
if ($alembicExit -ne 0) {
    Add-Step -Name "alembic_upgrade_head" -Ok $false -Detail "exit code $alembicExit"
    Write-Log "[FALHA] alembic upgrade head falhou."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_MIGRATION"
}
Add-Step -Name "alembic_upgrade_head" -Ok $true -Detail "Migracao aplicada com sucesso (idempotente)."
Write-Log "[OK] Migracao aplicada."

# ---- 3. Usuario admin sintetico (credenciais JA EXISTENTES, nunca uma senha nova) -----------
Write-Log "-- Passo 3: garantindo usuario administrador sintetico (biomatcad_api.seed) --"
$seedResult = Invoke-PythonJson -ScriptArgs @("-m", "biomatcad_api.seed")
Write-Log $seedResult.Stdout
if ($seedResult.ExitCode -ne 0) {
    Add-Step -Name "synthetic_admin_seed" -Ok $false -Detail "exit code $($seedResult.ExitCode). stderr: $($seedResult.Stderr)"
    Write-Log "[FALHA] Seed do usuario administrador sintetico falhou."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_SEED"
}
$adminEmailCheck = Invoke-PythonJson -ScriptArgs @("-c", "from biomatcad_api.seed import SYNTHETIC_ADMIN_EMAIL; print(SYNTHETIC_ADMIN_EMAIL)")
$adminEmail = $adminEmailCheck.Stdout.Trim()
Add-Step -Name "synthetic_admin_seed" -Ok $true -Detail "Usuario administrador sintetico garantido: $adminEmail (senha reaproveitada, nunca exibida/gravada)."
Write-Log "[OK] Usuario administrador sintetico: $adminEmail"

# ---- 4. ScientificSource real "PubChem" (idempotente) ---------------------------------------
Write-Log "-- Passo 4: garantindo ScientificSource real PubChem --"
$sourceResult = Invoke-PythonJson -ScriptArgs @("scripts/ensure_pubchem_source.py")
if ($sourceResult.ExitCode -ne 0) {
    Add-Step -Name "ensure_pubchem_source" -Ok $false -Detail "exit code $($sourceResult.ExitCode). stderr: $($sourceResult.Stderr)"
    Write-Log "[FALHA] Nao foi possivel garantir o ScientificSource PubChem."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_SOURCE_SETUP"
}
$sourceJson = $sourceResult.Stdout.Trim() | ConvertFrom-Json
$sourceId = $sourceJson.id
Add-Step -Name "ensure_pubchem_source" -Ok $true -Detail "ScientificSource PubChem id=$sourceId (created=$($sourceJson.created))."
Write-Log "[OK] ScientificSource PubChem id=$sourceId"

function Submit-IngestionRequest {
    param([bool]$DryRun)
    $cliArgs = @("scripts/pubchem_ingest_cli.py", "--requested-by-email", $adminEmail, "--source-id", $sourceId)
    foreach ($cid in $Cids) { $cliArgs += @("--cid", $cid) }
    if ($DryRun) { $cliArgs += "--dry-run" }
    $result = Invoke-PythonJson -ScriptArgs $cliArgs
    if ($result.ExitCode -ne 0) {
        return @{ Ok = $false; Detail = "CLI exit code $($result.ExitCode). stderr: $($result.Stderr)" }
    }
    $parsed = $result.Stdout.Trim() | ConvertFrom-Json
    return @{ Ok = $true; RequestId = $parsed.id }
}

function Invoke-WaitAndValidate {
    # Acompanha o request_id EXATO ate estado terminal (nunca aceita queued/running como
    # sucesso) e valida o relatorio final via scripts/pubchem_pilot_wait_and_validate.py --
    # substitui o antigo par Invoke-DispatcherOnce+Get-PilotReport, que so verificava a
    # contagem global do dispatcher e o status "!= failed" (falso positivo confirmado na Run 2:
    # ver docs/data/connectors/PUBCHEM_CONNECTOR.md, INVALID_FALSE_POSITIVE). Devolve sempre o
    # JSON {ok, reason, report} tal como o script Python o produziu -- nunca reinterpretado ou
    # afrouxado aqui.
    param([string]$RequestId, [string]$Kind)
    $cliArgs = @(
        "scripts/pubchem_pilot_wait_and_validate.py",
        "--request-id", $RequestId,
        "--kind", $Kind,
        "--poll-interval-seconds", $PollIntervalSeconds,
        "--timeout-seconds", $TimeoutSeconds
    )
    foreach ($cid in $Cids) { $cliArgs += @("--expected-cid", $cid) }
    $result = Invoke-PythonJson -ScriptArgs $cliArgs
    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        return @{ Ok = $false; Reason = "Script wait_and_validate nao produziu saida. exit=$($result.ExitCode). stderr: $($result.Stderr)"; Report = $null }
    }
    $parsed = $result.Stdout.Trim() | ConvertFrom-Json
    return @{ Ok = [bool]$parsed.ok; Reason = $parsed.reason; Report = $parsed.report }
}

function Invoke-CheckIdempotency {
    # Compara as duas rodadas de persistencia real via
    # scripts/pubchem_pilot_check_idempotency.py -- substitui o antigo loop PowerShell que
    # comparava SHA-256/contagem de versoes manualmente e que, na Run 2, tinha um bug real:
    # o ramo de "sem RawSourceRecord" fazia `continue` sem nunca propagar $idempotencyOk =
    # $false, entao o agregado ficava $true mesmo com todos os CIDs falhos (ver
    # docs/data/connectors/PUBCHEM_CONNECTOR.md, INVALID_FALSE_POSITIVE).
    param([string]$RequestId1, [string]$RequestId2)
    $cliArgs = @(
        "scripts/pubchem_pilot_check_idempotency.py",
        "--request-id-1", $RequestId1,
        "--request-id-2", $RequestId2
    )
    foreach ($cid in $Cids) { $cliArgs += @("--expected-cid", $cid) }
    $result = Invoke-PythonJson -ScriptArgs $cliArgs
    if ([string]::IsNullOrWhiteSpace($result.Stdout)) {
        return @{ Ok = $false; Reason = "Script check_idempotency nao produziu saida. exit=$($result.ExitCode). stderr: $($result.Stderr)"; Details = @() }
    }
    $parsed = $result.Stdout.Trim() | ConvertFrom-Json
    return @{ Ok = [bool]$parsed.ok; Reason = $parsed.reason; Details = $parsed.details }
}

# ---- 5-7. DRY RUN: confirma resposta oficial sem persistir nada ----------------------------
Write-Log "-- Passo 5: submetendo DRY RUN dos CIDs $($Cids -join ', ') --"
$dryRunSubmit = Submit-IngestionRequest -DryRun $true
if (-not $dryRunSubmit.Ok) {
    Add-Step -Name "dry_run_submit" -Ok $false -Detail $dryRunSubmit.Detail
    Write-Log "[FALHA] Submissao do dry run falhou: $($dryRunSubmit.Detail)"
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_DRY_RUN_SUBMIT"
}
Write-Log "[OK] Dry run enfileirado: $($dryRunSubmit.RequestId)"

Write-Log "-- Passo 6: acompanhando o request_id exato do dry run ate estado terminal (timeout=${TimeoutSeconds}s) --"
$dryRunWait = Invoke-WaitAndValidate -RequestId $dryRunSubmit.RequestId -Kind "dry_run"
$dryRunReport = $dryRunWait.Report
if ($null -eq $dryRunReport) {
    Add-Step -Name "dry_run_result" -Ok $false -Detail $dryRunWait.Reason
    Write-Log "[FALHA] $($dryRunWait.Reason)"
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_DRY_RUN_REPORT"
}
Write-Log "[INFO] Dry run finalizado com status: $($dryRunReport.status)"
Write-Log "[INFO] Diff do dry run (nenhuma entidade persistida): $($dryRunReport.summary | ConvertTo-Json -Depth 10 -Compress)"

if ($dryRunReport.status -eq "failed") {
    Write-Log "[FALHA] Dry run falhou para todos os CIDs -- tratando como bloqueio de rede/PubChem ate prova em contrario (ver REGRAS ADICIONAIS regra 1). Interrompendo o piloto -- nenhuma persistencia sera tentada."
    Add-Step -Name "network_reachability" -Ok $false -Detail "Todos os CIDs falharam na busca durante o dry run -- rede PubChem pode estar bloqueada/indisponivel neste ambiente Windows tambem. Ver fetch_errors." -Extra $dryRunReport.summary.fetch_errors
    Write-ReportAndExit -ExitCode 2 -FinalStatus "NETWORK_UNREACHABLE_OR_ALL_CIDS_FAILED"
}
Add-Step -Name "network_reachability" -Ok $true -Detail "Ao menos um CID foi confirmado com sucesso contra a resposta oficial do PubChem (estado terminal != failed)."

# dry_run_result so e Ok=true se: estado terminal succeeded; started_at/finished_at
# preenchidos; summary coerente; ZERO RawSourceRecord persistido para qualquer CID esperado --
# validado por scripts/pubchem_pilot_validation.py::validate_dry_run_report. Isto substitui o
# antigo teste fail-open "status -eq succeeded -or status -eq partial", responsavel (junto com
# o Bug A do passo real, abaixo) pelo falso positivo da Run 2 (ver
# docs/data/connectors/PUBCHEM_CONNECTOR.md, INVALID_FALSE_POSITIVE).
Add-Step -Name "dry_run_result" -Ok $dryRunWait.Ok -Detail $dryRunWait.Reason -Extra $dryRunReport
if (-not $dryRunWait.Ok) {
    Write-Log "[FALHA] Validacao do dry run reprovada: $($dryRunWait.Reason)"
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_VALIDATION"
}

# ---- 8-9. Persistencia real (primeira vez) --------------------------------------------------
Write-Log "-- Passo 8: submetendo solicitacao REAL (persistente) dos mesmos CIDs --"
$realSubmit1 = Submit-IngestionRequest -DryRun $false
if (-not $realSubmit1.Ok) {
    Add-Step -Name "real_submit_1" -Ok $false -Detail $realSubmit1.Detail
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_SUBMIT_1"
}
Write-Log "[OK] Solicitacao real enfileirada: $($realSubmit1.RequestId)"

Write-Log "-- Passo 9: acompanhando o request_id exato da 1a persistencia real ate estado terminal (timeout=${TimeoutSeconds}s) --"
$realWait1 = Invoke-WaitAndValidate -RequestId $realSubmit1.RequestId -Kind "real"
$realReport1 = $realWait1.Report
if ($null -eq $realReport1) {
    Add-Step -Name "real_result_1" -Ok $false -Detail $realWait1.Reason
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_DISPATCH_1"
}
# real_result_1 so e Ok=true se: estado terminal succeeded; started_at/finished_at
# preenchidos; error ausente; exatamente 1 RawSourceRecord por CID esperado com >=1 versao e
# SHA-256 nao vazio -- validado por
# scripts/pubchem_pilot_validation.py::validate_real_report. Isto substitui o antigo teste
# fail-open "status -ne failed" (Bug A confirmado na Run 2 -- aceitava "queued" como sucesso;
# ver docs/data/connectors/PUBCHEM_CONNECTOR.md, INVALID_FALSE_POSITIVE).
Add-Step -Name "real_result_1" -Ok $realWait1.Ok -Detail $realWait1.Reason -Extra $realReport1
Write-Log "[INFO] Primeira persistencia real finalizada com status: $($realReport1.status)"
if (-not $realWait1.Ok) {
    Write-Log "[FALHA] Validacao da primeira persistencia real reprovada: $($realWait1.Reason)"
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_VALIDATION"
}

# ---- 10-12. Repete para provar idempotencia -------------------------------------------------
Write-Log "-- Passo 10: submetendo a MESMA solicitacao real novamente (prova de idempotencia) --"
$realSubmit2 = Submit-IngestionRequest -DryRun $false
if (-not $realSubmit2.Ok) {
    Add-Step -Name "real_submit_2" -Ok $false -Detail $realSubmit2.Detail
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_SUBMIT_2"
}
Write-Log "[OK] Segunda solicitacao real enfileirada: $($realSubmit2.RequestId)"

Write-Log "-- Passo 11: acompanhando o request_id exato da 2a persistencia real ate estado terminal (timeout=${TimeoutSeconds}s) --"
$realWait2 = Invoke-WaitAndValidate -RequestId $realSubmit2.RequestId -Kind "real"
$realReport2 = $realWait2.Report
if ($null -eq $realReport2) {
    Add-Step -Name "real_result_2" -Ok $false -Detail $realWait2.Reason
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_DISPATCH_2"
}
Add-Step -Name "real_result_2" -Ok $realWait2.Ok -Detail $realWait2.Reason -Extra $realReport2
Write-Log "[INFO] Segunda persistencia real finalizada com status: $($realReport2.status)"
if (-not $realWait2.Ok) {
    Write-Log "[FALHA] Validacao da segunda persistencia real reprovada: $($realWait2.Reason)"
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_VALIDATION"
}

Write-Log "-- Passo 12: comparando hashes SHA-256 entre as duas rodadas (prova de idempotencia real) --"
# Delegado a scripts/pubchem_pilot_check_idempotency.py::validate_idempotency -- substitui o
# antigo loop PowerShell que tinha um bug real confirmado na Run 2: o ramo "sem
# RawSourceRecord" fazia `continue` sem nunca propagar $idempotencyOk = $false, entao o
# agregado ficava $true mesmo com TODOS os CIDs com ok=false (ver
# docs/data/connectors/PUBCHEM_CONNECTOR.md, INVALID_FALSE_POSITIVE). A nova validacao exige
# lista nao vazia e every(ok) para aprovar -- lista vazia ou qualquer item false reprova.
$idempotencyCheck = Invoke-CheckIdempotency -RequestId1 $realSubmit1.RequestId -RequestId2 $realSubmit2.RequestId
foreach ($detail in $idempotencyCheck.Details) {
    Write-Log "[INFO] CID $($detail.cid) -- ok=$($detail.ok) -- $($detail | ConvertTo-Json -Depth 10 -Compress)"
}
Add-Step -Name "idempotency_proof" -Ok $idempotencyCheck.Ok -Detail $idempotencyCheck.Reason -Extra $idempotencyCheck.Details

if (-not $idempotencyCheck.Ok) {
    Write-Log "[FALHA] Idempotencia NAO comprovada -- ver idempotency_proof no relatorio."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "IDEMPOTENCY_NOT_PROVEN"
}

Write-Log "[OK] Idempotencia comprovada: mesmo payload em ambas as rodadas -- SHA-256 identico, nenhuma nova versao de RawSourceRecord criada."

# ---- Agregacao FAIL-CLOSED final ------------------------------------------------------------
# Nunca declarar SUCCEEDED/exit 0 so porque chegamos ate aqui sem um 'throw'/exit explicito -- a
# Run 2 provou que isso e insuficiente (nenhuma das condicoes de aborto codificadas disparou, e
# o roteiro caiu no SUCCEEDED incondicional do final do arquivo mesmo com queued/sem
# RawSourceRecord/idempotencia toda falsa). Em vez disso, releia TODOS os passos ja registrados
# no relatorio e so declare sucesso se, literalmente, todos tiverem ok=true -- qualquer passo
# com ok=false aqui reprova o piloto, mesmo que nenhum 'exit' anterior tenha disparado.
$failedSteps = @($report.steps | Where-Object { -not $_.ok })
if ($failedSteps.Count -gt 0) {
    $failedNames = ($failedSteps | ForEach-Object { $_.name }) -join ', '
    Write-Log "[FALHA] Agregacao fail-closed reprovou o piloto -- passo(s) com ok=false: $failedNames"
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_VALIDATION"
}

Write-Log "== PILOTO PUBCHEM REAL CONCLUIDO COM SUCESSO =="
Write-ReportAndExit -ExitCode 0 -FinalStatus "SUCCEEDED"
