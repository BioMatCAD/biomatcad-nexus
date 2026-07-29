using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class GeometryMetricsCalculatorTests
{
    [Fact]
    public void UnitCube_HasVolumeOneAreaSixAndIsWatertight()
    {
        var cube = SimpleMesh.Box(1, 1, 1);
        Assert.Equal(8, cube.Vertices.Count);
        Assert.Equal(12, cube.Triangles.Count);
        Assert.Equal(1.0, GeometryMetricsCalculator.ComputeVolumeMm3(cube), 6);
        Assert.Equal(6.0, GeometryMetricsCalculator.ComputeSurfaceAreaMm2(cube), 6);
        Assert.True(GeometryMetricsCalculator.IsWatertight(cube));
    }

    [Fact]
    public void BoundingBox_MatchesCubeExtents()
    {
        var cube = SimpleMesh.Box(2, 4, 6);
        var (min, max) = GeometryMetricsCalculator.ComputeBoundingBox(cube);
        Assert.Equal(-1.0, min.X, 6); Assert.Equal(1.0, max.X, 6);
        Assert.Equal(-2.0, min.Y, 6); Assert.Equal(2.0, max.Y, 6);
        Assert.Equal(-3.0, min.Z, 6); Assert.Equal(3.0, max.Z, 6);
    }

    [Fact]
    public void PorosityEstimate_HalfSolidVolume_Is50Percent()
    {
        double porosity = GeometryMetricsCalculator.EstimatePorosityPct(scaffoldSolidVolumeMm3: 500, domainVolumeMm3: 1000);
        Assert.Equal(50.0, porosity, 6);
    }

    [Fact]
    public void PorosityEstimate_IsClampedToZeroAndHundred()
    {
        Assert.Equal(0.0, GeometryMetricsCalculator.EstimatePorosityPct(2000, 1000), 6);
        Assert.Equal(100.0, GeometryMetricsCalculator.EstimatePorosityPct(-10, 1000), 6);
    }

    [Fact]
    public void DomainVolume_BlockAndCylinder_ComputeCorrectly()
    {
        var block = new RecipeDomain
        {
            Shape = "block",
            DimensionsMm = new RecipeDimensions { Kind = "block", XMm = 2, YMm = 3, ZMm = 4 },
        };
        Assert.Equal(24.0, GeometryMetricsCalculator.ComputeDomainVolumeMm3(block), 6);

        var cylinder = new RecipeDomain
        {
            Shape = "cylinder",
            DimensionsMm = new RecipeDimensions { Kind = "cylinder", RadiusMm = 1, HeightMm = 10 },
        };
        Assert.Equal(Math.PI * 1 * 1 * 10, GeometryMetricsCalculator.ComputeDomainVolumeMm3(cylinder), 6);
    }

    [Fact]
    public void SingleTriangle_IsNotWatertight()
    {
        var mesh = new SimpleMesh();
        mesh.AddTriangle(new Vec3(0, 0, 0), new Vec3(1, 0, 0), new Vec3(0, 1, 0));
        Assert.False(GeometryMetricsCalculator.IsWatertight(mesh));
    }
    [Fact]
    public void ComputeAll_WeldsBeforeReportingUniqueVertexCount()
    {
        // Reproduz o cenário exato da auditoria: malha crua vinda de GetTriangle (sem solda).
        var raw = new SimpleMesh();
        var a = new Vec3(0, 0, 0);
        var b = new Vec3(1, 0, 0);
        var c = new Vec3(0, 1, 0);
        var d = new Vec3(1, 1, 0);
        raw.AddTriangle(a, b, c);
        raw.AddTriangle(b, d, c);

        var domain = new RecipeDomain { Shape = "block", DimensionsMm = new RecipeDimensions { Kind = "block", XMm = 1, YMm = 1, ZMm = 1 } };
        var metrics = GeometryMetricsCalculator.ComputeAll(raw, domain);

        Assert.Equal(4, metrics.VertexCountUnique); // a,b,c,d únicos -- não 6 (2 triângulos * 3)
        Assert.Equal(2, metrics.TriangleCount);
    }
}