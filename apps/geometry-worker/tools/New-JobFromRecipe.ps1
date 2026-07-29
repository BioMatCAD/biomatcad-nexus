<#
.SYNOPSIS
    Monta um job.json (contrato de entrada do worker) a partir de uma receita canônica
    (golden recipe ou qualquer outra receita válida contra o schema BioMatCEM v1).

.DESCRIPTION
    O worker (BioMatCadGeometryWorker.dll) espera um único argumento: o caminho para um
    job.json contendo { job_id, recipe, output_dir }. Este script existe apenas para poupar
    a montagem manual desse envelope ao rodar o worker isoladamente no Windows, fora do
    fluxo completo API -> fila -> dispatcher (Incremento 2.1.1, Seção 15 -- kit de execução).

.PARAMETER RecipePath
    Caminho para o arquivo JSON da receita (ex.: schemas\biomatcem\golden-recipes\block-gyroid-v1.json).

.PARAMETER JobId
    Identificador do job. Se omitido, gera um GUID.

.PARAMETER OutputDir
    Diretório onde o worker deve gravar os artefatos (STL, etc.). Criado se não existir.

.EXAMPLE
    .\New-JobFromRecipe.ps1 -RecipePath ..\..\..\schemas\biomatcem\golden-recipes\block-gyroid-v1.json `
        -OutputDir C:\biomatcad-runs\block-gyroid-v1
#>
param(
    [Parameter(Mandatory = $true)][string]$RecipePath,
    [string]$JobId = [guid]::NewGuid().ToString(),
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $RecipePath)) {
    throw "Receita não encontrada: $RecipePath"
}

$recipe = Get-Content -Raw -Path $RecipePath | ConvertFrom-Json

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
$OutputDir = (Resolve-Path $OutputDir).Path

$job = [ordered]@{
    job_id     = $JobId
    recipe     = $recipe
    output_dir = $OutputDir
}

$jobJsonPath = Join-Path $OutputDir "job.json"
$job | ConvertTo-Json -Depth 20 | Set-Content -Path $jobJsonPath -Encoding utf8

Write-Host "job.json gerado em: $jobJsonPath"
Write-Host "output_dir:         $OutputDir"
Write-Host "job_id:             $JobId"
Write-Output $jobJsonPath
