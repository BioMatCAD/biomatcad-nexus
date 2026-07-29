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
    private readonly List<(string Name, Process Process)> _children = new();
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
    /// Inicia um processo de longa duração (ex.: uvicorn, vite dev server) e passa a rastreá-lo.
    /// <paramref name="environmentOverrides"/> é aplicado por cima do ambiente herdado -- é assim
    /// que ENVIRONMENT=test e API_SECRET_KEY chegam ao processo da API sem nunca tocar disco.
    /// </summary>
    public ManagedProcessHandle StartTracked(
        string name,
        string fileName,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        IReadOnlyDictionary<string, string>? environmentOverrides = null)
    {
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        foreach (var arg in arguments)
        {
            psi.ArgumentList.Add(arg);
        }
        if (environmentOverrides is not null)
        {
            foreach (var (key, value) in environmentOverrides)
            {
                psi.Environment[key] = value;
            }
        }

        var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
        if (!process.Start())
        {
            throw new InvalidOperationException($"Falha ao iniciar processo '{name}' ({fileName}).");
        }

        lock (_lock)
        {
            _children.Add((name, process));
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
        };
        foreach (var arg in arguments)
        {
            psi.ArgumentList.Add(arg);
        }
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
            foreach (var (_, process) in _children)
            {
                process.Dispose();
            }
            _children.Clear();
        }
    }
}
