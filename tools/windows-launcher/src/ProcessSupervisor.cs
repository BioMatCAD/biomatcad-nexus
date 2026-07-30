using System.Diagnostics;
using System.Text;

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

        // Sinalizados quando OutputDataReceived/ErrorDataReceived entregam e.Data == null --
        // o sinal padrão do .NET de que aquele stream redirecionado chegou ao fim (EOF), ou
        // seja, todas as linhas já foram entregues e não há mais nada a drenar. Nulos quando
        // não há LogWriter (nada sendo drenado para arquivo).
        public ManualResetEventSlim? StdoutDrained { get; init; }
        public ManualResetEventSlim? StderrDrained { get; init; }

        // Idempotência/thread-safety da finalização (item 3 do relatório do usuário): pode ser
        // disparada concorrentemente por Process.Exited (término natural), TryKillNamed,
        // ShutdownAll ou Dispose -- só a PRIMEIRA chamada deve realmente fechar o LogWriter.
        private int _finalized;
        public bool TryBeginFinalize() => Interlocked.CompareExchange(ref _finalized, 1, 0) == 0;
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
    /// mais saída.
    ///
    /// Ciclo de vida do arquivo de log (bug real relatado pelo usuário: IOException "sendo
    /// usado por outro processo" ao ler child.log com o processo filho ainda rodando ou recém
    /// terminado):
    ///   - O FileStream do escritor é aberto explicitamente com FileShare.Read: permite que
    ///     OUTROS leitores (o painel de observabilidade, <see cref="ReadLogFile"/>, os testes)
    ///     abram o mesmo arquivo para leitura enquanto ainda escrevemos nele, mas nunca permite
    ///     que outro processo externo abra o arquivo para ESCRITA concorrente.
    ///   - Por si só, FileShare.Read do lado do escritor não é suficiente: quem for LER o
    ///     arquivo enquanto ele ainda está aberto para escrita precisa declarar, na sua própria
    ///     abertura, que tolera um escritor concorrente (FileShare.ReadWrite do lado do leitor
    ///     -- ver <see cref="ReadLogFile"/>). Isso é uma regra de compartilhamento do próprio
    ///     Windows (bidirecional: o pedido de acesso do novo handle precisa ser permitido pelo
    ///     "share" do handle já aberto, E o "share" do novo handle precisa permitir o acesso do
    ///     handle já aberto) -- por isso a correção certa é no lado de quem LÊ, não relaxar o
    ///     lado de quem ESCREVE para algo mais permissivo que o necessário.
    ///   - O LogWriter só é fechado (Flush + Dispose) quando o processo filho termina de
    ///     verdade -- via <see cref="Process.Exited"/> (término natural) OU explicitamente por
    ///     <see cref="TryKillNamed"/>/<see cref="ShutdownAll"/>/<see cref="Dispose"/> -- e só
    ///     depois de esperar (com timeout limitado) os handlers assíncronos de stdout/stderr
    ///     sinalizarem que já entregaram tudo (EOF), para nunca perder as últimas linhas nem
    ///     fechar o arquivo no meio de uma entrega ainda em voo. Os quatro caminhos convergem
    ///     para a mesma rotina (<see cref="FinalizeChild"/>), que é idempotente.
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
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
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
        ManualResetEventSlim? stdoutDrained = null;
        ManualResetEventSlim? stderrDrained = null;

        if (logFilePath is not null)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(logFilePath) ?? ".");
            // FileShare.Read explícito (documentado na doc-comment do método): permite leitores
            // concorrentes (observabilidade/testes via ReadLogFile), nunca outro escritor
            // externo.
            var fileStream = new FileStream(logFilePath, FileMode.Create, FileAccess.Write, FileShare.Read);
            logWriter = new StreamWriter(fileStream, Encoding.UTF8) { AutoFlush = true };
            stdoutDrained = new ManualResetEventSlim(false);
            stderrDrained = new ManualResetEventSlim(false);
        }

        // "child" precisa existir ANTES de Process.Start() porque os handlers abaixo (fechados
        // sobre esta variável) podem disparar a qualquer momento depois do Start(), inclusive
        // Process.Exited, que precisa da referência completa (incluindo LogWriter/eventos de
        // drenagem) para poder finalizar corretamente.
        var child = new TrackedChild
        {
            Name = name,
            Process = process,
            LogWriter = logWriter,
            StdoutDrained = stdoutDrained,
            StderrDrained = stderrDrained,
        };

        if (logWriter is not null)
        {
            void OnOutputLine(object sender, DataReceivedEventArgs e)
            {
                if (e.Data is null)
                {
                    stdoutDrained!.Set();
                    return;
                }
                WriteSanitizedLine(logWriter, e.Data, sanitizeLine);
            }

            void OnErrorLine(object sender, DataReceivedEventArgs e)
            {
                if (e.Data is null)
                {
                    stderrDrained!.Set();
                    return;
                }
                WriteSanitizedLine(logWriter, e.Data, sanitizeLine);
            }

            process.OutputDataReceived += OnOutputLine;
            process.ErrorDataReceived += OnErrorLine;
        }

        // Término natural (o processo simplesmente sai sozinho, sem ninguém chamar
        // TryKillNamed/ShutdownAll/Dispose primeiro) -- este é o caminho que faltava antes
        // desta correção: sem ele, um processo que termina por conta própria nunca tinha seu
        // LogWriter fechado, a não ser que Dispose() do supervisor inteiro fosse chamado depois.
        process.Exited += (_, _) => FinalizeChild(child);

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
            _children.Add(child);
        }

        return new ManagedProcessHandle(name, process.Id);
    }

    private static void WriteSanitizedLine(StreamWriter logWriter, string data, Func<string, string>? sanitizeLine)
    {
        var line = sanitizeLine is not null ? sanitizeLine(data) : data;
        try
        {
            logWriter.WriteLine(line);
        }
        catch (ObjectDisposedException)
        {
            // Escritor já foi fechado (FinalizeChild já rodou) -- linha tardia, descartável.
        }
    }

    /// <summary>
    /// Lê o conteúdo completo de um arquivo de log de um processo rastreado, mesmo que o
    /// processo AINDA ESTEJA RODANDO (e portanto o LogWriter interno ainda tenha o arquivo
    /// aberto para escrita) -- é assim que o painel de observabilidade (e os testes) podem
    /// consultar os logs em tempo real, sem esperar o processo terminar.
    ///
    /// FileShare.ReadWrite aqui é sobre o que ESTA leitura tolera de handles concorrentes já
    /// abertos (o nosso próprio escritor interno, que tem acesso de escrita) -- é uma regra de
    /// compartilhamento do Windows: um leitor que só declara FileShare.Read falha com
    /// IOException ("sendo usado por outro processo") ao tentar abrir um arquivo que já está
    /// aberto para escrita por outro handle, mesmo que o próprio leitor só peça acesso de
    /// leitura. Isto NÃO abre a porta para qualquer processo externo escrever no arquivo --
    /// quem decide isso é exclusivamente quem ABRE o arquivo para escrita (<see
    /// cref="StartTracked"/>, que usa FileShare.Read, nunca Write, do lado do escritor).
    /// </summary>
    public static string ReadLogFile(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        using var reader = new StreamReader(stream, Encoding.UTF8);
        return reader.ReadToEnd();
    }

    /// <summary>
    /// Espera (com timeout limitado, nunca indefinidamente) até que a drenagem assíncrona de
    /// stdout E stderr do processo rastreado <paramref name="name"/> tenha sinalizado EOF --
    /// ou seja, até que todas as linhas que aquele processo já escreveu tenham sido de fato
    /// entregues ao LogWriter. Não é um sleep arbitrário: espera uma condição real
    /// (ManualResetEventSlim sinalizado pelos próprios handlers de OutputDataReceived/
    /// ErrorDataReceived quando entregam e.Data == null). Retorna true se ambos os streams
    /// (ou nenhum, se o processo não tiver LogWriter) já drenaram dentro do timeout; false se o
    /// timeout expirou primeiro.
    /// </summary>
    public bool WaitUntilLogDrained(string name, TimeSpan timeout)
    {
        TrackedChild? found;
        lock (_lock)
        {
            found = _children.LastOrDefault(c => c.Name == name);
        }
        if (found?.LogWriter is null)
        {
            return true; // nada rastreado com LogWriter para esse nome -- nada a drenar.
        }

        var deadline = DateTime.UtcNow + timeout;
        var stdoutOk = found.StdoutDrained is null || found.StdoutDrained.Wait(timeout);
        var remaining = deadline - DateTime.UtcNow;
        var stderrOk = found.StderrDrained is null ||
            found.StderrDrained.Wait(remaining > TimeSpan.Zero ? remaining : TimeSpan.Zero);
        return stdoutOk && stderrOk;
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
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
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
    /// Rotina única de finalização de um processo rastreado (item 4 do relatório do usuário:
    /// Dispose, TryKillNamed, ShutdownAll e término natural precisam convergir para a mesma
    /// rotina). Idempotente e thread-safe via <see cref="TrackedChild.TryBeginFinalize"/> --
    /// pode ser chamada mais de uma vez (ex.: Process.Exited dispara concorrentemente com uma
    /// chamada explícita a TryKillNamed) sem efeito colateral duplicado. Espera (com timeout
    /// limitado) a drenagem de stdout/stderr terminar antes de fechar o LogWriter, para nunca
    /// perder as últimas linhas nem lançar no meio de uma entrega assíncrona ainda em voo.
    /// </summary>
    private static void FinalizeChild(TrackedChild child)
    {
        if (!child.TryBeginFinalize())
        {
            return;
        }
        child.StdoutDrained?.Wait(TimeSpan.FromSeconds(5));
        child.StderrDrained?.Wait(TimeSpan.FromSeconds(5));
        child.LogWriter?.Flush();
        child.LogWriter?.Dispose();
    }

    /// <summary>
    /// Encerra à força SOMENTE o processo filho rastreado mais recente com este `name` (ex.:
    /// "frontend", "dispatcher", "api") -- Incremento 2.2, seção 2 ("encerramento ordenado" e
    /// "matar forçadamente apenas o processo filho específico"). Nunca afeta outros processos
    /// filhos rastreados, e nunca usa taskkill genérico por nome/porta do sistema operacional.
    /// Retorna false se nenhum processo vivo com esse nome estiver rastreado (idempotente --
    /// chamar de novo depois que já encerrou não é erro). Espera (com timeout curto e limitado)
    /// o processo sair de verdade e finaliza seu log antes de retornar.
    /// </summary>
    public bool TryKillNamed(string name)
    {
        TrackedChild? target = null;
        lock (_lock)
        {
            for (var i = _children.Count - 1; i >= 0; i--)
            {
                if (_children[i].Name == name && !SafeHasExited(_children[i].Process))
                {
                    target = _children[i];
                    break;
                }
            }
        }
        if (target is null)
        {
            return false;
        }
        TryKillTree(target.Process);
        try { target.Process.WaitForExit(2000); } catch { /* segue mesmo assim */ }
        FinalizeChild(target);
        return true;
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
    /// processo), na ordem inversa de criação. Nunca usa taskkill por nome ou por porta. Espera
    /// cada processo sair e finaliza seu log antes de seguir para o próximo.
    /// </summary>
    public void ShutdownAll()
    {
        List<TrackedChild> snapshot;
        lock (_lock)
        {
            snapshot = new List<TrackedChild>(_children);
        }
        for (var i = snapshot.Count - 1; i >= 0; i--)
        {
            var child = snapshot[i];
            TryKillTree(child.Process);
            try { child.Process.WaitForExit(2000); } catch { /* segue mesmo assim */ }
            FinalizeChild(child);
        }
    }

    /// <summary>
    /// Encerra todos os processos rastreados e libera de verdade seus recursos: mata, espera
    /// sair, finaliza o log (mesma rotina convergente de <see cref="FinalizeChild"/>, portanto
    /// idempotente mesmo que o processo já tenha sido finalizado por término natural ou por
    /// TryKillNamed/ShutdownAll antes) e descarta o objeto Process.
    /// </summary>
    public void Dispose()
    {
        lock (_lock)
        {
            for (var i = _children.Count - 1; i >= 0; i--)
            {
                var child = _children[i];
                TryKillTree(child.Process);
                try { child.Process.WaitForExit(2000); } catch { /* segue mesmo assim */ }
                FinalizeChild(child);
                child.Process.Dispose();
            }
            _children.Clear();
        }
    }
}
