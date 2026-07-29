using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class StlExporterTests
{
    [Fact]
    public void WriteBinary_CubeStl_HasExpectedFileSize()
    {
        var cube = SimpleMesh.Box(1, 1, 1);
        string path = Path.Combine(Path.GetTempPath(), $"biomatcad-test-{Guid.NewGuid():N}.stl");
        try
        {
            StlExporter.WriteBinary(cube, path);
            var bytes = File.ReadAllBytes(path);
            // Header (80 bytes) + contagem de triângulos (4 bytes) + 50 bytes por triângulo.
            long expected = 80 + 4 + (cube.Triangles.Count * 50L);
            Assert.Equal(expected, bytes.LongLength);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }
    [Fact]
    public void ReadBinary_RoundTripsCubeGeometry()
    {
        var cube = SimpleMesh.Box(2, 3, 4);
        string path = Path.Combine(Path.GetTempPath(), $"biomatcad-test-{Guid.NewGuid():N}.stl");
        try
        {
            StlExporter.WriteBinary(cube, path);
            var reloaded = StlExporter.ReadBinary(path);
            Assert.Equal(cube.Triangles.Count, reloaded.Triangles.Count);
            Assert.Equal(cube.Triangles.Count * 3, reloaded.Vertices.Count); // STL sempre solto, 3 por triângulo

            var weldedReloaded = reloaded.Weld();
            Assert.Equal(8, weldedReloaded.Vertices.Count); // reconstrói os 8 vértices únicos do cubo
            Assert.True(GeometryMetricsCalculator.IsWatertight(weldedReloaded));
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    [Fact]
    public void ValidateWrittenFile_ValidCube_Passes()
    {
        var cube = SimpleMesh.Box(1, 1, 1);
        string path = Path.Combine(Path.GetTempPath(), $"biomatcad-test-{Guid.NewGuid():N}.stl");
        try
        {
            StlExporter.WriteBinary(cube, path);
            var result = StlExporter.ValidateWrittenFile(path, expectedTriangleCount: cube.Triangles.Count, expectedWatertight: true);
            Assert.True(result.Passed, result.FailureReason);
            Assert.Equal(8, result.ReloadedUniqueVertexCount);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    [Fact]
    public void ValidateWrittenFile_WrongExpectedTriangleCount_Fails()
    {
        var cube = SimpleMesh.Box(1, 1, 1);
        string path = Path.Combine(Path.GetTempPath(), $"biomatcad-test-{Guid.NewGuid():N}.stl");
        try
        {
            StlExporter.WriteBinary(cube, path);
            var result = StlExporter.ValidateWrittenFile(path, expectedTriangleCount: 999, expectedWatertight: true);
            Assert.False(result.Passed);
            Assert.NotNull(result.FailureReason);
        }
        finally
        {
            if (File.Exists(path)) File.Delete(path);
        }
    }

    [Fact]
    public void ComputeSha256Hex_IsDeterministicForSameContent()
    {
        var cube = SimpleMesh.Box(1, 1, 1);
        string path1 = Path.Combine(Path.GetTempPath(), $"biomatcad-test-{Guid.NewGuid():N}.stl");
        string path2 = Path.Combine(Path.GetTempPath(), $"biomatcad-test-{Guid.NewGuid():N}.stl");
        try
        {
            StlExporter.WriteBinary(cube, path1);
            StlExporter.WriteBinary(cube, path2);
            string hash1 = StlExporter.ComputeSha256Hex(path1);
            string hash2 = StlExporter.ComputeSha256Hex(path2);
            Assert.Equal(hash1, hash2);
            Assert.Equal(64, hash1.Length); // hex sha256
        }
        finally
        {
            if (File.Exists(path1)) File.Delete(path1);
            if (File.Exists(path2)) File.Delete(path2);
        }
    }
}