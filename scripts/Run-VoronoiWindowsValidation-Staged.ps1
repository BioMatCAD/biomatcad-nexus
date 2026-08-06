<#
.SYNOPSIS
    Roteiro Windows ESTAGIADO da rodada Voronoi (Incremento 2.2) -- correcao real pos-auditoria
    da execucao 20260806-112714: roda primeiro APENAS um piloto pequeno (1 receita Voronoi +
    1 receita Gyroid de controle) e SO prossegue para a matriz completa (6 receitas x 2
    execucoes cada) se AMBAS as receitas do piloto tiverem sucesso.

.DESCRIPTION
    Motivacao (ver TEST_EVIDENCE.md, secao da rodada 20260806-112714): naquela execucao real, a
    primeira receita Voronoi (block-voronoi-preview-v1) excedeu o timeout (WORKER_TIMEOUT) nas
    duas tentativas, e TODAS as invocacoes seguintes do dispatcher falharam em cascata
    (exit_code=1), inclusive as golden recipes Gyroid de controle ja aprovadas -- ou seja, uma
    unica receita problematica invalidou a rodada inteira, sem produzir evidencia valida sobre
    NENHUMA das outras 5 receitas. As correcoes desta rodada (worker_client.py, geometry_
    dispatcher.py, verify_full_pipeline_sha256.py, Run-VoronoiWindowsValidation.ps1) tornam essa
    cascata especifica muito menos provavel -- mas este roteiro estagiado adiciona uma segunda
    camada de protecao estrutural: nunca gastar o tempo (e o risco de deixar processos orfaos)
    de rodar as 6 receitas x 2 execucoes se a primeira receita Voronoi ja falhar de forma
    reproduzivel.

    Este script NAO duplica nenhuma logica de gate -- ele apenas invoca
    Run-VoronoiWindowsValidation.ps1 (o roteiro unico ja corrigido) DUAS vezes:

      Estagio 1 (piloto): -Recipes @("block-voronoi-preview-v1", "preview-gyroid-low-res-v1")
      -SkipE2E, gravado em <OutputDir>\pilot. Sempre pula o E2E no piloto (o objetivo e ser
      rapido) independentemente do valor de -SkipE2E pedido pelo usuario para o estagio final.

      Avaliacao: se AMBAS as receitas do piloto tiverem run1_ok E run2_ok verdadeiros no
      CONSOLIDATED_REPORT.json do piloto, prossegue. Caso contrario, PARA aqui -- a matriz
      completa nunca roda, e o relatorio final registra explicitamente que ela foi pulada e
      por qual motivo real (nao um valor generico).

      Estagio 2 (matriz completa): -Recipes (default: as 6 golden recipes de sempre) -SkipE2E:
      $SkipE2E (respeita a preferencia do usuario para a rodada completa), gravado em
      <OutputDir>\full.

.PARAMETER RepoPath
    Ver Run-VoronoiWindowsValidation.ps1 -- repassado sem alteracao.

.PARAMETER BundlePath
    Ver Run-VoronoiWindowsValidation.ps1 -- repassado sem alteracao.

.PARAMETER Branch
    Ver Run-VoronoiWindowsValidation.ps1 -- repassado sem alteracao.

.PARAMETER DatabaseUrl
    Ver Run-VoronoiWindowsValidation.ps1 -- repassado sem alteracao.

.PARAMETER ApiPort
    Ver Run-VoronoiWindowsValidation.ps1 -- repassado sem alteracao.

.PARAMETER FullRecipes
    Receitas da matriz completa (Estagio 2), usadas somente se o piloto (Estagio 1) passar.
    Default: as mesmas 6 golden recipes de sempre (3 Voronoi + 3 Gyroid de regressao).

.PARAMETER OutputDir
    Pasta-base desta execucao estagiada. Os dois estagios gravam em subpastas 'pilot' e
    'full' dentro dela. Default: C:\biomatcad-runs\voronoi-validation-staged-<timestamp>.

.PARAMETER TimeoutSeconds
    Repassado para ambos os estagios (ver Run-VoronoiWindowsValidation.ps1 -- o timeout
    EFETIVO real por receita e calculado automaticamente por verify_full_pipeline_sha256.py a
    partir do compute_limits.max_duration_seconds de cada receita, nunca menor que isso).

.PARAMETER SkipE2E
    Aplicado somente ao Estagio 2 (matriz completa) -- o Estagio 1 (piloto) SEMPRE pula o E2E.

.PARAMETER PilotOnly
    Roda somente o Estagio 1 (piloto) e para -- util para uma verificacao rapida de sanidade
    sem comprometer tempo com a matriz completa.

.EXAMPLE
    pwsh .\scripts\Run-VoronoiWindowsValidation-Staged.ps1 `
        -RepoPath C:\dev\biomatcad-nexus `
        -BundlePath C:\Users\voce\Downloads\biomatcad-nexus-v2.2-alpha-wip.bundle `
        -DatabaseUrl "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoPath,
    [Parameter(Mandatory = $true)][string]$BundlePath,
    [string]$Branch = "incremento-2.2-alpha-pesquisa",
    [string]$DatabaseUrl = "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad",
    [int]$ApiPort = 8000,
    [string[]]$FullRecipes = @(
        "block-voronoi-preview-v1", "block-voronoi-final-v1", "cylinder-voronoi-preview-v1",
        "block-gyroid-v1", "cylinder-gyroid-v1", "preview-gyroid-low-res-v1"
    ),
    [string]$OutputDir = $null,
    [double]$TimeoutSeconds = 300,
    [switch]$SkipE2E,
    [switch]$PilotOnly
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$PILOT_RECIPES = @("block-voronoi-preview-v1", "preview-gyroid-low-res-v1")

if (-not $OutputDir) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = "C:\biomatcad-runs\voronoi-validation-staged-$timestamp"
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$innerScript = Join-Path $scriptDir "Run-VoronoiWindowsValidation.ps1"
if (-not (Test-Path $innerScript)) {
    Write-Host "ERRO: nao encontrei Run-VoronoiWindowsValidation.ps1 em $innerScript" -ForegroundColor Red
    exit 1
}

$staged = [ordered]@{
    roteiro       = "Run-VoronoiWindowsValidation-Staged.ps1"
    incremento    = "2.2 (rodada Voronoi -- correcao pos-auditoria 20260806-112714)"
    started_at    = (Get-Date).ToString("o")
    pilot_recipes = $PILOT_RECIPES
    full_recipes  = $FullRecipes
    output_dir    = $OutputDir
}

function Save-StagedReport {
    $staged.finished_at = (Get-Date).ToString("o")
    $jsonPath = Join-Path $OutputDir "STAGED_REPORT.json"
    $staged | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding utf8
    Write-Host "`nRelatorio estagiado salvo em: $jsonPath" -ForegroundColor Cyan
}

Write-Host "== BioMatCAD Nexus -- roteiro ESTAGIADO de validacao Windows, rodada Voronoi (Incremento 2.2) ==" -ForegroundColor Cyan
Write-Host "Estagio 1 (piloto): $($PILOT_RECIPES -join ', ')"
Write-Host "Estagio 2 (matriz completa, somente se o piloto passar): $($FullRecipes -join ', ')"

# ---- Estagio 1: piloto ----
$pilotOutputDir = Join-Path $OutputDir "pilot"
Write-Host "`n-- ESTAGIO 1 (piloto): $($PILOT_RECIPES -join ', ') --" -ForegroundColor Cyan
& $innerScript `
    -RepoPath $RepoPath `
    -BundlePath $BundlePath `
    -Branch $Branch `
    -DatabaseUrl $DatabaseUrl `
    -ApiPort $ApiPort `
    -Recipes $PILOT_RECIPES `
    -OutputDir $pilotOutputDir `
    -TimeoutSeconds $TimeoutSeconds `
    -SkipE2E
$pilotExit = $LASTEXITCODE
$staged.pilot_exit_code = $pilotExit
$staged.pilot_output_dir = $pilotOutputDir

$pilotReportPath = Join-Path $pilotOutputDir "CONSOLIDATED_REPORT.json"
$pilotPassed = $false
$pilotDetail = "CONSOLIDATED_REPORT.json do piloto nao encontrado em $pilotReportPath -- tratado como falha."

if (Test-Path $pilotReportPath) {
    $pilotReport = Get-Content $pilotReportPath -Raw -Encoding utf8 | ConvertFrom-Json
    $pilotRecipeResults = @($pilotReport.recipe_results)
    $allPilotRecipesOk = $true
    $details = New-Object System.Collections.Generic.List[string]
    foreach ($expectedRecipe in $PILOT_RECIPES) {
        $match = $pilotRecipeResults | Where-Object { $_.recipe -eq $expectedRecipe } | Select-Object -First 1
        if (-not $match) {
            $allPilotRecipesOk = $false
            $details.Add("$expectedRecipe`: NAO ENCONTRADO no relatorio do piloto")
            continue
        }
        $recipeOk = ($match.run1_ok -eq $true) -and ($match.run2_ok -eq $true)
        if (-not $recipeOk) { $allPilotRecipesOk = $false }
        $details.Add("$expectedRecipe`: run1_ok=$($match.run1_ok) run2_ok=$($match.run2_ok)")
    }
    $pilotPassed = $allPilotRecipesOk
    $pilotDetail = ($details -join "; ")
}

$staged.pilot_passed = $pilotPassed
$staged.pilot_detail = $pilotDetail
Write-Host "`n-- Resultado do piloto: $(if ($pilotPassed) {'PASSOU'} else {'FALHOU'}) -- $pilotDetail --" -ForegroundColor $(if ($pilotPassed) {'Green'} else {'Red'})

if ($PilotOnly) {
    $staged.full_stage_executed = $false
    $staged.full_stage_skip_reason = "Pulado via -PilotOnly (nao um resultado de falha do piloto)."
    Save-StagedReport
    if ($pilotPassed) { exit 0 } else { exit 1 }
}

if (-not $pilotPassed) {
    $staged.full_stage_executed = $false
    $staged.full_stage_skip_reason = "Piloto FALHOU -- a matriz completa NAO foi executada, para nao repetir a cascata de falhas observada na rodada 20260806-112714 (uma receita problematica invalidando a evidencia de todas as outras). Corrija a causa raiz do piloto antes de tentar a matriz completa."
    Save-StagedReport
    Write-Host "`n== ROTEIRO ESTAGIADO INTERROMPIDO: piloto falhou -- matriz completa NAO executada -- ver $pilotReportPath ==" -ForegroundColor Red
    exit 1
}

# ---- Estagio 2: matriz completa (somente se o piloto passou) ----
$fullOutputDir = Join-Path $OutputDir "full"
Write-Host "`n-- ESTAGIO 2 (matriz completa): $($FullRecipes -join ', ') --" -ForegroundColor Cyan
& $innerScript `
    -RepoPath $RepoPath `
    -BundlePath $BundlePath `
    -Branch $Branch `
    -DatabaseUrl $DatabaseUrl `
    -ApiPort $ApiPort `
    -Recipes $FullRecipes `
    -OutputDir $fullOutputDir `
    -TimeoutSeconds $TimeoutSeconds `
    -SkipE2E:$SkipE2E
$fullExit = $LASTEXITCODE
$staged.full_stage_executed = $true
$staged.full_exit_code = $fullExit
$staged.full_output_dir = $fullOutputDir

Save-StagedReport

if ($fullExit -eq 0) {
    Write-Host "`n== ROTEIRO ESTAGIADO CONCLUIDO: piloto e matriz completa OK -- revise $fullOutputDir\CONSOLIDATED_REPORT.md mesmo assim antes de declarar a rodada concluida ==" -ForegroundColor Green
    exit 0
}
else {
    Write-Host "`n== ROTEIRO ESTAGIADO CONCLUIDO COM FALHAS na matriz completa -- ver $fullOutputDir\CONSOLIDATED_REPORT.md ==" -ForegroundColor Red
    exit 1
}
