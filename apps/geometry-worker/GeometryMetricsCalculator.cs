// Métricas geométricas independentes do PicoGK -- testáveis sem o runtime nativo bloqueado.
namespace BioMatCadGeometryWorker;

public static class GeometryMetricsCalculator
{
    public static (Vec3 Min, Vec3 Max) ComputeBoundingBox(SimpleMesh mesh)
    {
        if (mesh.Vertices.Count == 0) return (new Vec3(0, 0, 0), new Vec3(0, 0, 0));
        double minX = double.MaxValue, minY = double.MaxValue, minZ = double.MaxValue;
        double maxX = double.MinValue, maxY = double.MinValue, maxZ = double.MinValue;
        foreach (var v in mesh.Vertices)
        {
            minX = Math.Min(minX, v.X); minY = Math.Min(minY, v.Y); minZ = Math.Min(minZ, v.Z);
            maxX = Math.Max(maxX, v.X); maxY = Math.Max(maxY, v.Y); maxZ = Math.Max(maxZ, v.Z);
        }
        return (new Vec3(minX, minY, minZ), new Vec3(maxX, maxY, maxZ));
    }

    /// <summary>Volume por soma de tetraedros assinados a partir da origem -- independente da
    /// orientação de winding (retorna o valor absoluto), válido para qualquer malha fechada.</summary>
    public static double ComputeVolumeMm3(SimpleMesh mesh)
    {
        double sum = 0;
        foreach (var (ia, ib, ic) in mesh.Triangles)
        {
            var a = mesh.Vertices[ia];
            var b = mesh.Vertices[ib];
            var c = mesh.Vertices[ic];
            sum += Vec3.Dot(a, Vec3.Cross(b, c)) / 6.0;
        }
        return Math.Abs(sum);
    }

    public static double ComputeSurfaceAreaMm2(SimpleMesh mesh)
    {
        double area = 0;
        foreach (var (ia, ib, ic) in mesh.Triangles)
        {
            var a = mesh.Vertices[ia];
            var b = mesh.Vertices[ib];
            var c = mesh.Vertices[ic];
            var cross = Vec3.Cross(b - a, c - a);
            area += 0.5 * cross.Length();
        }
        return area;
    }

    /// <summary>Malha é watertight se toda aresta (não-direcionada) aparece em exatamente 2
    /// triângulos -- um teste simples mas real de fechamento topológico.</summary>
    public static bool IsWatertight(SimpleMesh mesh)
    {
        var edgeCounts = new Dictionary<(int, int), int>();
        void AddEdge(int u, int v)
        {
            var key = u < v ? (u, v) : (v, u);
            edgeCounts[key] = edgeCounts.GetValueOrDefault(key, 0) + 1;
        }
        foreach (var (a, b, c) in mesh.Triangles)
        {
            AddEdge(a, b);
            AddEdge(b, c);
            AddEdge(c, a);
        }
        return edgeCounts.Count > 0 && edgeCounts.Values.All(count => count == 2);
    }

    public static double ComputeDomainVolumeMm3(RecipeDomain domain)
    {
        var d = domain.DimensionsMm;
        return domain.Shape switch
        {
            "block" => (d.XMm ?? 0) * (d.YMm ?? 0) * (d.ZMm ?? 0),
            "cylinder" => Math.PI * Math.Pow(d.RadiusMm ?? 0, 2) * (d.HeightMm ?? 0),
            _ => 0,
        };
    }

    public static double EstimatePorosityPct(double scaffoldSolidVolumeMm3, double domainVolumeMm3)
    {
        if (domainVolumeMm3 <= 0) return 0;
        double porosity = (1.0 - scaffoldSolidVolumeMm3 / domainVolumeMm3) * 100.0;
        return Math.Clamp(porosity, 0.0, 100.0);
    }

    /// <summary>Calcula todas as métricas sobre a malha REALMENTE gerada. Solda os vértices
    /// primeiro (ver SimpleMesh.Weld) -- isto é o que corrige a divergência da auditoria entre
    /// "vértices" do STL e do manifesto: ambos agora vêm da mesma malha soldada por posição
    /// (Incremento 2.1.1, itens 2 e 11). A malha soldada também é a única sobre a qual o teste
    /// de watertight faz sentido (arestas compartilhadas por índice).</summary>
    public static GeometryMetrics ComputeAll(SimpleMesh rawMesh, RecipeDomain domain, double weldEpsilonMm = 1e-5)
    {
        var mesh = rawMesh.Weld(weldEpsilonMm);
        var (min, max) = ComputeBoundingBox(mesh);
        double volume = ComputeVolumeMm3(mesh);
        double domainVolume = ComputeDomainVolumeMm3(domain);
        return new GeometryMetrics
        {
            BoundingBoxMm = new[] { new[] { min.X, min.Y, min.Z }, new[] { max.X, max.Y, max.Z } },
            VolumeMm3 = volume,
            SurfaceAreaMm2 = ComputeSurfaceAreaMm2(mesh),
            VertexCountUnique = mesh.Vertices.Count,
            TriangleCount = mesh.Triangles.Count,
            IsWatertight = IsWatertight(mesh),
            PorosityPctMeasured = EstimatePorosityPct(volume, domainVolume),
            StlReloadValidationPassed = false, // preenchido por StlExporter.ValidateWrittenFile após a gravação
        };
    }
}
