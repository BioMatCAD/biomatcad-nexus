using System.Diagnostics;
using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class ProcessSupervisorTests
{
    // Comando real de longa duração, escolhido por plataforma, usado apenas para os testes de
    // supervisão de processos (nunca toca a API/frontend reais) -- prova o encerramento de
    // filhos com um PROCESSO REAL do sistema operacional, não uma simulação em memória.
    private static (string FileName, string[] Args) LongRunningCommand(int seconds) =>
        OperatingSystem.IsWindows()
            ? ("cmd.exe", new[] { "/c", "timeout", "/t", seconds.ToString() })
            : ("sleep", new[] { seconds.ToString() });

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
        var outputFile = Path.Combine(Path.GetTempPath(), $"biomatcad-env-test-{Guid.NewGuid():N}.txt");
        try
        {
            using var supervisor = new ProcessSupervisor();
            var (fileName, args) = OperatingSystem.IsWindows()
                ? ("cmd.exe", new[] { "/c", $"echo %MEU_TESTE_ENV% > \"{outputFile}\"" })
                : ("sh", new[] { "-c", $"echo \"$MEU_TESTE_ENV\" > '{outputFile}'" });

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
