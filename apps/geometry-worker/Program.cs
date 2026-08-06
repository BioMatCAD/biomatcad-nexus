// Ponto de entrada CLI: dotnet BioMatCadGeometryWorker.dll <job.json>
// Nunca fabrica sucesso: qualquer exceção (incluindo DllNotFoundException do runtime nativo
// PicoGK ausente em linux-x64) é capturada e emitida como StructuredWorkerError em stderr,
// com exit code 1 -- ver ADR-0007/WORKER_STATUS.md.
//
// Incremento 2.1.1 (itens 3 e 4) adiciona validações PRÉ-execução (voxel count, memória
// estimada, formatos de saída suportados) que rodam ANTES de qualquer chamada ao PicoGK, e
// limpeza de arquivos parciais em caso de falha (ver OutputCleanup.cs -- correção adicional
// nesta sessão, depois que uma tentativa real de execução revelou que a limpeza original
// apagava também o job.json de entrada, gravado pelo chamador dentro do mesmo output_dir).
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using BioMatCadGeometryWorker;

const string WorkerVersion = "0.2.0-incremento-2.1.1";
HashSet<string> SupportedOutputFormats = new() { "stl" };

static StructuredWorkerError MakeError(string code, string message, Dictionary<string, string>? details = null) =>
    new() { ErrorCode = code, Message = Sanitize(message), Details = details };

// Nunca vaza caminhos absolutos do sistema de arquivos do usuário além do necessário -- troca o
// diretório home do usuário atual por um marcador neutro antes de emitir qualquer mensagem de
// erro (item 3: "erro estruturado e sanitizado").
static string Sanitize(string message)
{
    string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    if (!string.IsNullOrEmpty(home) && message.Contains(home))
        message = message.Replace(home, "~");
    return message;
}


if (args.Length < 1)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(MakeError("MISSING_JOB_ARGUMENT", "Uso: BioMatCadGeometryWorker <caminho-para-job.json>")));
    return 1;
}

var stopwatch = Stopwatch.StartNew();
string? outputDirForCleanup = null;
try
{
    string jobJsonPath = args[0];
    string jobJsonText = File.ReadAllText(jobJsonPath);
    var job = JsonSerializer.Deserialize<JobInput>(jobJsonText)
        ?? throw new InvalidOperationException("job.json vazio ou inválido.");

    outputDirForCleanup = job.OutputDir;

    // Incremento 2.2 (Seção 4): despacho por registro explícito de ITopologyProvider, em vez
    // de um if/else fixo -- rejeita ANTES de qualquer execução, com erro estruturado (mesmo
    // padrão dos demais rejeitos pré-execução abaixo), qualquer topology.kind desconhecido ou
    // ainda não implementado (ex.: "voronoi", que já existe como preparação documentada mas
    // nunca é aceito aqui -- ver docs/architecture/voronoi-topology-preparation.md).
    if (!TopologyProviderRegistry.TryGet(job.Recipe.Topology.Kind, out var topologyProvider) || topologyProvider is null)
    {
        Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
            "TOPOLOGY_PROVIDER_UNKNOWN",
            $"Provider de topologia desconhecido ou não implementado: '{job.Recipe.Topology.Kind}'.",
            new Dictionary<string, string>
            {
                ["requested_kind"] = job.Recipe.Topology.Kind,
                ["known_kinds"] = string.Join(",", TopologyProviderRegistry.KnownKinds),
            })));
        return 1;
    }

    // --- Item 4: honrar output_formats, rejeitar ANTES da execução se não suportado ---
    var unsupported = job.Recipe.OutputFormats.Where(f => !SupportedOutputFormats.Contains(f)).ToList();
    if (unsupported.Count > 0)
    {
        Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
            "OUTPUT_FORMAT_UNSUPPORTED",
            $"Formato(s) de saída solicitado(s) não suportado(s) por esta versão do worker: {string.Join(", ", unsupported)}.",
            new Dictionary<string, string> { ["requested_formats"] = string.Join(",", job.Recipe.OutputFormats), ["unsupported_formats"] = string.Join(",", unsupported) })));
        return 1;
    }

    // --- Item 3: limites computacionais -- estimativa PRÉVIA, antes de qualquer alocação real ---
    var topology = job.Recipe.Topology;
    double voxelSizeEffectiveMm = GyroidMath.EffectiveVoxelSizeMm(job.Recipe.Resolution.VoxelSizeMm, job.Recipe.Mode);
    long estimatedVoxelCount = GyroidMath.EstimateVoxelCount(job.Recipe.Domain, voxelSizeEffectiveMm);
    double estimatedMemoryMb = GyroidMath.EstimateMemoryMbUpperBound(estimatedVoxelCount);

    if (estimatedVoxelCount > job.Recipe.ComputeLimits.MaxVoxelCount)
    {
        Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
            "VOXEL_COUNT_LIMIT_EXCEEDED",
            $"Número estimado de voxels ({estimatedVoxelCount}) excede max_voxel_count ({job.Recipe.ComputeLimits.MaxVoxelCount}).",
            new Dictionary<string, string>
            {
                ["estimated_voxel_count"] = estimatedVoxelCount.ToString(),
                ["max_voxel_count"] = job.Recipe.ComputeLimits.MaxVoxelCount.ToString(),
                ["limit_kind"] = "estimated_upper_bound_dense_grid",
            })));
        return 1;
    }

    if (estimatedMemoryMb > job.Recipe.ComputeLimits.MaxMemoryMb)
    {
        Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
            "MEMORY_LIMIT_EXCEEDED",
            $"Memória estimada ({estimatedMemoryMb:F1}MB, limite superior de grade densa) excede max_memory_mb ({job.Recipe.ComputeLimits.MaxMemoryMb}). "
                + "Esta é uma estimativa PREVENTIVA (grade densa no pior caso) -- o PicoGK/OpenVDB usa estrutura esparsa e tipicamente consome menos; "
                + "não é um limite físico garantido.",
            new Dictionary<string, string>
            {
                ["estimated_memory_mb_upper_bound"] = estimatedMemoryMb.ToString("F1"),
                ["max_memory_mb"] = job.Recipe.ComputeLimits.MaxMemoryMb.ToString(),
                ["limit_kind"] = "estimated_preventive_not_physical_guarantee",
            })));
        return 1;
    }

    // --- Item 2: segunda checagem de consistência espessura/isovalor, específica da conversão
    // real usada pelo worker (a checagem estrutural genérica já roda na API antes de chegar aqui,
    // mas o worker é quem conhece a fórmula de conversão espessura->banda de verdade). ---
    // Incremento 2.2 (Seção 8): esta checagem é ESPECÍFICA do Gyroid (cell_size_mm/isovalue só
    // existem semanticamente para essa topologia) -- gated por topology.Kind para que uma
    // receita Voronoi (cujos campos cell_size_mm/wall_thickness_mm/isovalue nunca são
    // preenchidos, ficando em seus defaults 0.0) não seja rejeitada incorretamente por uma regra
    // que não se aplica a ela.
    if (job.Recipe.Topology.Kind == "gyroid")
    {
        double effectiveWallThicknessMm = topology.WallThicknessMm;
        if (topology.TargetPorosityPct is null && topology.WallThicknessMm >= topology.CellSizeMm / 2.0)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
                "TOPOLOGY_PARAMETERS_INCONSISTENT",
                $"wall_thickness_mm ({topology.WallThicknessMm}) >= cell_size_mm/2 ({topology.CellSizeMm / 2.0}) -- célula sem poro algum.")));
            return 1;
        }
        double halfBandWidthCheck = GyroidMath.WallThicknessMmToHalfBandWidth(effectiveWallThicknessMm, topology.CellSizeMm);
        const double maxFieldAmplitude = 3.0; // soma de 3 termos em [-1,1] -- limite algébrico exato
        if (topology.Isovalue - halfBandWidthCheck > maxFieldAmplitude || topology.Isovalue + halfBandWidthCheck < -maxFieldAmplitude)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
                "TOPOLOGY_PARAMETERS_INCONSISTENT",
                "A banda isovalor +/- meia-espessura resultante fica inteiramente fora da amplitude alcançável do campo gyroid ([-3,3]) -- geometria resultante seria vazia.")));
            return 1;
        }
    }

    Directory.CreateDirectory(job.OutputDir);
    string stlPath = Path.Combine(job.OutputDir, "scaffold.stl");

    var buildResult = topologyProvider.BuildAndExport(job, stlPath);
    // Marcador de diagnostico puro (rodada Voronoi 20260806-*, prova direta sem dispatcher) --
    // NAO altera nenhum algoritmo/parametro cientifico, apenas emite em stderr o instante exato
    // (UTC, ISO 8601) em que BuildAndExport (que envolve, de forma sincrona, a chamada real a
    // PicoGK.Library.Go) RETORNOU ao chamador -- permite a um roteiro externo medir com
    // precisao o tempo decorrido ate o retorno de Library.Go, distinto do tempo ate o JSON
    // final ser impresso (que so acontece depois de metrics/validacao/hash abaixo) e do tempo
    // adicional durante o qual o processo eventualmente continua vivo apos ambos ja terem
    // ocorrido -- ver scripts/Run-VoronoiDirectWorkerProbe.ps1 e
    // apps/geometry-worker/WORKER_STATUS.md secao 13.
    Console.Error.WriteLine($"[DIAG_MARKER] library_go_returned_at_utc={DateTime.UtcNow:O}");
    Console.Error.Flush();
    var metrics = GeometryMetricsCalculator.ComputeAll(buildResult.Mesh, job.Recipe.Domain);

    // --- Item 2: validar o STL após a gravação (não apenas confiar na malha em memória) ---
    var stlValidation = StlExporter.ValidateWrittenFile(stlPath, expectedTriangleCount: metrics.TriangleCount, expectedWatertight: metrics.IsWatertight);
    metrics.StlReloadValidationPassed = stlValidation.Passed;
    if (!stlValidation.Passed)
    {
        OutputCleanup.CleanupPartialOutputs(job.OutputDir);
        Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
            "STL_VALIDATION_FAILED_AFTER_WRITE",
            stlValidation.FailureReason ?? "Validação do STL após gravação falhou por motivo desconhecido.")));
        return 1;
    }

    stopwatch.Stop();

    string? picogkVersion = Assembly.Load("PicoGK").GetName().Version?.ToString();
    string stlSha256 = StlExporter.ComputeSha256Hex(stlPath);

    // Item 6/7 (correção pós-execução real): measured_porosity_pct SEMPRE vem de
    // metrics.PorosityPctMeasured -- calculada sobre buildResult.Mesh, que é EXATAMENTE a malha
    // soldada gravada no STL (não uma medição separada em memória que poderia divergir do
    // arquivo).
    //
    // Incremento 2.2 (Seção 8): a montagem de EffectiveParameters (antes hardcoded aqui, direto
    // contra os campos concretos de GyroidScaffoldBuilder.BuildResult) agora é DELEGADA ao
    // próprio provider através da interface -- cada provider conhece seu próprio tipo de
    // resultado (downcast interno seguro) e preenche os campos comuns + Extra
    // topologia-específico, sem que Program.cs precise saber qual topologia rodou. Mesma lógica
    // para as métricas extras (PopulateMetricsExtra) -- Gyroid não adiciona nada (metrics.Extra
    // permanece nulo, JSON idêntico a antes); Voronoi preenche contagens/comprimentos/graus.
    topologyProvider.PopulateMetricsExtra(metrics, buildResult);
    var effectiveParameters = topologyProvider.DescribeEffectiveParameters(
        job, buildResult, metrics, estimatedVoxelCount, estimatedMemoryMb);

    var output = new WorkerResultOutput
    {
        StlPath = stlPath,
        StlSha256 = stlSha256,
        ThumbnailPath = null, // geração de thumbnail depende de execução real -- ver WORKER_STATUS.md
        VdbPath = null,       // vdb não implementado nesta versão -- rejeitado antes da execução, ver acima
        Metrics = metrics,
        EffectiveParameters = effectiveParameters,
        TopologyProviderKind = topologyProvider.Kind,
        TopologyProviderVersion = topologyProvider.ProviderVersion,
        WorkerVersion = WorkerVersion,
        DotnetVersion = Environment.Version.ToString(),
        PicogkVersion = picogkVersion ?? "unknown",
        Platform = RuntimeInformation.OSDescription + " / " + RuntimeInformation.OSArchitecture,
        DurationSeconds = stopwatch.Elapsed.TotalSeconds,
    };
    Console.WriteLine(JsonSerializer.Serialize(output));
    return 0;
}
catch (PorosityTargetNotReachedException porosityEx)
{
    // Correção pós-execução real (Incremento 2.1.1): NUNCA finge sucesso científico quando a
    // calibração fechada contra a malha real não converge dentro da tolerância medida. Erro
    // estruturado dedicado (não WORKER_EXECUTION_FAILED genérico) para que quem consome a saída
    // do worker distinga claramente este caso de uma falha de execução comum.
    if (outputDirForCleanup is not null) OutputCleanup.CleanupPartialOutputs(outputDirForCleanup);

    var cal = porosityEx.CalibrationResult;
    Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(
        "POROSITY_TARGET_NOT_REACHED",
        porosityEx.Message,
        new Dictionary<string, string>
        {
            ["measured_porosity_pct"] = cal.MeasuredPorosityPct.ToString("F6"),
            ["porosity_tolerance_pct_points"] = cal.ToleranceUsedPctPoints.ToString("F2"),
            ["measured_porosity_error_pct_points"] = cal.ResidualErrorPctPoints.ToString("F6"),
            ["mesh_calibration_iterations"] = cal.Iterations.ToString(),
        })));
    return 1;
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

    if (outputDirForCleanup is not null) OutputCleanup.CleanupPartialOutputs(outputDirForCleanup);

    Console.Error.WriteLine(JsonSerializer.Serialize(MakeError(errorCode, ex.ToString())));
    return 1;
}
