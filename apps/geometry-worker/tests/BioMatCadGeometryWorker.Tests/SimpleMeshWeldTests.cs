using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class SimpleMeshWeldTests
{
    [Fact]
    public void Weld_CubeBuiltWithoutSharedIndices_ProducesEightUniqueVertices()
    {
        // Simula exatamente o que GyroidScaffoldBuilder recebia do PicoGK antes da correção:
        // AddTriangle(pos,pos,pos) por face, sem nenhum compartilhamento de índice --
        // 12 triângulos * 3 = 36 vértices "soltos", mas apenas 8 posições distintas.
        var raw = new SimpleMesh();
        double h = 0.5;
        (double, double, double)[] c =
        {
            (-h, -h, -h), (h, -h, -h), (h, h, -h), (-h, h, -h),
            (-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h),
        };
        int[][] faces =
        {
            new[] { 0, 1, 2 }, new[] { 0, 2, 3 },
            new[] { 4, 6, 5 }, new[] { 4, 7, 6 },
            new[] { 0, 4, 5 }, new[] { 0, 5, 1 },
            new[] { 3, 2, 6 }, new[] { 3, 6, 7 },
            new[] { 0, 3, 7 }, new[] { 0, 7, 4 },
            new[] { 1, 5, 6 }, new[] { 1, 6, 2 },
        };
        foreach (var f in faces)
        {
            var (ax, ay, az) = c[f[0]];
            var (bx, by, bz) = c[f[1]];
            var (cx, cy, cz) = c[f[2]];
            raw.AddTriangle(new Vec3(ax, ay, az), new Vec3(bx, by, bz), new Vec3(cx, cy, cz));
        }

        Assert.Equal(36, raw.Vertices.Count); // sem solda: 3 por triângulo, 12 triângulos
        Assert.False(GeometryMetricsCalculator.IsWatertight(raw), "malha crua sem solda não deveria passar no teste de watertight");

        var welded = raw.Weld();
        Assert.Equal(8, welded.Vertices.Count); // 8 posições únicas reais
        Assert.Equal(36 / 3, welded.Triangles.Count);
        Assert.True(GeometryMetricsCalculator.IsWatertight(welded), "malha soldada por posição deveria ser watertight");
    }

    [Fact]
    public void Weld_PreservesGeometricVolumeAndArea()
    {
        var raw = new SimpleMesh();
        // Um triângulo isolado replicado três vezes com posições idênticas (simula redundância).
        var a = new Vec3(0, 0, 0);
        var b = new Vec3(1, 0, 0);
        var c = new Vec3(0, 1, 0);
        for (int i = 0; i < 3; i++) raw.AddTriangle(a, b, c);

        var welded = raw.Weld();
        Assert.Equal(3, welded.Vertices.Count); // 1 posição única por vértice do triângulo (a,b,c)
        Assert.Equal(3, welded.Triangles.Count); // triângulos continuam distintos (não deduplicamos triângulos, só vértices)
    }

    [Fact]
    public void Weld_RespectsEpsilonTolerance_NearbyButDistinctPointsStaySeparate()
    {
        var raw = new SimpleMesh();
        raw.AddVertex(new Vec3(0, 0, 0));
        raw.AddVertex(new Vec3(0.01, 0, 0)); // 0.01mm de distância -- bem acima do epsilon default (1e-5)
        raw.AddTriangleByIndex(0, 1, 0);

        var welded = raw.Weld(epsilonMm: 1e-5);
        Assert.Equal(2, welded.Vertices.Count);
    }
}
