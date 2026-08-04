// Testes de regressão do contrato JSON após a generalização de ITopologyProvider.BuildAndExport
// para TopologyBuildResult (Incremento 2.2, Seção 8) -- provam que o refactor NÃO alterou o
// formato de saída já aprovado para o Gyroid (3 golden recipes), e que o novo caminho Voronoi
// produz o formato esperado (campos comuns + Extra).
//
// Como este projeto referencia o worker inteiro via ProjectReference (mesmo padrão já usado
// pelos demais testes deste projeto) mas NUNCA chama BuildAndExport (que exigiria o runtime
// nativo do PicoGK, indisponível neste sandbox -- ver ADR-0007), a JIT preguiçosa do .NET nunca
// toca PicoGK.Library/Voxels/Mesh: construímos os objetos BuildResult "à mão" (são POCOs
// simples) e exercitamos apenas DescribeEffectiveParameters/PopulateMetricsExtra, que são pura
// lógica de dados.
using System.Text.Json;
using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class TopologyBuildResultContractTests
{
    private static JobInput MakeGyroidJob() => new()
    {
        JobId = "job-1",
        OutputDir = "/tmp/whatever",
        Recipe = new RecipeCanonical
        {
            SchemaVersion = "1.0.0",
            Seed = 42,
            Mode = "final",
            Domain = new RecipeDomain { Shape = "block", DimensionsMm = new RecipeDimensions { Kind = "block", XMm = 10, YMm = 10, ZMm = 10 } },
            Topology = new RecipeTopology { Kind = "gyroid", CellSizeMm = 3.0, WallThicknessMm = 0.4, Isovalue = 0.0, TargetPorosityPct = 60.0 },
            Resolution = new RecipeResolution { VoxelSizeMm = 0.2 },
            ComputeLimits = new RecipeComputeLimits { MaxDurationSeconds = 60, MaxMemoryMb = 512, MaxVoxelCount = 2_000_000 },
            OutputFormats = new List<string> { "stl" },
        },
    };

    [Fact]
    public void Gyroid_DescribeEffectiveParameters_ProduzExatamenteOsCamposEsperadosSemChaveExtra()
    {
        var job = MakeGyroidJob();
        var buildResult = new GyroidScaffoldBuilder.BuildResult
        {
            Mesh = new SimpleMesh(),
            AnalyticalPorosityCalibration = null,
            MeshPorosityCalibration = new GyroidMath.MonotonicCalibrationResult
            {
                Converged = true,
                EffectiveWallThicknessMm = 0.42,
                MeasuredPorosityPct = 60.5,
                ResidualErrorPctPoints = 0.5,
                ToleranceUsedPctPoints = 2.0,
                Iterations = 5,
            },
            PorosityToleranceUsedPctPoints = 2.0,
            EffectiveWallThicknessMm = 0.42,
            IsovalueCenter = 0.0,
            SeedPhaseShiftRad = 1.23,
            VoxelSizeEffectiveMm = 0.2,
        };
        var measuredMetrics = new GeometryMetrics { PorosityPctMeasured = 60.5 };

        var provider = new GyroidTopologyProvider();
        var effectiveParameters = provider.DescribeEffectiveParameters(job, buildResult, measuredMetrics, estimatedVoxelCount: 125000, estimatedMemoryMb: 4.0);

        // Valores -- prova de que a lógica movida de Program.cs continua computando IGUAL.
        Assert.Equal(0.4, effectiveParameters.WallThicknessRequestedMm);
        Assert.Equal(0.42, effectiveParameters.WallThicknessEffectiveMm);
        Assert.Equal(0.0, effectiveParameters.IsovalueCenter);
        Assert.Equal(60.0, effectiveParameters.TargetPorosityPctRequested);
        Assert.Equal(60.5, effectiveParameters.MeasuredPorosityPct);
        Assert.Equal(0.5, effectiveParameters.MeasuredPorosityErrorPctPoints);
        Assert.True(effectiveParameters.MeasuredPorosityWithinTolerance);
        Assert.Equal(5, effectiveParameters.MeshCalibrationIterations);
        Assert.Equal(42, effectiveParameters.Seed);
        Assert.Equal(1.23, effectiveParameters.SeedPhaseShiftRad);
        Assert.Equal("final", effectiveParameters.Mode);
        Assert.Equal(125000, effectiveParameters.EstimatedVoxelCount);

        // Contrato JSON -- Extra deve ficar nulo (Gyroid nunca o preenche) e portanto NENHUMA
        // chave nova deve aparecer no JSON serializado -- prova de que o refactor da Seção 8 é
        // 100% aditivo/transparente para o formato já aprovado das 3 golden recipes.
        Assert.Null(effectiveParameters.Extra);
        string json = JsonSerializer.Serialize(effectiveParameters);
        Assert.DoesNotContain("\"Extra\"", json);
        Assert.DoesNotContain("site_count", json);
    }

    [Fact]
    public void Gyroid_PopulateMetricsExtra_NaoAlteraMetricsExtra()
    {
        var buildResult = new GyroidScaffoldBuilder.BuildResult { Mesh = new SimpleMesh() };
        var metrics = new GeometryMetrics { VolumeMm3 = 123.0 };

        new GyroidTopologyProvider().PopulateMetricsExtra(metrics, buildResult);

        Assert.Null(metrics.Extra);
        string json = JsonSerializer.Serialize(metrics);
        Assert.DoesNotContain("\"Extra\"", json);
    }

    private static JobInput MakeVoronoiJob() => new()
    {
        JobId = "job-2",
        OutputDir = "/tmp/whatever",
        Recipe = new RecipeCanonical
        {
            SchemaVersion = "1.0.0",
            Seed = 7,
            Mode = "preview",
            Domain = new RecipeDomain { Shape = "block", DimensionsMm = new RecipeDimensions { Kind = "block", XMm = 10, YMm = 10, ZMm = 10 } },
            Topology = new RecipeTopology
            {
                Kind = "voronoi_cell_edges_v1",
                SiteCount = 10,
                Distribution = "uniform_random",
                StrutRadiusMm = 0.3,
                NodeSmoothing = 0.5,
                NodeRadiusFactor = 1.3,
                TargetPorosityPct = 70.0,
            },
            Resolution = new RecipeResolution { VoxelSizeMm = 0.3 },
            ComputeLimits = new RecipeComputeLimits { MaxDurationSeconds = 60, MaxMemoryMb = 512, MaxVoxelCount = 2_000_000 },
            OutputFormats = new List<string> { "stl" },
        },
    };

    [Fact]
    public void Voronoi_DescribeEffectiveParameters_PreenchemComunsENaoTocaCamposGyroidEspecificos()
    {
        var job = MakeVoronoiJob();
        var siteResult = new VoronoiSiteGenerator.SiteGenerationResult
        {
            Sites = new List<Vec3> { new(0, 0, 0), new(1, 1, 1), new(2, 2, 2), new(-1, -1, -1) },
            SitesSha256 = "abc123",
            RequestedSiteCount = 10,
            RejectedAttempts = 3,
            MinSeparationMmUsed = 0.5,
        };
        var tessellation = new VoronoiTessellationResult
        {
            Nodes = new List<Vec3> { new(0.5, 0.5, 0.5), new(1.5, 1.5, 1.5) },
            Edges = new List<(int, int)> { (0, 1) },
            SiteCount = 4,
            DelaunayCellCount = 2,
            DegenerateCellCount = 0,
            InternalEdgeCount = 1,
            BoundaryRayEdgeCount = 0,
            ConnectedComponentCount = 1,
            IsolatedNodeCount = 0,
            NodesAndEdgesSha256 = "def456",
        };
        var buildResult = new VoronoiScaffoldBuilder.BuildResult
        {
            Mesh = new SimpleMesh(),
            SiteGeneration = siteResult,
            Tessellation = tessellation,
            MeshPorosityCalibration = null,
            PorosityToleranceUsedPctPoints = 5.0,
            StrutRadiusRequestedMm = 0.3,
            StrutRadiusEffectiveMm = 0.3,
            NodeRadiusEffectiveMm = 0.39,
            NodeSmoothingLengthMm = 0.15,
            VoxelSizeEffectiveMm = 0.3,
        };
        var measuredMetrics = new GeometryMetrics { PorosityPctMeasured = 68.0 };

        var provider = new VoronoiTopologyProvider();
        var effectiveParameters = provider.DescribeEffectiveParameters(job, buildResult, measuredMetrics, estimatedVoxelCount: 37000, estimatedMemoryMb: 1.5);

        // Campos comuns preenchidos corretamente.
        Assert.Equal(70.0, effectiveParameters.TargetPorosityPctRequested);
        Assert.Equal(7, effectiveParameters.Seed);
        Assert.Equal("preview", effectiveParameters.Mode);
        Assert.Equal(37000, effectiveParameters.EstimatedVoxelCount);

        // Campos Gyroid-específicos permanecem em seus defaults -- NUNCA preenchidos pelo
        // provider Voronoi (documentado explicitamente no cabeçalho de VoronoiTopologyProvider.cs).
        Assert.Equal(0.0, effectiveParameters.WallThicknessRequestedMm);
        Assert.Equal(0.0, effectiveParameters.WallThicknessEffectiveMm);
        Assert.Equal(0.0, effectiveParameters.IsovalueCenter);
        Assert.Equal(0.0, effectiveParameters.SeedPhaseShiftRad);
        Assert.Null(effectiveParameters.AnalyticalPorosityEstimatePct);

        // Extra populado com os campos específicos do Voronoi.
        Assert.NotNull(effectiveParameters.Extra);
        Assert.Equal(10, effectiveParameters.Extra!["site_count_requested"]);
        Assert.Equal(4, effectiveParameters.Extra!["site_count_effective"]);
        Assert.Equal("uniform_random", effectiveParameters.Extra!["distribution_used"]);
        Assert.Equal("abc123", effectiveParameters.Extra!["sites_sha256"]);
        Assert.Equal("def456", effectiveParameters.Extra!["nodes_and_edges_sha256"]);

        // Contrato JSON -- as chaves Extra devem aparecer como IRMÃS no JSON, não aninhadas sob
        // uma chave "Extra"/"extra".
        string json = JsonSerializer.Serialize(effectiveParameters);
        Assert.Contains("\"site_count_requested\":10", json);
        Assert.DoesNotContain("\"Extra\":{", json);
        Assert.DoesNotContain("\"extra\":{", json);
    }

    [Fact]
    public void Voronoi_PopulateMetricsExtra_PreencheContagensComprimentosEGraus()
    {
        var tessellation = new VoronoiTessellationResult
        {
            Nodes = new List<Vec3> { new(0, 0, 0), new(3, 4, 0), new(3, 4, 12) },
            Edges = new List<(int, int)> { (0, 1), (1, 2) }, // comprimentos: 5.0 e 12.0
            SiteCount = 6,
            DelaunayCellCount = 3,
            DegenerateCellCount = 1,
            InternalEdgeCount = 2,
            BoundaryRayEdgeCount = 0,
            ConnectedComponentCount = 1,
            IsolatedNodeCount = 0,
            NodesAndEdgesSha256 = "xyz",
        };
        var buildResult = new VoronoiScaffoldBuilder.BuildResult
        {
            Mesh = new SimpleMesh(),
            SiteGeneration = new VoronoiSiteGenerator.SiteGenerationResult { Sites = Array.Empty<Vec3>() },
            Tessellation = tessellation,
        };
        var metrics = new GeometryMetrics();

        new VoronoiTopologyProvider().PopulateMetricsExtra(metrics, buildResult);

        Assert.NotNull(metrics.Extra);
        Assert.Equal(6, metrics.Extra!["site_count"]);
        Assert.Equal(3, metrics.Extra!["node_count"]);
        Assert.Equal(2, metrics.Extra!["edge_count"]);
        Assert.Equal(17.0, (double)metrics.Extra!["total_strut_length_mm"]!, 6); // 5 + 12
        Assert.Equal(8.5, (double)metrics.Extra!["mean_strut_length_mm"]!, 6);
        Assert.Equal(5.0, (double)metrics.Extra!["min_strut_length_mm"]!, 6);
        Assert.Equal(12.0, (double)metrics.Extra!["max_strut_length_mm"]!, 6);
        // Graus: nó 0 tem grau 1, nó 1 tem grau 2 (compartilhado pelas 2 arestas), nó 2 tem grau 1.
        Assert.Equal(4.0 / 3.0, (double)metrics.Extra!["mean_node_degree"]!, 6);
    }
}
