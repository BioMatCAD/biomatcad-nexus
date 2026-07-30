using System.Diagnostics;
using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class DispatcherStateResolverTests
{
    private static readonly TimeSpan Staleness = TimeSpan.FromSeconds(30);
    private static readonly DateTimeOffset Now = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

    private static DispatcherStatusSnapshot Snapshot(string state, string phase, DateTimeOffset? lastPoll = null, int pid = 123) =>
        new(DispatcherId: "host:123:abc", Pid: pid, RawState: state, RawPhase: phase, LastPollAt: lastPoll ?? Now, JobsProcessedTotal: 0, CurrentPollIntervalSeconds: 3.0, LastJobId: null);

    [Fact]
    public void SemStatusFile_ProcessoVivo_EhStarting()
    {
        Assert.Equal(DispatcherState.Starting, DispatcherStateResolver.Resolve(processIsAlive: true, status: null, Now, Staleness));
    }

    [Fact]
    public void SemStatusFile_ProcessoMorto_EhFailed()
    {
        Assert.Equal(DispatcherState.Failed, DispatcherStateResolver.Resolve(processIsAlive: false, status: null, Now, Staleness));
    }

    [Fact]
    public void EstadoRunningFaseIdle_ProcessoVivo_EhIdle()
    {
        var status = Snapshot("running", "idle");
        Assert.Equal(DispatcherState.Idle, DispatcherStateResolver.Resolve(true, status, Now, Staleness));
    }

    [Fact]
    public void EstadoRunningFaseProcessing_ProcessoVivo_EhProcessing()
    {
        var status = Snapshot("running", "processing");
        Assert.Equal(DispatcherState.Processing, DispatcherStateResolver.Resolve(true, status, Now, Staleness));
    }

    [Fact]
    public void EstadoRunning_ProcessoMorto_EhFailed_EncerramentoInesperado()
    {
        var status = Snapshot("running", "idle");
        Assert.Equal(DispatcherState.Failed, DispatcherStateResolver.Resolve(processIsAlive: false, status, Now, Staleness));
    }

    [Fact]
    public void EstadoRunning_HeartbeatMuitoAtrasado_EhFailedMesmoComProcessoVivo()
    {
        var status = Snapshot("running", "idle", lastPoll: Now - TimeSpan.FromMinutes(5));
        Assert.Equal(DispatcherState.Failed, DispatcherStateResolver.Resolve(processIsAlive: true, status, Now, Staleness));
    }

    [Fact]
    public void EstadoRunning_HeartbeatDentroDoLimite_NaoEhFailed()
    {
        var status = Snapshot("running", "idle", lastPoll: Now - TimeSpan.FromSeconds(10));
        Assert.NotEqual(DispatcherState.Failed, DispatcherStateResolver.Resolve(processIsAlive: true, status, Now, Staleness));
    }

    [Fact]
    public void EstadoStopped_ProcessoAindaVivo_EhStopping()
    {
        var status = Snapshot("stopped", "idle");
        Assert.Equal(DispatcherState.Stopping, DispatcherStateResolver.Resolve(processIsAlive: true, status, Now, Staleness));
    }

    [Fact]
    public void EstadoStopped_ProcessoJaMorto_EhStopped()
    {
        var status = Snapshot("stopped", "idle");
        Assert.Equal(DispatcherState.Stopped, DispatcherStateResolver.Resolve(processIsAlive: false, status, Now, Staleness));
    }
}

public class DispatcherStatusReaderTests
{
    [Fact]
    public void TryRead_ArquivoAusente_RetornaNullSemLancar()
    {
        Assert.Null(DispatcherStatusReader.TryRead("/caminho/inexistente/status.json"));
    }

    [Fact]
    public void TryRead_JsonMalformado_RetornaNullSemLancar()
    {
        var tmp = Path.GetTempFileName();
        try
        {
            File.WriteAllText(tmp, "{ isto nao e json valido");
            Assert.Null(DispatcherStatusReader.TryRead(tmp));
        }
        finally { File.Delete(tmp); }
    }

    [Fact]
    public void TryRead_JsonValido_ParseiaTodosOsCampos()
    {
        var tmp = Path.GetTempFileName();
        try
        {
            File.WriteAllText(tmp, """
                {
                  "dispatcher_id": "host:99:abcd1234",
                  "pid": 99,
                  "state": "running",
                  "phase": "processing",
                  "started_at": "2026-01-01T00:00:00+00:00",
                  "last_poll_at": "2026-01-01T00:00:05+00:00",
                  "jobs_processed_total": 7,
                  "current_poll_interval_seconds": 4.5,
                  "last_job_id": "job-abc"
                }
                """);
            var snapshot = DispatcherStatusReader.TryRead(tmp);
            Assert.NotNull(snapshot);
            Assert.Equal("host:99:abcd1234", snapshot!.DispatcherId);
            Assert.Equal(99, snapshot.Pid);
            Assert.Equal("running", snapshot.RawState);
            Assert.Equal("processing", snapshot.RawPhase);
            Assert.Equal(7, snapshot.JobsProcessedTotal);
            Assert.Equal(4.5, snapshot.CurrentPollIntervalSeconds);
            Assert.Equal("job-abc", snapshot.LastJobId);
        }
        finally { File.Delete(tmp); }
    }
}

public class DispatcherManagerTests
{
    private static (string FileName, string[] Args) LongRunningCommand(int seconds) =>
        OperatingSystem.IsWindows()
            ? ("cmd.exe", new[] { "/c", "timeout", "/t", seconds.ToString() })
            : ("sleep", new[] { seconds.ToString() });

    [Fact]
    public void CanStartNewInstance_SemStatusFile_PermiteIniciar()
    {
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-dispatcher-test-");
        try
        {
            var manager = new DispatcherManager(supervisor, tmpDir.FullName, "python3",
                Path.Combine(tmpDir.FullName, "status.json"), Path.Combine(tmpDir.FullName, "stop"));

            var (canStart, reason) = manager.CanStartNewInstance();
            Assert.True(canStart);
            Assert.Null(reason);
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void CanStartNewInstance_StatusRunningComPidRealVivo_BloqueiaNovaInstancia()
    {
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-dispatcher-test-");
        try
        {
            // PID real e vivo: o processo de teste atual em execução.
            var realAlivePid = Environment.ProcessId;
            var statusFile = Path.Combine(tmpDir.FullName, "status.json");
            File.WriteAllText(statusFile, $$"""
                {"dispatcher_id":"host:{{realAlivePid}}:aaaa","pid":{{realAlivePid}},"state":"running","phase":"idle",
                 "started_at":"2026-01-01T00:00:00+00:00","last_poll_at":"2026-01-01T00:00:00+00:00",
                 "jobs_processed_total":0,"current_poll_interval_seconds":3.0,"last_job_id":null}
                """);

            var manager = new DispatcherManager(supervisor, tmpDir.FullName, "python3", statusFile, Path.Combine(tmpDir.FullName, "stop"));
            var (canStart, reason) = manager.CanStartNewInstance();

            Assert.False(canStart);
            Assert.Contains("Já existe um dispatcher ativo", reason);
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void CanStartNewInstance_StatusRunningComPidMorto_PermiteIniciarNovaInstancia()
    {
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-dispatcher-test-");
        try
        {
            const int almostCertainlyDeadPid = 999_999; // PID improvável de existir no sandbox de teste
            var statusFile = Path.Combine(tmpDir.FullName, "status.json");
            File.WriteAllText(statusFile, $$"""
                {"dispatcher_id":"host:{{almostCertainlyDeadPid}}:aaaa","pid":{{almostCertainlyDeadPid}},"state":"running","phase":"idle",
                 "started_at":"2026-01-01T00:00:00+00:00","last_poll_at":"2026-01-01T00:00:00+00:00",
                 "jobs_processed_total":0,"current_poll_interval_seconds":3.0,"last_job_id":null}
                """);

            var manager = new DispatcherManager(supervisor, tmpDir.FullName, "python3", statusFile, Path.Combine(tmpDir.FullName, "stop"));
            var (canStart, _) = manager.CanStartNewInstance();

            Assert.True(canStart, "um status 'running' com PID morto (órfão de execução anterior) não deve bloquear um novo dispatcher");
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void RequestGracefulStopAndWait_ProcessoRespondeAoStopFile_RetornaTrueDentroDoTimeout()
    {
        // Processo real que simula o comportamento do dispatcher: fica vivo até o stop_file
        // aparecer, então escreve state=stopped no status file e sai -- prova o mecanismo real
        // de arquivo sentinela ponta a ponta (não apenas em memória), com um processo do SO de
        // verdade, sem precisar do dispatcher Python completo.
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-dispatcher-test-");
        try
        {
            var statusFile = Path.Combine(tmpDir.FullName, "status.json");
            var stopFile = Path.Combine(tmpDir.FullName, "stop");
            var manager = new DispatcherManager(supervisor, tmpDir.FullName, "python3", statusFile, stopFile);

            var fakeDispatcherScript =
                "import time, json, os, sys\n" +
                $"stop_file = r'{stopFile}'\n" +
                $"status_file = r'{statusFile}'\n" +
                "for _ in range(200):\n" +
                "    if os.path.exists(stop_file):\n" +
                "        break\n" +
                "    time.sleep(0.05)\n" +
                "with open(status_file, 'w') as f:\n" +
                "    json.dump({'dispatcher_id':'fake','pid':os.getpid(),'state':'stopped','phase':'idle'," +
                "'started_at':'x','last_poll_at':'x','jobs_processed_total':0,'current_poll_interval_seconds':3.0,'last_job_id':None}, f)\n";

            var handle = supervisor.StartTracked("dispatcher", "python3", ["-c", fakeDispatcherScript], tmpDir.FullName);
            Assert.True(handle.ProcessId > 0);

            var stoppedGracefully = manager.RequestGracefulStopAndWait(TimeSpan.FromSeconds(10));
            Assert.True(stoppedGracefully);

            var finalStatus = manager.ReadStatus();
            Assert.NotNull(finalStatus);
            Assert.Equal("stopped", finalStatus!.RawState);
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void Start_RemoveStatusFileObsoletoAntesDeIniciar_EvitandoFalsoPositivoDeLiveness()
    {
        // Regressao real: encontrada rodando o launcher de ponta a ponta em sandbox. Sem esta
        // limpeza, um status.json deixado por uma execucao anterior do dispatcher (de outro PID,
        // possivelmente ja morto) era lido pelo laco de espera em Program.cs como se fosse a prova
        // de liveness do dispatcher recem-iniciado -- ou seja, o gate podia "passar" reportando o
        // dispatcher_id/PID de um processo antigo, sem nunca observar o processo novo escrever nada.
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-dispatcher-test-");
        try
        {
            var statusFile = Path.Combine(tmpDir.FullName, "status.json");
            var stopFile = Path.Combine(tmpDir.FullName, "stop");

            File.WriteAllText(statusFile, """
                {"dispatcher_id":"host:999999:stale","pid":999999,"state":"running","phase":"idle",
                 "started_at":"2020-01-01T00:00:00+00:00","last_poll_at":"2020-01-01T00:00:00+00:00",
                 "jobs_processed_total":0,"current_poll_interval_seconds":3.0,"last_job_id":null}
                """);
            Assert.True(File.Exists(statusFile));

            var manager = new DispatcherManager(supervisor, tmpDir.FullName, "python3", statusFile, stopFile);

            // Start() aponta para scripts/geometry_dispatcher.py dentro de tmpDir, que nao existe
            // -- o processo python provavelmente falhara ao iniciar, mas isso e irrelevante aqui:
            // testamos apenas o efeito colateral sincrono (remocao do status.json obsoleto), que
            // deve acontecer antes de qualquer tentativa de spawnar o processo.
            manager.Start(basePollIntervalSeconds: 3.0);

            Assert.False(File.Exists(statusFile));

            supervisor.TryKillNamed("dispatcher"); // limpeza, caso algo tenha chegado a iniciar
        }
        finally { tmpDir.Delete(recursive: true); }
    }


    [Fact]
    public void RequestGracefulStopAndWait_ProcessoNuncaResponde_RetornaFalseAposTimeoutCurto()
    {
        using var supervisor = new ProcessSupervisor();
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-dispatcher-test-");
        try
        {
            var statusFile = Path.Combine(tmpDir.FullName, "status.json");
            var stopFile = Path.Combine(tmpDir.FullName, "stop");
            var manager = new DispatcherManager(supervisor, tmpDir.FullName, "python3", statusFile, stopFile);

            var (fileName, args) = LongRunningCommand(30); // nunca olha para o stop_file
            supervisor.StartTracked("dispatcher", fileName, args, tmpDir.FullName);

            var stoppedGracefully = manager.RequestGracefulStopAndWait(TimeSpan.FromMilliseconds(500));
            Assert.False(stoppedGracefully);

            supervisor.TryKillNamed("dispatcher"); // limpeza -- prova também que o kill forçado funciona depois
        }
        finally { tmpDir.Delete(recursive: true); }
    }
}
