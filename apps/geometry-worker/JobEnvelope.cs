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
    [JsonPropertyName("wall_thickness_mm")] public double? WallThicknessMm { get; set; }
    [JsonPropertyName("isovalue")] public double Isovalue { get; set; }
    [JsonPropertyName("target_porosity_pct")] public double? TargetPorosityPct { get; set; }
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
    [JsonPropertyName("porosity_pct_estimated")] public double PorosityPctEstimated { get; set; }
    [JsonPropertyName("surface_area_mm2")] public double SurfaceAreaMm2 { get; set; }
    [JsonPropertyName("vertex_count")] public int VertexCount { get; set; }
    [JsonPropertyName("triangle_count")] public int TriangleCount { get; set; }
    [JsonPropertyName("is_watertight")] public bool IsWatertight { get; set; }
}

public sealed class WorkerResultOutput
{
    [JsonPropertyName("stl_path")] public string StlPath { get; set; } = "";
    [JsonPropertyName("thumbnail_path")] public string? ThumbnailPath { get; set; }
    [JsonPropertyName("vdb_path")] public string? VdbPath { get; set; }
    [JsonPropertyName("metrics")] public GeometryMetrics Metrics { get; set; } = new();
    [JsonPropertyName("worker_version")] public string WorkerVersion { get; set; } = "";
    [JsonPropertyName("dotnet_version")] public string DotnetVersion { get; set; } = "";
    [JsonPropertyName("picogk_version")] public string PicogkVersion { get; set; } = "";
    [JsonPropertyName("duration_seconds")] public double DurationSeconds { get; set; }
}

public sealed class StructuredWorkerError
{
    [JsonPropertyName("error_code")] public string ErrorCode { get; set; } = "";
    [JsonPropertyName("message")] public string Message { get; set; } = "";
}
