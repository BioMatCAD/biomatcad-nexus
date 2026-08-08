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
      6. Processa a fila uma unica vez (scripts/scientific_ingestion_dispatcher.py --once) --
         isto e o que de fato bate na rede oficial do PubChem.
      7. Exibe o diff do dry run (nenhuma entidade cientifica foi persistida neste passo).
      8. Submete a MESMA lista de CIDs como solicitacao REAL (dry_run=false).
      9. Processa a fila novamente (--once) -- desta vez persiste (RawSourceRecord +
         ScientificEntity/PropertyObservation em rascunho, nunca revisado).
     10. Submete a MESMA lista de CIDs UMA SEGUNDA VEZ (para provar idempotencia).
     11. Processa a fila mais uma vez (--once).
     12. Compara os relatorios das rodadas 9 e 11: o SHA-256 do payload de cada CID deve ser
         IDENTICO, e nenhuma nova versao de RawSourceRecord deve ter sido criada (mesmo
         payload = nenhuma linha nova) -- prova de idempotencia real, nao apenas assumida.

    NUNCA imprime segredos (senha do usuario sintetico, DATABASE_URL com credenciais) no
    console ou no relatorio -- apenas o e-mail do usuario administrador e a URL do banco com a
    senha mascarada. Encerra apenas processos que ELE MESMO iniciou (o dispatcher roda sempre
    em --once, um processo de vida curta que termina sozinho -- nunca inicia um processo em
    segundo plano de longa duracao que precisaria ser morto depois).

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

    [string]$PythonBin = $null
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
$dbCheck = Invoke-PythonJson -ScriptArgs @("-c", "import psycopg2, os, sys; url = os.environ['DATABASE_URL'].replace('postgresql+psycopg2://', 'postgresql://'); psycopg2.connect(url).close(); print('OK')")
if ($dbCheck.ExitCode -ne 0 -or $dbCheck.Stdout.Trim() -ne "OK") {
    Add-Step -Name "postgres_connectivity" -Ok $false -Detail "Falha ao conectar em $maskedDbUrl. stderr: $($dbCheck.Stderr)"
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

function Invoke-DispatcherOnce {
    $result = Invoke-PythonJson -ScriptArgs @("scripts/scientific_ingestion_dispatcher.py", "--once", "--limit", "1")
    Write-Log $result.Stdout
    return $result.ExitCode -eq 0
}

function Get-PilotReport {
    param([string]$RequestId)
    $result = Invoke-PythonJson -ScriptArgs @("scripts/pubchem_pilot_report.py", "--request-id", $RequestId)
    if ($result.ExitCode -ne 0) {
        return $null
    }
    return ($result.Stdout | ConvertFrom-Json)
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

Write-Log "-- Passo 6: processando a fila uma vez (dry run -- bate na rede oficial do PubChem) --"
if (-not (Invoke-DispatcherOnce)) {
    Add-Step -Name "dry_run_dispatch" -Ok $false -Detail "Dispatcher --once falhou ao processar o dry run."
    Write-Log "[FALHA] Dispatcher falhou processando o dry run."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_DRY_RUN_DISPATCH"
}

$dryRunReport = Get-PilotReport -RequestId $dryRunSubmit.RequestId
if ($null -eq $dryRunReport) {
    Add-Step -Name "dry_run_report" -Ok $false -Detail "Nao foi possivel obter o relatorio do dry run."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_DRY_RUN_REPORT"
}
Add-Step -Name "dry_run_result" -Ok ($dryRunReport.status -eq "succeeded" -or $dryRunReport.status -eq "partial") -Detail "status=$($dryRunReport.status)" -Extra $dryRunReport.summary
Write-Log "[INFO] Dry run finalizado com status: $($dryRunReport.status)"
Write-Log "[INFO] Diff do dry run (nenhuma entidade persistida): $($dryRunReport.summary | ConvertTo-Json -Depth 10 -Compress)"

if ($dryRunReport.status -eq "failed") {
    Write-Log "[FALHA] Dry run falhou para todos os CIDs -- tratando como bloqueio de rede/PubChem ate prova em contrario (ver REGRAS ADICIONAIS regra 1). Interrompendo o piloto -- nenhuma persistencia sera tentada."
    Add-Step -Name "network_reachability" -Ok $false -Detail "Todos os CIDs falharam na busca durante o dry run -- rede PubChem pode estar bloqueada/indisponivel neste ambiente Windows tambem. Ver fetch_errors." -Extra $dryRunReport.summary.fetch_errors
    Write-ReportAndExit -ExitCode 2 -FinalStatus "NETWORK_UNREACHABLE_OR_ALL_CIDS_FAILED"
}
Add-Step -Name "network_reachability" -Ok $true -Detail "Ao menos um CID foi confirmado com sucesso contra a resposta oficial do PubChem."

# ---- 8-9. Persistencia real (primeira vez) --------------------------------------------------
Write-Log "-- Passo 8: submetendo solicitacao REAL (persistente) dos mesmos CIDs --"
$realSubmit1 = Submit-IngestionRequest -DryRun $false
if (-not $realSubmit1.Ok) {
    Add-Step -Name "real_submit_1" -Ok $false -Detail $realSubmit1.Detail
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_SUBMIT_1"
}
Write-Log "[OK] Solicitacao real enfileirada: $($realSubmit1.RequestId)"

Write-Log "-- Passo 9: processando a fila (persistencia real, primeira vez) --"
if (-not (Invoke-DispatcherOnce)) {
    Add-Step -Name "real_dispatch_1" -Ok $false -Detail "Dispatcher --once falhou na primeira persistencia real."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_DISPATCH_1"
}
$realReport1 = Get-PilotReport -RequestId $realSubmit1.RequestId
Add-Step -Name "real_result_1" -Ok ($realReport1.status -ne "failed") -Detail "status=$($realReport1.status)" -Extra $realReport1
Write-Log "[INFO] Primeira persistencia real finalizada com status: $($realReport1.status)"

# ---- 10-12. Repete para provar idempotencia -------------------------------------------------
Write-Log "-- Passo 10: submetendo a MESMA solicitacao real novamente (prova de idempotencia) --"
$realSubmit2 = Submit-IngestionRequest -DryRun $false
if (-not $realSubmit2.Ok) {
    Add-Step -Name "real_submit_2" -Ok $false -Detail $realSubmit2.Detail
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_SUBMIT_2"
}
Write-Log "[OK] Segunda solicitacao real enfileirada: $($realSubmit2.RequestId)"

Write-Log "-- Passo 11: processando a fila (segunda vez) --"
if (-not (Invoke-DispatcherOnce)) {
    Add-Step -Name "real_dispatch_2" -Ok $false -Detail "Dispatcher --once falhou na segunda persistencia real."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "FAILED_REAL_DISPATCH_2"
}
$realReport2 = Get-PilotReport -RequestId $realSubmit2.RequestId
Add-Step -Name "real_result_2" -Ok ($realReport2.status -ne "failed") -Detail "status=$($realReport2.status)" -Extra $realReport2

Write-Log "-- Passo 12: comparando hashes SHA-256 entre as duas rodadas (prova de idempotencia real) --"
$idempotencyOk = $true
$idempotencyDetails = New-Object System.Collections.ArrayList
foreach ($cid in $Cids) {
    $rec1 = $realReport1.raw_source_records | Where-Object { $_.external_id -eq $cid } | Select-Object -First 1
    $rec2 = $realReport2.raw_source_records | Where-Object { $_.external_id -eq $cid } | Select-Object -First 1
    if ($null -eq $rec1 -or $rec1.version_count -eq 0) {
        [void]$idempotencyDetails.Add(@{ cid = $cid; ok = $false; reason = "sem RawSourceRecord na primeira rodada (busca deste CID pode ter falhado)" })
        continue
    }
    $hash1 = $rec1.versions[-1].payload_sha256
    $count1 = $rec1.version_count
    $hash2 = $rec2.versions[-1].payload_sha256
    $count2 = $rec2.version_count
    $sameHash = ($hash1 -eq $hash2)
    $noNewVersion = ($count2 -eq $count1)
    $cidOk = $sameHash -and $noNewVersion
    if (-not $cidOk) { $idempotencyOk = $false }
    [void]$idempotencyDetails.Add(@{
        cid = $cid; ok = $cidOk; sha256_round1 = $hash1; sha256_round2 = $hash2
        version_count_round1 = $count1; version_count_round2 = $count2
    })
    Write-Log "[INFO] CID $cid -- sha256 rodada1=$hash1 rodada2=$hash2 (identico=$sameHash), versoes rodada1=$count1 rodada2=$count2 (sem nova versao=$noNewVersion)"
}
Add-Step -Name "idempotency_proof" -Ok $idempotencyOk -Detail "Comparacao de SHA-256 e contagem de versoes entre as duas rodadas de persistencia real." -Extra $idempotencyDetails

if (-not $idempotencyOk) {
    Write-Log "[FALHA] Idempotencia NAO comprovada -- ver idempotency_proof no relatorio."
    Write-ReportAndExit -ExitCode 1 -FinalStatus "IDEMPOTENCY_NOT_PROVEN"
}

Write-Log "[OK] Idempotencia comprovada: mesmo payload em ambas as rodadas -- SHA-256 identico, nenhuma nova versao de RawSourceRecord criada."
Write-Log "== PILOTO PUBCHEM REAL CONCLUIDO COM SUCESSO =="
Write-ReportAndExit -ExitCode 0 -FinalStatus "SUCCEEDED"
