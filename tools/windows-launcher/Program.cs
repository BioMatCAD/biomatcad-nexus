using System.Diagnostics;
using BioMatCAD.Launcher;

// =============================================================================================
// BioMatCAD Nexus -- Launcher de pesquisa (Incremento 2.1.1 + Incremento 2.2, seção 2)
//
// Duplo clique neste executável (ou "Start-BioMatCAD.cmd") substitui a necessidade de abrir
// vários PowerShells manuais para: (1) preflight real do PostgreSQL, (2) migrações Alembic,
// (3) preparar/ativar o venv da API e instalar dependências, (4) iniciar a API (uvicorn) em
// localhost:8000, (5) iniciar o dispatcher geométrico contínuo (scripts/geometry_dispatcher.py,
// Incremento 2.2 seção 3), (6) preparar node_modules e iniciar o frontend (vite) em
// localhost:5173, (7) abrir o navegador só quando tudo estiver pronto. Ver README.md.
//
// AMBIENTE DE PESQUISA — este launcher SEMPRE define ENVIRONMENT=test e SEMPRE gera um
// API_SECRET_KEY efêmero novo a cada execução, apenas em memória. Nunca habilita um ambiente
// clínico, nunca grava ou exibe o segredo gerado, nunca cria/altera um usuário PostgreSQL, e
// nunca exibe senha, API_SECRET_KEY, JWT ou a DATABASE_URL completa.
// =============================================================================================

const string PermanentBanner = "AMBIENTE DE PESQUISA — NÃO UTILIZAR DADOS CLÍNICOS REAIS";
const int ApiPort = 8000;
const int WebPort = 5173;
const double DispatcherBasePollIntervalSeconds = 3.0;
var DispatcherGracefulShutdownTimeout = TimeSpan.FromSeconds(20);
var DispatcherStartupGrace = TimeSpan.FromSeconds(30);

Console.OutputEncoding = System.Text.Encoding.UTF8;
PrintBanner();

var isWindows = OperatingSystem.IsWindows();
var pathEnv = Environment.GetEnvironmentVariable("PATH");
var pathExtEnv = Environment.GetEnvironmentVariable("PATHEXT");

// ---- 1. Localizar a raiz do repositório ----------------------------------------------------
var startDir = AppContext.BaseDirectory;
var repoRoot = RepositoryLocator.FindRepoRoot(startDir) ?? RepositoryLocator.FindRepoRoot(Directory.GetCurrentDirectory());
if (repoRoot is null)
{
    Console.Error.WriteLine("[erro] Não foi possível localizar a raiz do repositório BioMatCAD Nexus.");
    Console.Error.WriteLine($"       Procurei a partir de: {startDir}");
    Console.Error.WriteLine("       Verifique se este executável está dentro (ou próximo) do repositório clonado.");
    return 1;
}
Console.WriteLine($"[repo] Raiz do repositório: {repoRoot}");

var apiDir = Path.Combine(repoRoot, "apps", "api");
var webDir = Path.Combine(repoRoot, "apps", "web");
var logsDir = Path.Combine(repoRoot, "data", "launcher-logs");
var artifactsDirDefault = Path.Combine(apiDir, "data", "artifacts");
var dispatcherStatusFile = Path.Combine(artifactsDirDefault, "_dispatcher", "status.json");
var dispatcherStopFile = Path.Combine(artifactsDirDefault, "_dispatcher", "stop_requested");
Directory.CreateDirectory(logsDir);

// ---- 2. Detectar Python, Node, npm e .NET ---------------------------------------------------
Console.WriteLine("[deps] Detectando dependências (Python, Node.js, npm, .NET)...");
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

// ---- 3. Preparar apps/api/.venv + pip install -e . (necessário para preflight e migrações) --
Console.WriteLine("[venv] Preparando ambiente virtual da API...");
var (venvResult, venvPython) = EnvironmentSetup.EnsureApiVenv(apiDir, python.ResolvedPath!, isWindows);
PrintStep(venvResult);
if (!venvResult.Ok || venvPython is null)
{
    return 1;
}
var pipResult = EnvironmentSetup.EnsureApiInstalled(apiDir, venvPython);
PrintStep(pipResult);
if (!pipResult.Ok)
{
    return 1;
}

// ---- 4. Preflight real do PostgreSQL (Incremento 2.2, seção 2, item 1) ----------------------
Console.WriteLine("[banco] Verificando configuração do banco de dados...");
var databaseUrl = DatabasePreflight.ReadDatabaseUrl(apiDir, repoRoot);
if (databaseUrl is null)
{
    var missing = DatabasePreflight.MissingConfiguration(apiDir, repoRoot);
    Console.Error.WriteLine();
    Console.Error.WriteLine("[erro] Banco de dados não configurado.");
    Console.Error.WriteLine($"       {missing.GuidanceMessage}");
    return 1;
}
Console.WriteLine($"       DATABASE_URL: {DatabasePreflight.SanitizeForDisplay(databaseUrl)}");

var preflight = DatabasePreflight.Run(venvPython, apiDir, databaseUrl);
foreach (var step in preflight.Steps)
{
    Console.WriteLine(step.Ok ? $"       [ok] {step.Step}: {step.Detail}" : $"       [falha] {step.Step}: {step.Detail}");
}
if (!preflight.Ok)
{
    Console.Error.WriteLine();
    Console.Error.WriteLine("[erro] Preflight do banco de dados falhou -- não é possível continuar.");
    Console.Error.WriteLine($"       Motivo: {preflight.FailureReason}");
    Console.Error.WriteLine("       Este launcher NUNCA cria ou altera um usuário/senha do PostgreSQL automaticamente.");
    Console.Error.WriteLine("       Verifique se o PostgreSQL está rodando, acessível, e se as credenciais em DATABASE_URL estão corretas.");
    return 1;
}
Console.WriteLine("       [ok] Banco de dados real acessível (SELECT 1 bem-sucedido).");

// ---- 5. Migrações Alembic (Incremento 2.2, seção 2, item 2) ---------------------------------
Console.WriteLine("[migração] Executando 'alembic upgrade head'...");
var migration = MigrationRunner.Run(venvPython, apiDir);
if (!migration.Ok)
{
    Console.Error.WriteLine();
    Console.Error.WriteLine($"[erro] Migração falhou (exit code {migration.ExitCode}). Saída (sanitizada):");
    Console.Error.WriteLine(Truncate(migration.SanitizedOutput));
    return 1;
}
Console.WriteLine("       [ok] Migrações aplicadas com sucesso.");

// ---- 14. Detectar portas ocupadas ------------------------------------------------------------
var apiPortInUse = PortChecker.IsPortInUse(ApiPort);
var webPortInUse = PortChecker.IsPortInUse(WebPort);
var apiPlan = StartupPlanner.PlanService(new ServicePlanInput("API", ApiPort, apiPortInUse));
var webPlan = StartupPlanner.PlanService(new ServicePlanInput("Frontend", WebPort, webPortInUse));
Console.WriteLine($"[portas] {apiPlan.Message}");
Console.WriteLine($"[portas] {webPlan.Message}");

using var supervisor = new ProcessSupervisor();
var dispatcherManager = new DispatcherManager(supervisor, apiDir, venvPython, dispatcherStatusFile, dispatcherStopFile);
var cts = new CancellationTokenSource();
var dispatcherStartedByUs = false;

Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    Console.WriteLine();
    Console.WriteLine("[encerrando] Ctrl+C recebido -- iniciando encerramento ordenado (frontend -> dispatcher -> API)...");
    OrderedShutdown();
    cts.Cancel();
};
AppDomain.CurrentDomain.ProcessExit += (_, _) => OrderedShutdown();

try
{
    if (apiPlan.Action == ServiceAction.StartNew)
    {
        var apiSecretKey = SecretGenerator.GenerateHex(32);
        Console.WriteLine("[api] API_SECRET_KEY efêmera gerada (não exibida, nunca gravada em disco).");
        Console.WriteLine($"[api] Iniciando API em http://localhost:{ApiPort} (ENVIRONMENT=test)...");
        var apiEnv = new Dictionary<string, string>
        {
            ["ENVIRONMENT"] = "test",
            ["API_SECRET_KEY"] = apiSecretKey,
            ["DATABASE_URL"] = databaseUrl,
        };
        var apiHandle = supervisor.StartTracked(
            "api",
            venvPython,
            ["-m", "uvicorn", "biomatcad_api.main:app", "--host", "127.0.0.1", "--port", ApiPort.ToString()],
            apiDir,
            apiEnv,
            logFilePath: Path.Combine(logsDir, "api.log"),
            sanitizeLine: DatabasePreflight.SanitizeForDisplay);
        Console.WriteLine($"       API iniciada -- PID {apiHandle.ProcessId}");

        Console.WriteLine("[api] Aguardando API ficar pronta...");
        if (!PortChecker.WaitUntilReady(ApiPort, TimeSpan.FromSeconds(60)))
        {
            Console.Error.WriteLine("[erro] API não ficou disponível a tempo. Encerrando processos já iniciados.");
            return 1;
        }
        Console.WriteLine("       [ok] API pronta.");
    }
    else
    {
        Console.WriteLine("[api] Pulando inicialização da API -- porta já em uso (reaproveitando serviço existente).");
    }

    // ---- 6. Dispatcher geométrico contínuo (Incremento 2.2, seção 2, item 4) ----------------
    var (canStartDispatcher, blockingReason) = dispatcherManager.CanStartNewInstance();
    if (!canStartDispatcher)
    {
        Console.WriteLine($"[dispatcher] {blockingReason} Reaproveitando a instância já ativa.");
    }
    else
    {
        Console.WriteLine("[dispatcher] Iniciando dispatcher geométrico contínuo...");
        var dispatcherHandle = dispatcherManager.Start(DispatcherBasePollIntervalSeconds);
        dispatcherStartedByUs = true;
        Console.WriteLine($"       Dispatcher iniciado -- PID {dispatcherHandle.ProcessId}");

        Console.WriteLine("[dispatcher] Aguardando primeiro status file (liveness)...");
        var deadline = DateTime.UtcNow + DispatcherStartupGrace;
        DispatcherStatusSnapshot? status = null;
        while (DateTime.UtcNow < deadline)
        {
            status = dispatcherManager.ReadStatus();
            if (status is not null)
            {
                break;
            }
            if (!supervisor.IsNamedAlive("dispatcher"))
            {
                break;
            }
            Thread.Sleep(300);
        }
        if (status is null)
        {
            Console.Error.WriteLine("[erro] Dispatcher não produziu um status file a tempo -- provável falha de inicialização.");
            return 1;
        }
        Console.WriteLine($"       [ok] Dispatcher vivo (dispatcher_id={status.DispatcherId}).");
    }

    if (webPlan.Action == ServiceAction.StartNew)
    {
        Console.WriteLine("[frontend] Verificando dependências do frontend (node_modules)...");
        var npmResult = EnvironmentSetup.EnsureFrontendDependencies(webDir, npm.ResolvedPath!);
        PrintStep(npmResult);
        if (!npmResult.Ok)
        {
            return 1;
        }

        Console.WriteLine($"[frontend] Iniciando frontend em http://localhost:{WebPort}...");
        var webHandle = supervisor.StartTracked(
            "frontend",
            npm.ResolvedPath!,
            ["run", "dev", "--", "--host", "127.0.0.1", "--port", WebPort.ToString(), "--strictPort"],
            webDir,
            logFilePath: Path.Combine(logsDir, "frontend.log"));
        Console.WriteLine($"       Frontend iniciado -- PID {webHandle.ProcessId}");

        Console.WriteLine("[frontend] Aguardando frontend ficar pronto...");
        if (!PortChecker.WaitUntilReady(WebPort, TimeSpan.FromSeconds(60)))
        {
            Console.Error.WriteLine("[erro] Frontend não ficou disponível a tempo. Encerrando processos já iniciados.");
            return 1;
        }
        Console.WriteLine("       [ok] Frontend pronto.");
    }
    else
    {
        Console.WriteLine("[frontend] Pulando inicialização -- porta já em uso (reaproveitando serviço existente).");
    }

    // ---- 7. Abrir o navegador só agora que tudo está operacional --------------------------
    var loginUrl = $"http://localhost:{WebPort}/login";
    Console.WriteLine($"[navegador] Abrindo {loginUrl}...");
    TryOpenBrowser(loginUrl);

    Console.WriteLine();
    PrintStatusPanel();
    Console.WriteLine();
    Console.WriteLine("Pressione Ctrl+C para encerrar todos os processos filhos e sair.");
    PrintBanner();

    var lastPanelRefresh = DateTime.UtcNow;
    while (!cts.IsCancellationRequested)
    {
        Thread.Sleep(1000);

        // ---- Monitoramento contínuo: detecta encerramento inesperado do dispatcher e tenta
        // reinício controlado (Incremento 2.2, seção 2, item 4: "detectar encerramento
        // inesperado" e "permitir reinício controlado"). Não se aplica se o próprio operador
        // pediu Ctrl+C (cts já estaria cancelado nesse caso, saindo do loop antes desta checagem).
        if (dispatcherStartedByUs)
        {
            var state = dispatcherManager.CurrentState(processStartedAtAll: true);
            if (state == DispatcherState.Failed)
            {
                Console.WriteLine("[dispatcher] [aviso] Encerramento inesperado detectado -- tentando reinício controlado...");
                supervisor.TryKillNamed("dispatcher"); // garante que não sobra nada da instância morta
                try
                {
                    var restarted = dispatcherManager.Start(DispatcherBasePollIntervalSeconds);
                    Console.WriteLine($"       Dispatcher reiniciado -- novo PID {restarted.ProcessId}");
                }
                catch (InvalidOperationException ex)
                {
                    Console.WriteLine($"       [falha] Não foi possível reiniciar o dispatcher: {ex.Message}");
                }
            }
        }

        if ((DateTime.UtcNow - lastPanelRefresh) > TimeSpan.FromSeconds(30))
        {
            PrintStatusPanel();
            lastPanelRefresh = DateTime.UtcNow;
        }
    }
}
finally
{
    OrderedShutdown();
}

return 0;

void OrderedShutdown()
{
    // Incremento 2.2, seção 2, item 6: "Ctrl+C ou fechamento deve encerrar, nesta ordem:
    // frontend -> dispatcher -> API; aguardar shutdown gracioso do dispatcher; matar
    // forçadamente apenas o processo filho específico se exceder timeout; nunca taskkill
    // genérico; não deixar processos órfãos."
    if (supervisor.IsNamedAlive("frontend"))
    {
        Console.WriteLine("[encerrando] Parando frontend...");
        supervisor.TryKillNamed("frontend");
    }

    if (supervisor.IsNamedAlive("dispatcher"))
    {
        Console.WriteLine("[encerrando] Solicitando parada graciosa do dispatcher (aguardando até " +
            $"{DispatcherGracefulShutdownTimeout.TotalSeconds:0}s)...");
        var stoppedGracefully = dispatcherManager.RequestGracefulStopAndWait(DispatcherGracefulShutdownTimeout);
        if (!stoppedGracefully && supervisor.IsNamedAlive("dispatcher"))
        {
            Console.WriteLine("[encerrando] [aviso] Dispatcher não parou graciosamente a tempo -- encerrando à força (somente este processo).");
            supervisor.TryKillNamed("dispatcher");
        }
        else
        {
            Console.WriteLine("[encerrando] Dispatcher parado graciosamente.");
        }
    }

    if (supervisor.IsNamedAlive("api"))
    {
        Console.WriteLine("[encerrando] Parando API...");
        supervisor.TryKillNamed("api");
    }

    // Rede de segurança: garante que absolutamente nenhum processo rastreado sobra, mesmo que
    // algum passo acima tenha sido pulado por causa de uma exceção. Idempotente.
    supervisor.ShutdownAll();
}

void PrintStep(StepResult result) =>
    Console.WriteLine(result.Ok ? $"       [ok] {result.Message}" : $"       [falha] {result.Message}");

void PrintBanner()
{
    Console.WriteLine(new string('=', PermanentBanner.Length + 4));
    Console.WriteLine($"  {PermanentBanner}");
    Console.WriteLine(new string('=', PermanentBanner.Length + 4));
}

void PrintStatusPanel()
{
    // Incremento 2.2, seção 2, item 8 ("interface do launcher"): banco, API, dispatcher,
    // frontend, endereço, diretório de artefatos, diretório de logs -- nunca senha,
    // API_SECRET_KEY, JWT ou DATABASE_URL completa.
    var sanitizedUrl = databaseUrl is not null ? DatabasePreflight.SanitizeForDisplay(databaseUrl) : "(desconhecida)";
    Console.WriteLine("Status:");
    Console.WriteLine($"  Banco:      OK (preflight aprovado; {sanitizedUrl})");
    Console.WriteLine($"  API:        {(supervisor.IsNamedAlive("api") || apiPlan.Action == ServiceAction.ReuseExisting ? "rodando" : "parada")}  -- http://localhost:{ApiPort}");
    Console.WriteLine($"  Dispatcher: {dispatcherManager.CurrentState(processStartedAtAll: true)}");
    Console.WriteLine($"  Frontend:   {(supervisor.IsNamedAlive("frontend") || webPlan.Action == ServiceAction.ReuseExisting ? "rodando" : "parada")}  -- http://localhost:{WebPort}");
    Console.WriteLine($"  Diretório de artefatos: {artifactsDirDefault}");
    Console.WriteLine($"  Diretório de logs:      {logsDir}");
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

static string Truncate(string s, int max = 2000) => s.Length <= max ? s : s[..max] + "... [truncado]";
