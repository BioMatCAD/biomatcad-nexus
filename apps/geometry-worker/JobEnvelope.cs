// Contrato JSON de entrada/saída do worker (Incremento 2.1, item 3).
// Independente do PicoGK -- testável sem o runtime nativo bloqueado.
using System.Text.Json.Serialization;

namespace BioMatCadGeometryWorker;

public sealed class RecipeDimensions
{
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("x_mm")] public double? XMm { get; set; }
    [JsonPropertyName("y_mm")] public double? YMm { get; set; }
    [JsonPropertyName("z_mm")] public double? ZMm { get; set; }
    [JsonPropertyName("radius_mm")] public double? RadiusMm { get; set; }
    [JsonPropertyName("height_mm")] public double? HeightMm { get; set; }
}

public sealed class RecipeDomain
{
    [JsonPropertyName("shape")] public string Shape { get; set; } = "";
    [JsonPropertyName("dimensions_mm")] public RecipeDimensions DimensionsMm { get; set; } = new();
}

public sealed class RecipeTopology
{
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("cell_size_mm")] public double CellSizeMm { get; set; }
    // Incremento 2.1.1 (item 2): obrigatório no schema; único controlador de espessura.
    [JsonPropertyName("wall_thickness_mm")] public double WallThicknessMm { get; set; }
    // Opcional no schema (default 0.0 = centro de banda balanceado); NÃO controla espessura.
    [JsonPropertyName("isovalue")] public double Isovalue { get; set; }
    [JsonPropertyName("target_porosity_pct")] public double? TargetPorosityPct { get; set; }

    // Incremento 2.2 (Secao 3, rodada Voronoi): campos especificos de voronoi_cell_edges_v1,
    // todos opcionais/nulaveis -- receitas Gyroid nunca os populam, e a ausencia deles nunca
    // afeta a desserializacao/comportamento de uma receita Gyroid existente (aditivo, zero
    // regressao). VoronoiScaffoldBuilder exige os obrigatorios (site_count, distribution,
    // strut_radius_mm) em tempo de execucao e lanca erro estruturado se ausentes -- o JSON
    // Schema (geometry-recipe-v1.schema.json) ja os torna obrigatorios no ramo voronoi_cell_edges_v1
    // antes mesmo de chegar ao worker.
    [JsonPropertyName("site_count")] public int? SiteCount { get; set; }
    [JsonPropertyName("distribution")] public string? Distribution { get; set; }
    [JsonPropertyName("seed_site_min_separation_mm")] public double? SeedSiteMinSeparationMm { get; set; }
    [JsonPropertyName("strut_radius_mm")] public double? StrutRadiusMm { get; set; }
    [JsonPropertyName("node_smoothing")] public double? NodeSmoothing { get; set; }
    [JsonPropertyName("node_radius_factor")] public double? NodeRadiusFactor { get; set; }
    [JsonPropertyName("boundary_behavior")] public string? BoundaryBehavior { get; set; }
}

public sealed class RecipeResolution
{
    [JsonPropertyName("voxel_size_mm")] public double VoxelSizeMm { get; set; } = 0.2;
}

public sealed class RecipeComputeLimits
{
    [JsonPropertyName("max_duration_seconds")] public int MaxDurationSeconds { get; set; }
    [JsonPropertyName("max_memory_mb")] public int MaxMemoryMb { get; set; }
    [JsonPropertyName("max_voxel_count")] public long MaxVoxelCount { get; set; }
}

public sealed class RecipeCanonical
{
    [JsonPropertyName("schema_version")] public string SchemaVersion { get; set; } = "";
    [JsonPropertyName("domain")] public RecipeDomain Domain { get; set; } = new();
    [JsonPropertyName("topology")] public RecipeTopology Topology { get; set; } = new();
    [JsonPropertyName("resolution")] public RecipeResolution Resolution { get; set; } = new();
    [JsonPropertyName("mode")] public string Mode { get; set; } = "preview";
    [JsonPropertyName("seed")] public long Seed { get; set; }
    [JsonPropertyName("compute_limits")] public RecipeComputeLimits ComputeLimits { get; set; } = new();
    [JsonPropertyName("output_formats")] public List<string> OutputFormats { get; set; } = new();
}

public sealed class JobInput
{
    [JsonPropertyName("job_id")] public string JobId { get; set; } = "";
    [JsonPropertyName("recipe")] public RecipeCanonical Recipe { get; set; } = new();
    [JsonPropertyName("output_dir")] public string OutputDir { get; set; } = "";
}

public sealed class GeometryMetrics
{
    [JsonPropertyName("bounding_box_mm")] public double[][] BoundingBoxMm { get; set; } = Array.Empty<double[]>();
    [JsonPropertyName("volume_mm3")] public double VolumeMm3 { get; set; }
    [JsonPropertyName("porosity_pct_measured")] public double PorosityPctMeasured { get; set; }
    [JsonPropertyName("surface_area_mm2")] public double SurfaceAreaMm2 { get; set; }
    // Vértices ÚNICOS (após solda por posição, ver SimpleMesh.Weld) -- não 3 por triângulo
    // (Incremento 2.1.1, item 2/11, corrige divergência da auditoria STL-vs-manifesto).
    [JsonPropertyName("vertex_count_unique")] public int VertexCountUnique { get; set; }
    [JsonPropertyName("triangle_count")] public int TriangleCount { get; set; }
    [JsonPropertyName("is_watertight")] public bool IsWatertight { get; set; }
    [JsonPropertyName("stl_reload_validation_passed")] public bool StlReloadValidationPassed { get; set; }

    // Incremento 2.2 (Secao 8/9): campos METRICOS especificos de cada topologia (ex.: contagem
    // de sitios/nos/arestas/componentes do Voronoi) sao mesclados aqui de forma GENERICA via
    // [JsonExtensionData] -- verificado empiricamente (probe descartavel) que, quando Extra e
    // nulo ou vazio, a serializacao produz EXATAMENTE o mesmo JSON de antes (nenhuma chave nova
    // aparece, zero regressao para o Gyroid, que nunca popula este dicionario). Quando populado
    // (Voronoi), cada chave/valor e mesclado como um campo IRMAO no mesmo objeto JSON, nao
    // aninhado sob uma chave "extra" -- Program.cs nunca precisa saber quais chaves cada
    // topologia usa.
    [JsonExtensionData] public Dictionary<string, object?>? Extra { get; set; }
}

public sealed class EffectiveParameters
{
    [JsonPropertyName("wall_thickness_requested_mm")] public double WallThicknessRequestedMm { get; set; }
    [JsonPropertyName("wall_thickness_effective_mm")] public double WallThicknessEffectiveMm { get; set; }
    [JsonPropertyName("isovalue_center")] public double IsovalueCenter { get; set; }
    [JsonPropertyName("target_porosity_pct_requested")] public double? TargetPorosityPctRequested { get; set; }
    // Correção pós-execução real (Incremento 2.1.1): distinção EXPLÍCITA entre a estimativa
    // analítica contínua (Passo 1, palpite inicial, nunca prova sucesso sozinha) e a porosidade
    // MEDIDA de verdade sobre a malha real do PicoGK (Passo 2, valor de referência definitivo).
    // A auditoria do usuário no Windows encontrou um caso real (preview) em que a estimativa
    // analítica "convergia" (59,40% vs. alvo 60%) enquanto a malha real media 78,80% -- por isso
    // analytical_calibration_converged NUNCA deve ser interpretado como prova de que o alvo foi
    // atingido; measured_porosity_within_tolerance é quem responde essa pergunta de verdade.
    [JsonPropertyName("analytical_porosity_estimate_pct")] public double? AnalyticalPorosityEstimatePct { get; set; }
    [JsonPropertyName("analytical_calibration_converged")] public bool? AnalyticalCalibrationConverged { get; set; }
    [JsonPropertyName("measured_porosity_pct")] public double? MeasuredPorosityPct { get; set; }
    [JsonPropertyName("porosity_tolerance_pct_points")] public double? PorosityTolerancePctPoints { get; set; }
    [JsonPropertyName("measured_porosity_error_pct_points")] public double? MeasuredPorosityErrorPctPoints { get; set; }
    [JsonPropertyName("measured_porosity_within_tolerance")] public bool? MeasuredPorosityWithinTolerance { get; set; }
    [JsonPropertyName("mesh_calibration_iterations")] public int? MeshCalibrationIterations { get; set; }
    [JsonPropertyName("seed")] public long Seed { get; set; }
    [JsonPropertyName("seed_phase_shift_rad")] public double SeedPhaseShiftRad { get; set; }
    [JsonPropertyName("mode")] public string Mode { get; set; } = "";
    [JsonPropertyName("voxel_size_requested_mm")] public double VoxelSizeRequestedMm { get; set; }
    [JsonPropertyName("voxel_size_effective_mm")] public double VoxelSizeEffectiveMm { get; set; }
    [JsonPropertyName("estimated_voxel_count")] public long EstimatedVoxelCount { get; set; }
    [JsonPropertyName("estimated_memory_mb_upper_bound")] public double EstimatedMemoryMbUpperBound { get; set; }

    // Incremento 2.2 (Secao 8/9): mesma tecnica de extensao generica de GeometryMetrics.Extra
    // (ver comentario acima), aplicada aqui para parametros efetivos especificos de cada
    // topologia (ex.: site_count, distribution_used, strut_radius_effective_mm do Voronoi).
    // Os campos Gyroid-especificos ja existentes nesta classe (wall_thickness_*, isovalue_center,
    // seed_phase_shift_rad, analytical_*) permanecem EXATAMENTE como estao -- nunca preenchidos
    // por VoronoiTopologyProvider, que usa apenas este dicionario Extra para seus proprios campos.
    [JsonExtensionData] public Dictionary<string, object?>? Extra { get; set; }
}

public sealed class WorkerResultOutput
{
    [JsonPropertyName("stl_path")] public string StlPath { get; set; } = "";
    [JsonPropertyName("stl_sha256")] public string StlSha256 { get; set; } = "";
    [JsonPropertyName("thumbnail_path")] public string? ThumbnailPath { get; set; }
    [JsonPropertyName("vdb_path")] public string? VdbPath { get; set; }
    [JsonPropertyName("metrics")] public GeometryMetrics Metrics { get; set; } = new();
    [JsonPropertyName("effective_parameters")] public EffectiveParameters EffectiveParameters { get; set; } = new();
    // Incremento 2.2 (Seção 4): qual provider de topologia efetivamente gerou esta geometria --
    // nunca assumido implicitamente a partir do nome da receita, sempre o valor real reportado
    // pelo próprio ITopologyProvider que rodou (ver TopologyProviderRegistry em Program.cs).
    [JsonPropertyName("topology_provider_kind")] public string TopologyProviderKind { get; set; } = "";
    [JsonPropertyName("topology_provider_version")] public string TopologyProviderVersion { get; set; } = "";
    [JsonPropertyName("worker_version")] public string WorkerVersion { get; set; } = "";
    [JsonPropertyName("dotnet_version")] public string DotnetVersion { get; set; } = "";
    [JsonPropertyName("picogk_version")] public string PicogkVersion { get; set; } = "";
    [JsonPropertyName("platform")] public string Platform { get; set; } = "";
    [JsonPropertyName("duration_seconds")] public double DurationSeconds { get; set; }
}

public sealed class StructuredWorkerError
{
    [JsonPropertyName("error_code")] public string ErrorCode { get; set; } = "";
    [JsonPropertyName("message")] public string Message { get; set; } = "";
    // Detalhes adicionais sanitizados (nunca stack trace bruto de path do sistema de arquivos
    // do usuário -- ver Program.cs Sanitize()) (Incremento 2.1.1, item 3).
    [JsonPropertyName("details")] public Dictionary<string, string>? Details { get; set; }
}
