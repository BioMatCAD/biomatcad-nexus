using System.Text.Json;
using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class JobEnvelopeTests
{
    private const string SampleJobJson = """
    {
      "job_id": "job-123",
      "output_dir": "/tmp/out",
      "recipe": {
        "schema_version": "1.0.0",
        "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
        "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "isovalue": 0.0, "target_porosity_pct": 60},
        "resolution": {"voxel_size_mm": 0.2},
        "mode": "preview",
        "seed": 42,
        "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
        "output_formats": ["stl"]
      }
    }
    """;

    [Fact]
    public void JobInput_DeserializesFromCanonicalJson()
    {
        var job = JsonSerializer.Deserialize<JobInput>(SampleJobJson);
        Assert.NotNull(job);
        Assert.Equal("job-123", job!.JobId);
        Assert.Equal("gyroid", job.Recipe.Topology.Kind);
        Assert.Equal(10, job.Recipe.Domain.DimensionsMm.XMm);
        Assert.Equal(42, job.Recipe.Seed);
    }

    [Fact]
    public void WorkerResultOutput_RoundTripsThroughJson()
    {
        var output = new WorkerResultOutput
        {
            StlPath = "/tmp/out/scaffold.stl",
            Metrics = new GeometryMetrics { VolumeMm3 = 123.4, IsWatertight = true, TriangleCount = 10, VertexCount = 8 },
            WorkerVersion = "0.1.0",
            DotnetVersion = "9.0.18",
            PicogkVersion = "2.2.0",
            DurationSeconds = 1.5,
        };
        string json = JsonSerializer.Serialize(output);
        var roundTripped = JsonSerializer.Deserialize<WorkerResultOutput>(json);
        Assert.NotNull(roundTripped);
        Assert.Equal(output.StlPath, roundTripped!.StlPath);
        Assert.Equal(output.Metrics.VolumeMm3, roundTripped.Metrics.VolumeMm3);
    }
}
