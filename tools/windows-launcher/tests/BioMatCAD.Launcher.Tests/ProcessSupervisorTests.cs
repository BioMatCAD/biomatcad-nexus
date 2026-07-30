using System.Diagnostics;
using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class ProcessSupervisorTests
{
    // Comando real de longa duração, usado apenas para os testes de supervisão de processos
    // (nunca toca a API/frontend reais) -- prova o encerramento de filhos com um PROCESSO REAL
    // do sistema operacional, não uma simulação em memória. Bug real corrigido nesta rodada: a
    // versão anterior usava "cmd.exe /c timeout /t N" no Windows, que falha de forma
    // intermitente/imediata quando executado sem um console real anexado (stdin redirecionado
    // ou CreateNoWindow) com "ERROR: Input redirection is not supported" -- exatamente o tipo
    // de falha relatada como "isolamento/temporização" na validação real no Windows. Substituído
    // pelo processo auxiliar multiplataforma controlado (TestHelperProcess via
    // TestHelperProcessLocator), que apenas dorme via Thread.Sleep -- sem nenhuma dependência de
    // console, shell ou sinal específico de SO.
    private static (string FileName, string[] Args) LongRunningCommand(int seconds) =>
        TestHelperProcessLocator.Command("sleep", seconds.ToString());

    private static bool IsProcessAlive(int pid)
    {
        try
        {
            var p = Process.GetProcessById(pid);
            return !p.HasExited;
        }
        catch (ArgumentException)
        {
            return false; // PID não existe mais
        }
    }

    [Fact]
    public void StartTracked_IniciaProcessoRealEExpoeSeuPid()
    {
        using var supervisor = new ProcessSupervisor();
        var (fileName, args) = LongRunningCommand(30);
        var handle = supervisor.StartTracked("dummy-long-lived", fileName, args, Directory.GetCurrentDirectory());

        Assert.True(handle.ProcessId > 0);
        Assert.True(IsProcessAlive(handle.ProcessId));

        supervisor.ShutdownAll();
    }

    [Fact]
    public void ShutdownAll_EncerraApenasOsProcessosRealmenteRastreados()
    {
        // "encerramento dos filhos": inicia dois processos reais rastreados pelo supervisor e
        // um terceiro processo real NÃO rastreado (iniciado fora do supervisor) -- Shutdown
        // deve matar SOMENTE os dois rastreados, nunca o terceiro. Prova que o mecanismo é
        // "matar só o que eu iniciei", nunca um taskkill genérico por nome/porta.
        using var supervisor = new ProcessSupervisor();
        var (fileName, args) = LongRunningCommand(30);

        var trackedA = supervisor.StartTracked("tracked-a", fileName, args, Directory.GetCurrentDirectory());
        var trackedB = supervisor.StartTracked("tracked-b", fileName, args, Directory.GetCurrentDirectory());

        var untrackedPsi = new ProcessStartInfo { FileName = fileName, UseShellExecute = false };
        foreach (var a in args) untrackedPsi.ArgumentList.Add(a);
        using var untrackedProcess = Process.Start(untrackedPsi)!;

        try
        {
            Assert.True(IsProcessAlive(trackedA.ProcessId));
            Assert.True(IsProcessAlive(trackedB.ProcessId));
            Assert.True(IsProcessAlive(untrackedProcess.Id));

            supervisor.ShutdownAll();
            Thread.Sleep(500);

            Assert.False(IsProcessAlive(trackedA.ProcessId));
            Assert.False(IsProcessAlive(trackedB.ProcessId));
            Assert.True(IsProcessAlive(untrackedProcess.Id), "Processo não rastreado não deveria ter sido afetado.");
        }
        finally
        {
            if (!untrackedProcess.HasExited)
            {
                untrackedProcess.Kill(entireProcessTree: true);
            }
        }
    }

    [Fact]
    public void ShutdownAll_ComInicioParcial_EncerraSomenteOQueChegouASerIniciado()
    {
        // "início parcial": simula o cenário em que o serviço A foi iniciado com sucesso, mas
        // um erro ocorreu ANTES de iniciar o serviço B (ex.: npm install falhou). O bloco
        // finally do Program.cs chama supervisor.ShutdownAll() de qualquer forma -- este teste
        // prova que isso é seguro mesmo quando só um processo chegou a ser criado.
        using var supervisor = new ProcessSupervisor();
        var (fileName, args) = LongRunningCommand(30);

        var onlyServiceStarted = supervisor.StartTracked("only-service", fileName, args, Directory.GetCurrentDirectory());
        Assert.True(IsProcessAlive(onlyServiceStarted.ProcessId));

        // Simula a falha ao iniciar o segundo serviço -- nenhuma chamada a StartTracked para
        // "B" acontece, exatamente como no fluxo real quando EnsureFrontendDependencies falha.

        supervisor.ShutdownAll();
        Thread.Sleep(500);

        Assert.False(IsProcessAlive(onlyServiceStarted.ProcessId));
        Assert.Empty(supervisor.Children);
    }

    [Fact]
    public void RunToCompletion_ExecutaComandoCurtoEReturnaExitCodeEOutput()
    {
        var (fileName, args) = OperatingSystem.IsWindows()
            ? ("cmd.exe", new[] { "/c", "echo", "ok-biomatcad" })
            : ("echo", new[] { "ok-biomatcad" });

        var (exitCode, output) = ProcessSupervisor.RunToCompletion(fileName, args, Directory.GetCurrentDirectory());

        Assert.Equal(0, exitCode);
        Assert.Contains("ok-biomatcad", output);
    }

    [Fact]
    public void StartTracked_PassaVariaveisDeAmbienteParaOProcessoFilho()
    {
        // Prova que ENVIRONMENT=test e o segredo efêmero realmente chegam ao processo filho
        // via variável de ambiente (e não via argumento de linha de comando, que apareceria em
        // listagens de processo do SO -- outra razão pela qual usamos env vars para o segredo).
        //
        // Bug real corrigido nesta rodada: a versão anterior montava a string do comando via
        // "cmd.exe /c \"echo %VAR% > arquivo\"" (Windows) / "sh -c 'echo \"$VAR\" > arquivo'"
        // (Linux) -- expansão de variável e redirecionamento dependiam da sintaxe exata de cada
        // shell sendo reinterpretada corretamente, um ponto de fragilidade real relatado como
        // falha de "propagação de ambiente" na validação no Windows. Substituído pelo processo
        // auxiliar multiplataforma (TestHelperProcess), que lê a variável de ambiente
        // diretamente via API gerenciada (Environment.GetEnvironmentVariable) e grava o arquivo
        // sem NENHUMA interpretação de shell/redirecionamento em nenhum dos dois SOs.
        var outputFile = Path.Combine(Path.GetTempPath(), $"biomatcad-env-test-{Guid.NewGuid():N}.txt");
        try
        {
            using var supervisor = new ProcessSupervisor();
            var (fileName, args) = TestHelperProcessLocator.Command("echo-env", "MEU_TESTE_ENV", outputFile);

            var handle = supervisor.StartTracked(
                "env-echo",
                fileName,
                args,
                Directory.GetCurrentDirectory(),
                new Dictionary<string, string> { ["MEU_TESTE_ENV"] = "valor-secreto-de-teste" });

            for (var i = 0; i < 50 && !File.Exists(outputFile); i++)
            {
                Thread.Sleep(100);
            }

            Assert.True(File.Exists(outputFile));
            var content = File.ReadAllText(outputFile);
            Assert.Contains("valor-secreto-de-teste", content);
        }
        finally
        {
            if (File.Exists(outputFile)) File.Delete(outputFile);
        }
    }
}

public class ProcessSupervisorNamedControlTests
{
    private static (string FileName, string[] Args) LongRunningCommand(int seconds) =>
        TestHelperProcessLocator.Command("sleep", seconds.ToString());

    private static bool IsProcessAlive(int pid)
    {
        try { return !Process.GetProcessById(pid).HasExited; }
        catch (ArgumentException) { return false; }
    }

    [Fact]
    public void TryKillNamed_EncerraSomenteOProcessoComEsseNome()
    {
        // Incremento 2.2, seção 2 (encerramento ordenado frontend->dispatcher->API): prova que
        // matar "frontend" por nome não afeta um "api" também rastreado -- essencial para o
        // encerramento em ordem específica, diferente de ShutdownAll (que mata tudo de uma vez).
        using var supervisor = new ProcessSupervisor();
        var (fileName, args) = LongRunningCommand(30);

        var api = supervisor.StartTracked("api", fileName, args, Directory.GetCurrentDirectory());
        var frontend = supervisor.StartTracked("frontend", fileName, args, Directory.GetCurrentDirectory());

        var killed = supervisor.TryKillNamed("frontend");
        Thread.Sleep(400);

        Assert.True(killed);
        Assert.False(IsProcessAlive(frontend.ProcessId));
        Assert.True(IsProcessAlive(api.ProcessId), "matar 'frontend' não deveria afetar 'api'");

        supervisor.ShutdownAll();
    }

    [Fact]
    public void TryKillNamed_SemProcessoComEsseNome_RetornaFalseSemLancar()
    {
        using var supervisor = new ProcessSupervisor();
        Assert.False(supervisor.TryKillNamed("nome-que-nao-existe"));
    }

    [Fact]
    public void IsNamedAlive_RefleteEstadoRealDoProcesso()
    {
        using var supervisor = new ProcessSupervisor();
        var (fileName, args) = LongRunningCommand(30);
        supervisor.StartTracked("dispatcher", fileName, args, Directory.GetCurrentDirectory());

        Assert.True(supervisor.IsNamedAlive("dispatcher"));
        supervisor.TryKillNamed("dispatcher");
        Thread.Sleep(400);
        Assert.False(supervisor.IsNamedAlive("dispatcher"));
    }

    [Fact]
    public void StartTracked_ComLogFilePath_DrenaStdoutEStderrSanitizadosParaOArquivo()
    {
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-log-test-");
        try
        {
            var logFile = Path.Combine(tmpDir.FullName, "child.log");

            // Bug real corrigido nesta rodada: a versão anterior invocava "python"/"python3"
            // diretamente para imprimir as linhas de teste -- substituído pelo processo auxiliar
            // multiplataforma (modo "log-lines"), eliminando a dependência de Python instalado.
            static string Sanitize(string line) => line.Replace("segredo123", "***");
            var (fileName, args) = TestHelperProcessLocator.Command("log-lines");

            supervisor.StartTracked(
                "logger-test", fileName, args, Directory.GetCurrentDirectory(),
                logFilePath: logFile, sanitizeLine: Sanitize);

            // A entrega das últimas linhas via OutputDataReceived/ErrorDataReceived é
            // assíncrona e pode continuar chegando por um curto período MESMO DEPOIS que
            // Process.HasExited já é true (o SO ainda está entregando os buffers pendentes ao
            // .NET) -- por isso o teste espera pelo CONTEÚDO esperado aparecer, com um timeout
            // generoso, em vez de um sleep fixo após checar apenas a saída do processo.
            var content = "";
            for (var i = 0; i < 100; i++)
            {
                if (File.Exists(logFile))
                {
                    content = File.ReadAllText(logFile);
                    if (content.Contains("linha stdout") && content.Contains("linha stderr"))
                    {
                        break;
                    }
                }
                Thread.Sleep(100);
            }

            Assert.Contains("linha stdout", content);
            Assert.Contains("linha stderr", content);
            Assert.DoesNotContain("segredo123", content);
            Assert.Contains("***", content);
        }
        finally
        {
            // Bug real corrigido nesta rodada (relatado pelo usuário): chamar apenas
            // ShutdownAll() mata o processo filho mas NÃO fecha o StreamWriter do arquivo de
            // log -- no Windows (ao contrário do Linux), um handle de arquivo ainda aberto
            // impede Directory.Delete(recursive: true) de apagar o diretório temporário
            // ("o processo não pode acessar o arquivo porque ele está sendo usado por outro
            // processo"). Dispose() fecha o LogWriter (além de matar os processos), então
            // precisa ser chamado ANTES de tentar apagar o diretório temporário.
            supervisor.Dispose();
            tmpDir.Delete(recursive: true);
        }
    }

    [Fact]
    public void Dispose_FechaOArquivoDeLogPermitindoApagarODiretorioLogoEmSeguida()
    {
        // Regressão dedicada ao bug real relatado ("StartTracked_ComLogFilePath deixa child.log
        // aberto durante a remoção do diretório temporário"): prova, isoladamente, que depois de
        // Dispose() o arquivo de log pode ser apagado imediatamente, sem exceção -- a garantia
        // exata que falhava no Windows real.
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-log-dispose-test-");
        try
        {
            var logFile = Path.Combine(tmpDir.FullName, "child.log");
            var supervisor = new ProcessSupervisor();
            var (fileName, args) = TestHelperProcessLocator.Command("log-lines");
            supervisor.StartTracked("logger-test", fileName, args, Directory.GetCurrentDirectory(), logFilePath: logFile);

            for (var i = 0; i < 100 && !File.Exists(logFile); i++)
            {
                Thread.Sleep(50);
            }
            Assert.True(File.Exists(logFile));

            supervisor.Dispose();

            // Se o LogWriter ainda estivesse aberto, isto lançaria IOException no Windows
            // (em Linux não lançaria de qualquer forma -- por isso o bug só apareceu na
            // validação real no Windows do usuário, nunca neste sandbox).
            var exception = Record.Exception(() => File.Delete(logFile));
            Assert.Null(exception);
        }
        finally
        {
            tmpDir.Delete(recursive: true);
        }
    }

    private static bool Process_HasExitedSafely(int pid)
    {
        try { return Process.GetProcessById(pid).HasExited; }
        catch (ArgumentException) { return true; }
    }

    [Fact]
    public void ShutdownAll_NuncaAfetaProcessosRastreadosPorOutraInstanciaDoSupervisor()
    {
        // Regressão dedicada de isolamento (item explicitamente pedido pelo usuário): duas
        // instâncias INDEPENDENTES de ProcessSupervisor (como aconteceria, por exemplo, se um
        // teste e o launcher real coexistissem, ou entre diferentes execuções) nunca devem se
        // afetar -- Dispose/ShutdownAll de uma nunca pode matar um processo rastreado pela
        // outra, reforçando (de forma mais direta que o teste com um processo solto fora de
        // qualquer supervisor) que o rastreamento é por INSTÂNCIA, não global.
        using var supervisorA = new ProcessSupervisor();
        using var supervisorB = new ProcessSupervisor();
        var (fileName, args) = LongRunningCommand(30);

        var trackedByA = supervisorA.StartTracked("proc-a", fileName, args, Directory.GetCurrentDirectory());
        var trackedByB = supervisorB.StartTracked("proc-b", fileName, args, Directory.GetCurrentDirectory());

        Assert.True(IsProcessAlive(trackedByA.ProcessId));
        Assert.True(IsProcessAlive(trackedByB.ProcessId));

        supervisorA.ShutdownAll();
        Thread.Sleep(500);

        Assert.False(IsProcessAlive(trackedByA.ProcessId));
        Assert.True(IsProcessAlive(trackedByB.ProcessId), "ShutdownAll de um supervisor não deveria afetar processos rastreados por outra instância");

        supervisorB.ShutdownAll();
    }
}
