using System.Diagnostics;
using BioMatCAD.Launcher;

// =============================================================================================
// BioMatCAD Nexus -- Launcher de desenvolvimento/teste (Incremento 2.1.1)
//
// Duplo clique neste executável (ou "Start-BioMatCAD.cmd") substitui a necessidade de abrir três
// PowerShells manuais para: (1) preparar/ativar o venv da API e instalar dependências, (2)
// iniciar a API (uvicorn) em localhost:8000, (3) preparar node_modules e iniciar o frontend
// (vite) em localhost:5173. Ver README.md para a lista completa dos 16 comportamentos
// implementados e a seção de segurança.
//
// AMBIENTE DE TESTE — este launcher SEMPRE define ENVIRONMENT=test e SEMPRE gera um
// API_SECRET_KEY efêmero novo a cada execução. Ele nunca habilita um ambiente clínico e nunca
// grava ou exibe o segredo gerado.
// =============================================================================================

const string PermanentBanner = "AMBIENTE DE TESTE — NÃO UTILIZAR DADOS CLÍNICOS REAIS";

Console.OutputEncoding = System.Text.Encoding.UTF8;
PrintBanner();

var isWindows = OperatingSystem.IsWindows();
var pathEnv = Environment.GetEnvironmentVariable("PATH");
var pathExtEnv = Environment.GetEnvironmentVariable("PATHEXT");

// ---- 1. Localizar a raiz do repositório ----------------------------------------------------
var startDir = AppContext.BaseDirectory;
var repoRoot = RepositoryLocator.FindRepoRoot(startDir);
if (repoRoot is null)
{
    // AppContext.BaseDirectory é onde o .exe está (ex.: dist/windows-launcher/); se o launcher
    // foi movido para fora da árvore do repositório, também tentamos a partir do diretório de
    // trabalho atual antes de desistir.
    repoRoot = RepositoryLocator.FindRepoRoot(Directory.GetCurrentDirectory());
}
if (repoRoot is null)
{
    Console.Error.WriteLine("[erro] Não foi possível localizar a raiz do repositório BioMatCAD Nexus.");
    Console.Error.WriteLine($"       Procurei a partir de: {startDir}");
    Console.Error.WriteLine("       Verifique se este executável está dentro (ou próximo) do repositório clonado.");
    return 1;
}
Console.WriteLine($"[1/16] Raiz do repositório: {repoRoot}");

var apiDir = Path.Combine(repoRoot, "apps", "api");
var webDir = Path.Combine(repoRoot, "apps", "web");

// ---- 2. Detectar Python, Node, npm e .NET ---------------------------------------------------
Console.WriteLine("[2/16] Detectando dependências (Python, Node.js, npm, .NET)...");
var python = DependencyDetector.DetectPython(pathEnv, pathExtEnv, isWindows);
var node = DependencyDetector.DetectNode(pathEnv, pathExtEnv, isWindows);
var npm = DependencyDetector.DetectNpm(pathEnv, pathExtEnv, isWindows);
var dotnet = DependencyDetector.DetectDotnet(pathEnv, pathExtEnv, isWindows);

foreach (var dep in new[] { python, node, npm, dotnet })
{
    Console.WriteLine(dep.Found
        ? $"       [ok] {dep.DependencyName}: {dep.VersionRaw} ({dep.ResolvedPath})"
        : $"       [falta] {dep.DependencyName}: {dep.Error}");
}

var gate = StartupPlanner.EvaluateDependencies(python, node, npm, dotnet);
if (!gate.CanProceed)
{
    Console.Error.WriteLine();
    Console.Error.WriteLine("[erro] Dependências obrigatórias ausentes -- não é possível continuar:");
    foreach (var reason in gate.BlockingReasons)
    {
        Console.Error.WriteLine($"       - {reason}");
    }
    return 1;
}

// ---- 14. Detectar portas ocupadas (feito antes de decidir iniciar cada serviço) -------------
const int apiPort = 8000;
const int webPort = 5173;
var apiPortInUse = PortChecker.IsPortInUse(apiPort);
var webPortInUse = PortChecker.IsPortInUse(webPort);

var apiPlan = StartupPlanner.PlanService(new ServicePlanInput("API", apiPort, apiPortInUse));
var webPlan = StartupPlanner.PlanService(new ServicePlanInput("Frontend", webPort, webPortInUse));
Console.WriteLine($"[14/16] {apiPlan.Message}");
Console.WriteLine($"[14/16] {webPlan.Message}");

using var supervisor = new ProcessSupervisor();
var cts = new CancellationTokenSource();

Console.CancelKeyPress += (_, e) =>
{
    // 13. Encerrar somente os processos filhos ao fechar/Ctrl+C -- nunca taskkill genérico.
    e.Cancel = true;
    Console.WriteLine();
    Console.WriteLine("[encerrando] Ctrl+C recebido -- finalizando somente os processos filhos iniciados por este launcher...");
    supervisor.ShutdownAll();
    cts.Cancel();
};
AppDomain.CurrentDomain.ProcessExit += (_, _) => supervisor.ShutdownAll();

try
{
    if (apiPlan.Action == ServiceAction.StartNew)
    {
        // ---- 3. Localizar ou criar apps/api/.venv -----------------------------------------
        Console.WriteLine("[3/16] Preparando ambiente virtual da API...");
        var (venvResult, venvPython) = EnvironmentSetup.EnsureApiVenv(apiDir, python.ResolvedPath!, isWindows);
        PrintStep(venvResult);
        if (!venvResult.Ok || venvPython is null)
        {
            return 1;
        }

        // ---- 4. Instalar a API com pip install -e . quando necessário ----------------------
        Console.WriteLine("[4/16] Verificando instalação da API (pip install -e . se necessário)...");
        var pipResult = EnvironmentSetup.EnsureApiInstalled(apiDir, venvPython);
        PrintStep(pipResult);
        if (!pipResult.Ok)
        {
            return 1;
        }

        // ---- 6. Gerar API_SECRET_KEY efêmera e criptograficamente segura -------------------
        // 15. Nunca gravar ou exibir o segredo: ele só existe nesta variável local em memória
        // e é passado diretamente como variável de ambiente do processo filho, nunca impresso,
        // nunca logado, nunca escrito em disco.
        var apiSecretKey = SecretGenerator.GenerateHex(32);
        Console.WriteLine("[6/16] API_SECRET_KEY efêmera gerada (não exibida, nunca gravada em disco).");

        // ---- 7. Definir ENVIRONMENT=test + 8. iniciar a API em localhost:8000 --------------
        Console.WriteLine("[7-8/16] Iniciando API em http://localhost:8000 (ENVIRONMENT=test)...");
        var apiEnv = new Dictionary<string, string>
        {
            ["ENVIRONMENT"] = "test",
            ["API_SECRET_KEY"] = apiSecretKey,
        };
        var apiHandle = supervisor.StartTracked(
            "api",
            venvPython,
            ["-m", "uvicorn", "biomatcad_api.main:app", "--host", "127.0.0.1", "--port", apiPort.ToString()],
            apiDir,
            apiEnv);
        Console.WriteLine($"       API iniciada -- PID {apiHandle.ProcessId}");
    }
    else
    {
        Console.WriteLine("[3-8/16] Pulando preparação/inicialização da API -- porta 8000 já está em uso (reaproveitando serviço existente).");
    }

    if (webPlan.Action == ServiceAction.StartNew)
    {
        // ---- 5. Verificar node_modules/package-lock ----------------------------------------
        Console.WriteLine("[5/16] Verificando dependências do frontend (node_modules)...");
        var npmResult = EnvironmentSetup.EnsureFrontendDependencies(webDir, npm.ResolvedPath!);
        PrintStep(npmResult);
        if (!npmResult.Ok)
        {
            return 1;
        }

        // ---- 9. Iniciar o frontend em localhost:5173 ---------------------------------------
        Console.WriteLine("[9/16] Iniciando frontend em http://localhost:5173...");
        var webHandle = supervisor.StartTracked(
            "frontend",
            npm.ResolvedPath!,
            ["run", "dev", "--", "--host", "127.0.0.1", "--port", webPort.ToString(), "--strictPort"],
            webDir);
        Console.WriteLine($"       Frontend iniciado -- PID {webHandle.ProcessId}");
    }
    else
    {
        Console.WriteLine("[5,9/16] Pulando preparação/inicialização do frontend -- porta 5173 já está em uso (reaproveitando serviço existente).");
    }

    // ---- 10. Aguardar os serviços ficarem disponíveis ----------------------------------------
    Console.WriteLine("[10/16] Aguardando serviços ficarem disponíveis...");
    var apiReady = PortChecker.WaitUntilReady(apiPort, TimeSpan.FromSeconds(60));
    var webReady = PortChecker.WaitUntilReady(webPort, TimeSpan.FromSeconds(60));
    Console.WriteLine($"       API pronta: {apiReady}    Frontend pronto: {webReady}");

    if (!apiReady || !webReady)
    {
        Console.Error.WriteLine("[erro] Um ou mais serviços não ficaram disponíveis a tempo. Encerrando processos iniciados por este launcher.");
        return 1;
    }

    // ---- 11. Abrir http://localhost:5173/login -----------------------------------------------
    // UseShellExecute=true é usado AQUI, exclusivamente, para abrir uma URL fixa construída
    // internamente (sem nenhum input externo/usuário concatenado) -- não é um vetor de command
    // injection porque não há nenhuma string variável sendo interpretada por um shell.
    const string loginUrl = "http://localhost:5173/login";
    Console.WriteLine($"[11/16] Abrindo {loginUrl} no navegador padrão...");
    TryOpenBrowser(loginUrl);

    // ---- 12. Mostrar status, PIDs e logs ------------------------------------------------------
    Console.WriteLine();
    Console.WriteLine("[12/16] Status:");
    foreach (var child in supervisor.Children)
    {
        Console.WriteLine($"        - {child.Name}: PID {child.ProcessId} (rodando)");
    }
    Console.WriteLine();
    Console.WriteLine("Pressione Ctrl+C para encerrar todos os processos filhos e sair.");
    PrintBanner();

    // Loop de espera -- mantém o launcher vivo enquanto os serviços filhos rodam, até Ctrl+C.
    while (!cts.IsCancellationRequested)
    {
        Thread.Sleep(1000);
    }
}
finally
{
    // 13. Encerrar somente os processos filhos ao sair, por qualquer caminho (sucesso, erro,
    // exceção não tratada) -- garante que nunca deixamos processos órfãos rodando.
    supervisor.ShutdownAll();
}

return 0;

void PrintStep(StepResult result) =>
    Console.WriteLine(result.Ok ? $"       [ok] {result.Message}" : $"       [falha] {result.Message}");

void PrintBanner()
{
    Console.WriteLine(new string('=', PermanentBanner.Length + 4));
    Console.WriteLine($"  {PermanentBanner}");
    Console.WriteLine(new string('=', PermanentBanner.Length + 4));
}

static void TryOpenBrowser(string url)
{
    try
    {
        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
    }
    catch (Exception ex)
    {
        Console.WriteLine($"       [aviso] Não foi possível abrir o navegador automaticamente ({ex.Message}). Abra manualmente: {url}");
    }
}
