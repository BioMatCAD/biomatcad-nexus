// Exportador/leitor STL binário independente do PicoGK -- testável sem o runtime nativo bloqueado.
namespace BioMatCadGeometryWorker;

public static class StlExporter
{
    public static void WriteBinary(SimpleMesh mesh, string path)
    {
        using var stream = new FileStream(path, FileMode.Create, FileAccess.Write);
        using var writer = new BinaryWriter(stream);

        var header = new byte[80];
        var headerText = System.Text.Encoding.ASCII.GetBytes("BioMatCAD Nexus BioMatCEM STL export");
        Array.Copy(headerText, header, Math.Min(headerText.Length, 80));
        writer.Write(header);

        writer.Write((uint)mesh.Triangles.Count);

        foreach (var (ia, ib, ic) in mesh.Triangles)
        {
            var a = mesh.Vertices[ia];
            var b = mesh.Vertices[ib];
            var c = mesh.Vertices[ic];
            var normal = Vec3.Cross(b - a, c - a);
            double len = normal.Length();
            if (len > 1e-12) normal = new Vec3(normal.X / len, normal.Y / len, normal.Z / len);

            writer.Write((float)normal.X); writer.Write((float)normal.Y); writer.Write((float)normal.Z);
            writer.Write((float)a.X); writer.Write((float)a.Y); writer.Write((float)a.Z);
            writer.Write((float)b.X); writer.Write((float)b.Y); writer.Write((float)b.Z);
            writer.Write((float)c.X); writer.Write((float)c.Y); writer.Write((float)c.Z);
            writer.Write((ushort)0); // attribute byte count
        }
    }

    /// <summary>Lê de volta um STL binário como uma malha CRUA (3 vértices soltos por triângulo,
    /// como qualquer leitor externo obteria do próprio formato -- ver SimpleMesh.Weld para a
    /// deduplicação). Usado tanto pela validação pós-gravação quanto por ferramentas de
    /// auditoria/teste.</summary>
    public static SimpleMesh ReadBinary(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read);
        using var reader = new BinaryReader(stream);

        _ = reader.ReadBytes(80); // header, não usado
        uint triangleCount = reader.ReadUInt32();

        var mesh = new SimpleMesh();
        for (uint i = 0; i < triangleCount; i++)
        {
            _ = reader.ReadSingle(); _ = reader.ReadSingle(); _ = reader.ReadSingle(); // normal (recalculado, não confiável)
            double ax = reader.ReadSingle(), ay = reader.ReadSingle(), az = reader.ReadSingle();
            double bx = reader.ReadSingle(), by = reader.ReadSingle(), bz = reader.ReadSingle();
            double cx = reader.ReadSingle(), cy = reader.ReadSingle(), cz = reader.ReadSingle();
            _ = reader.ReadUInt16(); // attribute byte count
            mesh.AddTriangle(new Vec3(ax, ay, az), new Vec3(bx, by, bz), new Vec3(cx, cy, cz));
        }
        return mesh;
    }

    public sealed class StlValidationResult
    {
        public bool Passed { get; init; }
        public string? FailureReason { get; init; }
        public int ReloadedTriangleCount { get; init; }
        public int ReloadedUniqueVertexCount { get; init; }
        public bool ReloadedIsWatertight { get; init; }
    }

    /// <summary>Validação pós-gravação (item 2: "validar o STL após a gravação"): relê o arquivo
    /// escrito em disco, reconta triângulos, solda vértices e recalcula watertight -- e compara
    /// contra os valores esperados calculados a partir da malha em memória ANTES da escrita. Se
    /// divergirem, é sinal de corrupção na gravação/leitura, não apenas um "trust me".</summary>
    public static StlValidationResult ValidateWrittenFile(string path, int expectedTriangleCount, bool expectedWatertight)
    {
        SimpleMesh reloaded;
        try
        {
            reloaded = ReadBinary(path);
        }
        catch (Exception ex)
        {
            return new StlValidationResult { Passed = false, FailureReason = $"Falha ao reler STL gravado: {ex.Message}" };
        }

        if (reloaded.Triangles.Count != expectedTriangleCount)
        {
            return new StlValidationResult
            {
                Passed = false,
                FailureReason = $"Contagem de triângulos divergente: esperado {expectedTriangleCount}, lido {reloaded.Triangles.Count}.",
                ReloadedTriangleCount = reloaded.Triangles.Count,
            };
        }

        var welded = reloaded.Weld();
        bool watertight = GeometryMetricsCalculator.IsWatertight(welded);
        if (watertight != expectedWatertight)
        {
            return new StlValidationResult
            {
                Passed = false,
                FailureReason = $"Watertight divergente após releitura: esperado {expectedWatertight}, obtido {watertight}.",
                ReloadedTriangleCount = reloaded.Triangles.Count,
                ReloadedUniqueVertexCount = welded.Vertices.Count,
                ReloadedIsWatertight = watertight,
            };
        }

        return new StlValidationResult
        {
            Passed = true,
            ReloadedTriangleCount = reloaded.Triangles.Count,
            ReloadedUniqueVertexCount = welded.Vertices.Count,
            ReloadedIsWatertight = watertight,
        };
    }

    public static string ComputeSha256Hex(string path)
    {
        using var sha = System.Security.Cryptography.SHA256.Create();
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read);
        byte[] hash = sha.ComputeHash(stream);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }
}
