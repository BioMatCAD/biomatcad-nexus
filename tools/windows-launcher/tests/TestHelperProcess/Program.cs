// Processo auxiliar de testes multiplataforma (ver comentário no .csproj). Cada "modo" é um
// comportamento controlado e determinístico usado pelos testes de BioMatCAD.Launcher.Tests,
// substituindo dependências de sh/sleep/python3/cmd.exe timeout por código gerenciado .NET
// idêntico em Linux e Windows.
//
// Uso: TestHelperProcess.dll <modo> [args...]
//   sleep <segundos>                      -- dorme e sai com código 0; nunca olha para nenhum
//                                             arquivo/sinal (simula um processo que "nunca
//                                             responde" a um pedido de parada graciosa).
//   watch-stopfile <stopFile> <statusFile> -- espera (polling) o arquivo <stopFile> aparecer
//                                             (até 60s), então escreve um status.json mínimo
//                                             (schema do dispatcher real, state=stopped, PID
//                                             real deste processo) em <statusFile> e sai.
//   echo-env <varName> <outFile>           -- grava o valor da variável de ambiente <varName>
//                                             (string vazia se ausente) em <outFile>, sem
//                                             nenhuma interpretação de shell/redirection.
//   log-lines                              -- imprime uma linha fixa em stdout (contendo um
//                                             segredo de teste a ser sanitizado) e uma linha
//                                             fixa em stderr, então sai -- usado para testar a
//                                             drenagem/sanitização de logs do ProcessSupervisor.
//   log-lines-then-sleep <segundos>        -- igual a "log-lines", mas permanece vivo por
//                                             <segundos> depois de imprimir -- usado para
//                                             testar leitura do log com o processo AINDA
//                                             rodando (não apenas depois de terminar).
//   slow-stderr <atrasoMs>                  -- imprime a linha de stdout IMEDIATAMENTE, espera
//                                             <atrasoMs> milissegundos, só então imprime a
//                                             linha de stderr, e sai -- usado para provar que o
//                                             EOF de stdout e o EOF de stderr são sinalizados de
//                                             forma independente (um atraso artificial em UM
//                                             stream não pode fazer a drenagem concluir antes
//                                             do outro).
//   slow-stdout <atrasoMs>                  -- o inverso de slow-stderr: imprime stderr
//                                             imediatamente, espera <atrasoMs>, só então
//                                             imprime stdout, e sai.
//   flood-lines <quantidade>                -- dispara DUAS threads verdadeiramente
//                                             concorrentes dentro do próprio processo filho:
//                                             uma escreve "OUT-0000".."OUT-NNNN" em stdout, a
//                                             outra escreve "ERR-0000".."ERR-NNNN" em stderr,
//                                             ao mesmo tempo -- maximiza a chance real de
//                                             sobreposição entre os callbacks OutputDataReceived
//                                             e ErrorDataReceived do lado do ProcessSupervisor,
//                                             para testes de stress da sincronização do log.

if (args.Length == 0)
{
    Console.Error.WriteLine("uso: TestHelperProcess <sleep|watch-stopfile|echo-env|log-lines> [args...]");
    return 1;
}

switch (args[0])
{
    case "sleep":
    {
        var seconds = args.Length > 1 ? int.Parse(args[1]) : 30;
        Thread.Sleep(TimeSpan.FromSeconds(seconds));
        return 0;
    }
    case "watch-stopfile":
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine("uso: watch-stopfile <stopFile> <statusFile>");
            return 1;
        }
        var stopFile = args[1];
        var statusFile = args[2];
        for (var i = 0; i < 600; i++) // até 60s (100ms por iteração)
        {
            if (File.Exists(stopFile))
            {
                break;
            }
            Thread.Sleep(100);
        }
        var pid = Environment.ProcessId;
        var json = "{\"dispatcher_id\":\"test-helper:" + pid + "\",\"pid\":" + pid +
            ",\"state\":\"stopped\",\"phase\":\"idle\",\"started_at\":\"2026-01-01T00:00:00+00:00\"," +
            "\"last_poll_at\":\"2026-01-01T00:00:00+00:00\",\"jobs_processed_total\":0," +
            "\"current_poll_interval_seconds\":3.0,\"last_job_id\":null}";
        File.WriteAllText(statusFile, json);
        return 0;
    }
    case "echo-env":
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine("uso: echo-env <varName> <outFile>");
            return 1;
        }
        var varName = args[1];
        var outFile = args[2];
        File.WriteAllText(outFile, Environment.GetEnvironmentVariable(varName) ?? string.Empty);
        return 0;
    }
    case "log-lines":
    {
        Console.WriteLine("linha stdout com postgresql://user:segredo123@host:5432/db");
        Console.Error.WriteLine("linha stderr");
        return 0;
    }
    case "log-lines-then-sleep":
    {
        var seconds = args.Length > 1 ? int.Parse(args[1]) : 5;
        Console.WriteLine("linha stdout com postgresql://user:segredo123@host:5432/db");
        Console.Error.WriteLine("linha stderr");
        Console.Out.Flush();
        Console.Error.Flush();
        Thread.Sleep(TimeSpan.FromSeconds(seconds));
        return 0;
    }
    case "slow-stderr":
    {
        var delayMs = args.Length > 1 ? int.Parse(args[1]) : 1000;
        Console.WriteLine("linha stdout com postgresql://user:segredo123@host:5432/db");
        Console.Out.Flush();
        Thread.Sleep(delayMs);
        Console.Error.WriteLine("linha stderr");
        Console.Error.Flush();
        return 0;
    }
    case "slow-stdout":
    {
        var delayMs = args.Length > 1 ? int.Parse(args[1]) : 1000;
        Console.Error.WriteLine("linha stderr");
        Console.Error.Flush();
        Thread.Sleep(delayMs);
        Console.WriteLine("linha stdout com postgresql://user:segredo123@host:5432/db");
        Console.Out.Flush();
        return 0;
    }
    case "flood-lines":
    {
        var count = args.Length > 1 ? int.Parse(args[1]) : 200;
        var stdoutThread = new Thread(() =>
        {
            for (var i = 0; i < count; i++)
            {
                Console.WriteLine($"OUT-{i:D4}");
            }
            Console.Out.Flush();
        });
        var stderrThread = new Thread(() =>
        {
            for (var i = 0; i < count; i++)
            {
                Console.Error.WriteLine($"ERR-{i:D4}");
            }
            Console.Error.Flush();
        });
        stdoutThread.Start();
        stderrThread.Start();
        stdoutThread.Join();
        stderrThread.Join();
        return 0;
    }
    default:
        Console.Error.WriteLine($"modo desconhecido: {args[0]}");
        return 1;
}
