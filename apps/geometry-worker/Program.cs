// Ponto de entrada CLI: dotnet BioMatCadGeometryWorker.dll <job.json>
// Nunca fabrica sucesso: qualquer exceção (incluindo DllNotFoundException do runtime nativo
// PicoGK ausente em linux-x64) é capturada e emitida como StructuredWorkerError em stderr,
// com exit code 1 -- ver ADR-0007/WORKER_STATUS.md.
using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using BioMatCadGeometryWorker;

if (args.Length < 1)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new StructuredWorkerError
    {
        ErrorCode = "MISSING_JOB_ARGUMENT",
        Message = "Uso: BioMatCadGeometryWorker <caminho-para-job.json>",
    }));
    return 1;
}

var stopwatch = Stopwatch.StartNew();
try
{
    string jobJsonPath = args[0];
    string jobJsonText = File.ReadAllText(jobJsonPath);
    var job = JsonSerializer.Deserialize<JobInput>(jobJsonText)
        ?? throw new InvalidOperationException("job.json vazio ou inválido.");

    if (job.Recipe.Topology.Kind != "gyroid")
        throw new NotSupportedException($"Topologia não suportada nesta versão: {job.Recipe.Topology.Kind}");

    Directory.CreateDirectory(job.OutputDir);
    string stlPath = Path.Combine(job.OutputDir, "scaffold.stl");

    var buildResult = GyroidScaffoldBuilder.BuildAndExport(job, stlPath);
    var metrics = GeometryMetricsCalculator.ComputeAll(buildResult.Mesh, job.Recipe.Domain);

    stopwatch.Stop();

    string? picogkVersion = Assembly.Load("PicoGK").GetName().Version?.ToString();

    var output = new WorkerResultOutput
    {
        StlPath = stlPath,
        ThumbnailPath = null, // geração de thumbnail depende de execução real -- ver WORKER_STATUS.md
        VdbPath = null,       // vdb não gerado nesta versão -- ver WORKER_STATUS.md
        Metrics = metrics,
        WorkerVersion = "0.1.0",
        DotnetVersion = Environment.Version.ToString(),
        PicogkVersion = picogkVersion ?? "unknown",
        DurationSeconds = stopwatch.Elapsed.TotalSeconds,
    };
    Console.WriteLine(JsonSerializer.Serialize(output));
    return 0;
}
catch (Exception ex)
{
    // PicoGK.Library captura internamente a DllNotFoundException do runtime nativo ausente e
    // relança uma System.Exception genérica ("Failed to load PicoGK library") -- por isso a
    // detecção verifica tanto o tipo da exceção (própria ou em InnerException) quanto a
    // mensagem textual, não apenas `ex is DllNotFoundException`.
    bool isPicoGkRuntimeUnavailable =
        ex is DllNotFoundException
        || (ex.InnerException is DllNotFoundException)
        || ex.ToString().Contains("DllNotFoundException")
        || ex.Message.Contains("Failed to load PicoGK library");
    string errorCode = isPicoGkRuntimeUnavailable ? "PICOGK_RUNTIME_UNAVAILABLE" : "WORKER_EXECUTION_FAILED";
    Console.Error.WriteLine(JsonSerializer.Serialize(new StructuredWorkerError
    {
        ErrorCode = errorCode,
        Message = ex.ToString(),
    }));
    return 1;
}
