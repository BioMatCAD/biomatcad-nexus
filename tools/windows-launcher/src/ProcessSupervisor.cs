using System.Diagnostics;

namespace BioMatCAD.Launcher;

public sealed record ManagedProcessHandle(string Name, int ProcessId);

/// <summary>
/// Inicia e supervisiona processos filhos de longa duração (API, frontend, e utilitários como
/// "pip install"/"npm install"), rastreando cada um por referência de objeto para que o
/// encerramento (Shutdown/Dispose) mate SOMENTE os processos que o próprio launcher iniciou --
/// nunca um "taskkill genérico" por nome/porta, que poderia atingir processos de outro programa.
///
/// Toda invocação usa ProcessStartInfo.ArgumentList (nunca Arguments concatenado como string) e
/// UseShellExecute=false, exceto a abertura do navegador (ver ConsoleUi/LauncherOrchestrator),
/// que usa UseShellExecute=true apenas para abrir uma URL fixa e interna, sem input externo.
/// </summary>
public sealed class ProcessSupervisor : IDisposable
{
    private sealed class TrackedChild
    {
        public required string Name { get; init; }
        public required Process Process { get; init; }
        public StreamWriter? LogWriter { get; init; }
    }

    private readonly List<TrackedChild> _children = new();
    private readonly object _lock = new();

    public IReadOnlyList<ManagedProcessHandle> Children
    {
        get
        {
            lock (_lock)
            {
                return _children
                    .Where(c => !SafeHasExited(c.Process))
                    .Select(c => new ManagedProcessHandle(c.Name, c.Process.Id))
                    .ToList();
            }
        }
    }

    /// <summary>
    /// Inicia um processo de longa duração (ex.: uvicorn, vite dev server, dispatcher contínuo)
    /// e passa a rastreá-lo. <paramref name="environmentOverrides"/> é aplicado por cima do
    /// ambiente herdado -- é assim que ENVIRONMENT=test e API_SECRET_KEY chegam ao processo da
    /// API sem nunca tocar disco.
    ///
    /// Se <paramref name="logFilePath"/> for fornecido, stdout/stderr são drenados
    /// assincronamente (via OutputDataReceived/ErrorDataReceived + BeginOutputReadLine) para
    /// esse arquivo, linha a linha, passando cada linha por <paramref name="sanitizeLine"/>
    /// antes de gravar (nunca grava segredos em disco). A drenagem assíncrona também evita um
    /// problema real e conhecido de processos de longa duração com RedirectStandardOutput=true:
    /// se ninguém lê os pipes, o buffer do SO enche e o processo filho trava ao tentar escrever
    /// mais saída (Incremento 2.2, seção 2, item 3: "capturar logs sanitizados" da API --
    /// e, por extensão, de qualquer processo de longa duração).
    /// </summary>
    public ManagedProcessHandle StartTracked(
        string name,
        string fileName,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        IReadOnlyDictionary<string, string>? environmentOverrides = null,
        string? logFilePath = null,
        Func<string, string>? sanitizeLine = null)
    {
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8,
            StandardErrorEncoding = System.Text.Encoding.UTF8,
        };
        foreach (var arg in arguments)
        {
            psi.ArgumentList.Add(arg);
        }
        // PYTHONUTF8/PYTHONIOENCODING garantem que processos Python filhos (API, dispatcher,
        // migrações) escrevam UTF-8 em stdout/stderr independentemente do codepage herdado do
        // console do Windows -- mesma correção já aplicada em scripts/Run-FinalGate.ps1
        // (Incremento 2.1.1) para o mojibake observado no Windows do usuário. Aplicado aqui
        // incondicionalmente (não é ruim para processos não-Python, que simplesmente ignoram
        // variáveis de ambiente que não leem).
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        if (environmentOverrides is not null)
        {
            foreach (var (key, value) in environmentOverrides)
            {
                psi.Environment[key] = value;
            }
        }

        var process = new Process { StartInfo = psi, EnableRaisingEvents = true };

        StreamWriter? logWriter = null;
        if (logFilePath is not null)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(logFilePath) ?? ".");
            logWriter = new StreamWriter(logFilePath, append: false, System.Text.Encoding.UTF8) { AutoFlush = true };

            void OnLine(object sender, DataReceivedEventArgs e)
            {
                if (e.Data is null)
                {
                    return;
                }
                var line = sanitizeLine is not null ? sanitizeLine(e.Data) : e.Data;
                try
                {
                    logWriter.WriteLine(line);
                }
                catch (ObjectDisposedException)
                {
                    // Escritor já foi fechado (processo encerrado e supervisor descartado) --
                    // linha tardia, sem problema descartá-la.
                }
            }

            process.OutputDataReceived += OnLine;
            process.ErrorDataReceived += OnLine;
        }

        if (!process.Start())
        {
            logWriter?.Dispose();
            throw new InvalidOperationException($"Falha ao iniciar processo '{name}' ({fileName}).");
        }

        if (logWriter is not null)
        {
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
        }

        lock (_lock)
        {
            _children.Add(new TrackedChild { Name = name, Process = process, LogWriter = logWriter });
        }

        return new ManagedProcessHandle(name, process.Id);
    }

    /// <summary>
    /// Executa um comando de curta duração até terminar (ex.: pip install -e ., npm ci) e
    /// retorna o código de saída + stdout/stderr combinados. Não é rastreado para kill posterior
    /// porque já terminou antes de retornar.
    /// </summary>
    public static (int ExitCode, string Output) RunToCompletion(
        string fileName,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        IReadOnlyDictionary<string, string>? environmentOverrides = null,
        TimeSpan? timeout = null)
    {
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = System.Text.Encoding.UTF8,
            StandardErrorEncoding = System.Text.Encoding.UTF8,
        };
        foreach (var arg in arguments)
        {
            psi.ArgumentList.Add(arg);
        }
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        if (environmentOverrides is not null)
        {
            foreach (var (key, value) in environmentOverrides)
            {
                psi.Environment[key] = value;
            }
        }

        using var process = Process.Start(psi) ?? throw new InvalidOperationException($"Falha ao iniciar '{fileName}'.");
        var stdout = process.StandardOutput.ReadToEnd();
        var stderr = process.StandardError.ReadToEnd();
        var completed = process.WaitForExit((int)(timeout ?? TimeSpan.FromMinutes(15)).TotalMilliseconds);
        if (!completed)
        {
            TryKillTree(process);
            return (-1, stdout + stderr + "\n[launcher] timeout excedido, processo encerrado.");
        }
        return (process.ExitCode, stdout + stderr);
    }

    private static bool SafeHasExited(Process p)
    {
        try { return p.HasExited; } catch { return true; }
    }

    private static void TryKillTree(Process p)
    {
        try
        {
            if (!p.HasExited)
            {
                p.Kill(entireProcessTree: true);
            }
        }
        catch
        {
            // processo já pode ter terminado entre a checagem e o kill -- não é um erro fatal
        }
    }

    /// <summary>
    /// Encerra à força SOMENTE o processo filho rastreado mais recente com este `name` (ex.:
    /// "frontend", "dispatcher", "api") -- Incremento 2.2, seção 2 ("encerramento ordenado" e
    /// "matar forçadamente apenas o processo filho específico"). Nunca afeta outros processos
    /// filhos rastreados, e nunca usa taskkill genérico por nome/porta do sistema operacional.
    /// Retorna false se nenhum processo vivo com esse nome estiver rastreado (idempotente --
    /// chamar de novo depois que já encerrou não é erro).
    /// </summary>
    public bool TryKillNamed(string name)
    {
        lock (_lock)
        {
            for (var i = _children.Count - 1; i >= 0; i--)
            {
                if (_children[i].Name == name && !SafeHasExited(_children[i].Process))
                {
                    TryKillTree(_children[i].Process);
                    return true;
                }
            }
            return false;
        }
    }

    /// <summary>
    /// True se o processo filho rastreado mais recente com este nome ainda está vivo. Usado
    /// para decidir se um "kill forçado" ainda é necessário depois de esperar um shutdown
    /// gracioso.
    /// </summary>
    public bool IsNamedAlive(string name)
    {
        lock (_lock)
        {
            for (var i = _children.Count - 1; i >= 0; i--)
            {
                if (_children[i].Name == name)
                {
                    return !SafeHasExited(_children[i].Process);
                }
            }
            return false;
        }
    }

    /// <summary>
    /// Encerra SOMENTE os processos filhos rastreados por este supervisor (e suas árvores de
    /// processo), na ordem inversa de criação. Nunca usa taskkill por nome ou por porta.
    /// </summary>
    public void ShutdownAll()
    {
        lock (_lock)
        {
            for (var i = _children.Count - 1; i >= 0; i--)
            {
                TryKillTree(_children[i].Process);
            }
        }
    }

    public void Dispose()
    {
        ShutdownAll();
        lock (_lock)
        {
            foreach (var child in _children)
            {
                child.LogWriter?.Dispose();
                child.Process.Dispose();
            }
            _children.Clear();
        }
    }
}
