using System.Diagnostics;
using System.Text.Json;

namespace BioMatCAD.Launcher;

/// <summary>Estados exibidos ao usuário (Incremento 2.2, seção 2, item 4).</summary>
public enum DispatcherState
{
    Starting,
    Idle,
    Processing,
    Stopping,
    Stopped,
    Failed,
}

public sealed record DispatcherStatusSnapshot(
    string? DispatcherId,
    int? Pid,
    string RawState,
    string RawPhase,
    DateTimeOffset? LastPollAt,
    long JobsProcessedTotal,
    double CurrentPollIntervalSeconds,
    string? LastJobId);

/// <summary>
/// Leitura pura e tolerante a falhas do status.json escrito por
/// scripts/geometry_dispatcher.py (Incremento 2.2, seção 3). Nunca lança: um arquivo ausente,
/// vazio ou parcialmente escrito (ver escrita atômica no lado Python -- isso não deveria
/// acontecer, mas o leitor é defensivo mesmo assim) resulta em `null`, não em exceção.
/// </summary>
public static class DispatcherStatusReader
{
    public static DispatcherStatusSnapshot? TryRead(string statusFilePath)
    {
        try
        {
            if (!File.Exists(statusFilePath))
            {
                return null;
            }
            var json = File.ReadAllText(statusFilePath);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            string? dispatcherId = root.TryGetProperty("dispatcher_id", out var d) ? d.GetString() : null;
            int? pid = root.TryGetProperty("pid", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetInt32() : null;
            var state = root.TryGetProperty("state", out var s) ? s.GetString() ?? "" : "";
            var phase = root.TryGetProperty("phase", out var ph) ? ph.GetString() ?? "idle" : "idle";
            DateTimeOffset? lastPoll = root.TryGetProperty("last_poll_at", out var lp) && DateTimeOffset.TryParse(lp.GetString(), out var parsed)
                ? parsed
                : null;
            long jobsTotal = root.TryGetProperty("jobs_processed_total", out var jt) && jt.ValueKind == JsonValueKind.Number ? jt.GetInt64() : 0;
            double pollInterval = root.TryGetProperty("current_poll_interval_seconds", out var pi) && pi.ValueKind == JsonValueKind.Number ? pi.GetDouble() : 0.0;
            string? lastJobId = root.TryGetProperty("last_job_id", out var lj) && lj.ValueKind == JsonValueKind.String ? lj.GetString() : null;

            return new DispatcherStatusSnapshot(dispatcherId, pid, state, phase, lastPoll, jobsTotal, pollInterval, lastJobId);
        }
        catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
        {
            // Leitura no meio de uma escrita atômica (raro, mas o rename pode coincidir com a
            // leitura em sistemas de arquivos de rede) -- trata como "ainda não sei", não como
            // erro fatal do launcher.
            return null;
        }
    }
}

/// <summary>
/// Lógica PURA (sem I/O) para decidir o estado exibido do dispatcher a partir de um snapshot
/// de status e do que sabemos sobre o processo do SO -- testável com dados sintéticos, sem
/// precisar rodar um dispatcher de verdade (mesmo padrão de StartupPlanner).
/// </summary>
public static class DispatcherStateResolver
{
    public static DispatcherState Resolve(
        bool processIsAlive,
        DispatcherStatusSnapshot? status,
        DateTimeOffset now,
        TimeSpan stalenessThreshold)
    {
        if (status is null)
        {
            // Processo iniciado mas ainda não escreveu seu primeiro status file -- comum logo
            // após o Start() (import do Python, conexão inicial ao banco). Se o processo já
            // nem está mais vivo e nunca chegou a escrever nada, algo falhou na inicialização.
            return processIsAlive ? DispatcherState.Starting : DispatcherState.Failed;
        }

        if (status.RawState == "stopped")
        {
            // Escreveu "stopped" mas o SO ainda não confirmou a saída do processo -- janela
            // curta entre write_status_file(state="stopped") e o retorno de main(). Fora essa
            // janela, o processo real já terá saído.
            return processIsAlive ? DispatcherState.Stopping : DispatcherState.Stopped;
        }

        // status.RawState == "running" a partir daqui.
        if (!processIsAlive)
        {
            // Disse "running" mas o processo do SO já não existe -- morreu sem completar o
            // shutdown gracioso (crash, kill externo, etc.). É exatamente o que a seção 2 pede
            // para detectar como "encerramento inesperado".
            return DispatcherState.Failed;
        }

        if (status.LastPollAt is DateTimeOffset lastPoll && (now - lastPoll) > stalenessThreshold)
        {
            // Processo vivo mas parou de atualizar o heartbeat do status file há mais tempo do
            // que o esperado -- travado (ex.: preso numa chamada bloqueante ao worker que nunca
            // retorna). Reportado como Failed para o operador investigar, mesmo o processo do
            // SO ainda existindo.
            return DispatcherState.Failed;
        }

        return status.RawPhase == "processing" ? DispatcherState.Processing : DispatcherState.Idle;
    }
}

/// <summary>
/// Orquestra o processo do dispatcher contínuo: inicia, verifica se já existe uma instância
/// ativa antes de iniciar outra (seção 2, item 4: "não executar dois dispatchers
/// acidentalmente"), permite pedir um shutdown gracioso com timeout (via o stop_file --
/// funciona em qualquer SO, inclusive Windows sem console compartilhado -- ver
/// scripts/geometry_dispatcher.py) e expõe o estado atual traduzido para
/// <see cref="DispatcherState"/>.
/// </summary>
public sealed class DispatcherManager
{
    private readonly ProcessSupervisor _supervisor;
    private readonly string _apiDir;
    private readonly string _venvPythonPath;
    private readonly string _statusFilePath;
    private readonly string _stopFilePath;
    private readonly TimeSpan _stalenessThreshold;

    public DispatcherManager(
        ProcessSupervisor supervisor,
        string apiDir,
        string venvPythonPath,
        string statusFilePath,
        string stopFilePath,
        TimeSpan? stalenessThreshold = null)
    {
        _supervisor = supervisor;
        _apiDir = apiDir;
        _venvPythonPath = venvPythonPath;
        _statusFilePath = statusFilePath;
        _stopFilePath = stopFilePath;
        _stalenessThreshold = stalenessThreshold ?? TimeSpan.FromSeconds(30);
    }

    public DispatcherStatusSnapshot? ReadStatus() => DispatcherStatusReader.TryRead(_statusFilePath);

    public static bool IsProcessAlive(int pid)
    {
        try
        {
            using var p = Process.GetProcessById(pid);
            return !p.HasExited;
        }
        catch (Exception ex) when (ex is ArgumentException or InvalidOperationException)
        {
            return false;
        }
    }

    /// <summary>
    /// Verifica, ANTES de iniciar um novo processo, se um status file pré-existente indica um
    /// dispatcher já ativo de verdade (estado "running" E o PID gravado corresponde a um
    /// processo do SO que realmente ainda existe). Um status file "running" com um PID morto é
    /// tratado como órfão de uma execução anterior que terminou sem escrever "stopped" (ex.:
    /// processo morto à força) -- seguro iniciar um novo dispatcher nesse caso (jobs que ele
    /// tinha reivindicado serão recuperados por recover_orphaned_jobs()).
    /// </summary>
    public (bool CanStart, string? BlockingReason) CanStartNewInstance()
    {
        var status = ReadStatus();
        if (status is null || status.RawState != "running")
        {
            return (true, null);
        }
        if (status.Pid is int pid && IsProcessAlive(pid))
        {
            return (
                false,
                $"Já existe um dispatcher ativo (dispatcher_id={status.DispatcherId}, PID {pid}). " +
                "O launcher não vai iniciar uma segunda instância.");
        }
        return (true, null);
    }

    public ManagedProcessHandle Start(double basePollIntervalSeconds = 5.0)
    {
        if (File.Exists(_stopFilePath))
        {
            File.Delete(_stopFilePath);
        }
        // Remove qualquer status.json remanescente de uma execução anterior do dispatcher.
        // Sem isto, o gate de liveness em Program.cs ("aguardar primeiro status file") pode
        // encontrar um arquivo obsoleto (de um PID diferente, possivelmente já morto) e
        // considerar erroneamente que o dispatcher recém-iniciado já está vivo -- um bug real
        // encontrado e comprovado em teste de sandbox: o status stale reportava um
        // dispatcher_id de um processo antigo enquanto o processo recém-criado tinha outro PID.
        if (File.Exists(_statusFilePath))
        {
            File.Delete(_statusFilePath);
        }
        return _supervisor.StartTracked(
            "dispatcher",
            _venvPythonPath,
            [
                "scripts/geometry_dispatcher.py",
                "--poll-interval", basePollIntervalSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture),
                "--status-file", _statusFilePath,
                "--stop-file", _stopFilePath,
            ],
            _apiDir);
    }

    /// <summary>
    /// Pede shutdown gracioso (cria o stop_file) e aguarda até `timeout` que o status file
    /// reflita state=stopped OU que o processo do SO tenha saído sozinho. Retorna true se o
    /// shutdown gracioso foi confirmado dentro do timeout; false se estourou o timeout (o
    /// chamador deve então decidir se força o encerramento via
    /// <see cref="ProcessSupervisor.TryKillNamed"/>).
    /// </summary>
    public bool RequestGracefulStopAndWait(TimeSpan timeout)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_stopFilePath) ?? ".");
        File.WriteAllText(_stopFilePath, "stop-requested-by-launcher");

        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            var status = ReadStatus();
            if (status is not null && status.RawState == "stopped")
            {
                return true;
            }
            if (!_supervisor.IsNamedAlive("dispatcher"))
            {
                return true;
            }
            Thread.Sleep(200);
        }
        return false;
    }

    public DispatcherState CurrentState(bool processStartedAtAll)
    {
        var isAlive = processStartedAtAll && _supervisor.IsNamedAlive("dispatcher");
        var status = ReadStatus();
        return DispatcherStateResolver.Resolve(isAlive, status, DateTimeOffset.UtcNow, _stalenessThreshold);
    }
}
