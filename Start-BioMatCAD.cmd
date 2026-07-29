@echo off
setlocal

rem =============================================================================================
rem BioMatCAD Nexus -- iniciador de duplo clique (ambiente de desenvolvimento/teste)
rem
rem Este arquivo NAO precisa de tres PowerShells manuais: ele localiza o executavel do launcher
rem (dist/windows-launcher/BioMatCAD-Nexus.exe) e o executa. O launcher em si detecta Python,
rem Node, npm e .NET; prepara o venv da API e o node_modules do frontend; gera um segredo
rem efemero; inicia API e frontend; e abre o navegador em http://localhost:5173/login.
rem
rem AMBIENTE DE TESTE -- NAO UTILIZAR DADOS CLINICOS REAIS.
rem =============================================================================================

set "REPO_ROOT=%~dp0"
set "LAUNCHER_EXE=%REPO_ROOT%dist\windows-launcher\BioMatCAD-Nexus.exe"

if not exist "%LAUNCHER_EXE%" (
    echo [erro] Nao encontrei "%LAUNCHER_EXE%".
    echo        Compile o launcher primeiro com:
    echo            pwsh -File "%REPO_ROOT%scripts\Build-WindowsLauncher.ps1"
    echo.
    pause
    exit /b 1
)

"%LAUNCHER_EXE%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [aviso] O launcher terminou com codigo de saida %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
