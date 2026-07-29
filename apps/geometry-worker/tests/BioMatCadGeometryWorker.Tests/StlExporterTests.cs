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
}
