<#
.SYNOPSIS
    Compila (cross-publish) o launcher executavel do BioMatCAD Nexus para Windows x64.

.DESCRIPTION
    Gera dist/windows-launcher/BioMatCAD-Nexus.exe a partir de
    tools/windows-launcher/BioMatCAD.Launcher.csproj, usando:
        dotnet publish -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true

    Framework-dependente (self-contained=false) porque o .NET 9 Runtime ja e um
    pre-requisito documentado do worker PicoGK (ver docs/examples/WINDOWS_EXECUTION_KIT.md) --
    nao ha necessidade de inflar o executavel do launcher com um runtime autocontido.

    Este script tambem roda a suite de testes reais (xUnit) do launcher ANTES de publicar,
    e se recusa a publicar se algum teste falhar -- nunca publica um binario nao testado.

.PARAMETER SkipTests
    Pula a execucao dos testes antes do build. Use apenas para iteracao rapida local; o
    fluxo padrao (sem este parametro) sempre roda os testes primeiro.

.EXAMPLE
    pwsh ./scripts/Build-WindowsLauncher.ps1

.EXAMPLE
    pwsh ./scripts/Build-WindowsLauncher.ps1 -SkipTests
#>
[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcherProj = Join-Path $repoRoot "tools/windows-launcher/BioMatCAD.Launcher.csproj"
$testsProj = Join-Path $repoRoot "tools/windows-launcher/tests/BioMatCAD.Launcher.Tests/BioMatCAD.Launcher.Tests.csproj"
$outDir = Join-Path $repoRoot "dist/windows-launcher"

if (-not (Test-Path $launcherProj)) {
    throw "Nao encontrei $launcherProj. Rode este script a partir de um clone completo do repositorio BioMatCAD Nexus."
}

Write-Host "== BioMatCAD Nexus -- build do launcher Windows ==" -ForegroundColor Cyan
Write-Host "Repositorio: $repoRoot"

if (-not $SkipTests) {
    Write-Host "`n-- Rodando testes reais do launcher (dotnet test) --" -ForegroundColor Cyan
    dotnet test $testsProj
    if ($LASTEXITCODE -ne 0) {
        throw "Testes do launcher falharam (exit code $LASTEXITCODE). Build cancelado -- nunca publicamos um binario nao testado."
    }
}
else {
    Write-Warning "SkipTests foi usado -- os testes NAO foram executados antes deste build. Nao use isto para o binario de entrega final."
}

Write-Host "`n-- Publicando win-x64 (framework-dependente, single-file) --" -ForegroundColor Cyan
if (Test-Path $outDir) {
    Remove-Item -Recurse -Force $outDir
}
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

dotnet publish $launcherProj `
    -c Release `
    -r win-x64 `
    --self-contained false `
    -p:PublishSingleFile=true `
    -o $outDir

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish falhou (exit code $LASTEXITCODE)."
}

$exePath = Join-Path $outDir "BioMatCAD-Nexus.exe"
if (-not (Test-Path $exePath)) {
    throw "Publish concluido mas $exePath nao foi encontrado -- verifique a saida do dotnet publish acima."
}

$hash = Get-FileHash -Path $exePath -Algorithm SHA256
$hashLine = "$($hash.Hash.ToLowerInvariant())  BioMatCAD-Nexus.exe"
Set-Content -Path (Join-Path $outDir "BioMatCAD-Nexus.exe.sha256") -Value $hashLine -Encoding ascii

Write-Host "`n== Build concluido ==" -ForegroundColor Green
Write-Host "Executavel: $exePath"
Write-Host "SHA-256:    $($hash.Hash.ToLowerInvariant())"
Write-Host "`nPara rodar: va ate a raiz do repositorio e de duplo clique em Start-BioMatCAD.cmd,"
Write-Host "ou execute diretamente: $exePath"
