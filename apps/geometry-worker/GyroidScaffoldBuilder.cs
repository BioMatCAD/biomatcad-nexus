// Geração real do scaffold Gyroid via PicoGK (LEAP 71, Apache-2.0) -- ver NOTICE.
// Fórmula da superfície mínima periódica (TPMS) de Alan Schoen (1970), domínio público:
//   sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x) = isovalue
// Este arquivo é DEPENDENTE do runtime nativo do PicoGK (libpicogk), que não está disponível
// para linux-x64 no pacote 2.2.0 (ver WORKER_STATUS.md/ADR-0007) -- compila, mas sua execução
// real não pôde ser verificada neste sandbox.
using System.Numerics;
using PicoGK;

namespace BioMatCadGeometryWorker;

public sealed class GyroidImplicit : IImplicit
{
    private readonly double _cellSizeMm;
    private readonly double _isovalue;

    public GyroidImplicit(double cellSizeMm, double isovalue)
    {
        _cellSizeMm = cellSizeMm;
        _isovalue = isovalue;
    }

    public float fSignedDistance(in Vector3 vec)
    {
        double scale = 2.0 * Math.PI / _cellSizeMm;
        double x = vec.X * scale, y = vec.Y * scale, z = vec.Z * scale;
        double gyroid = Math.Sin(x) * Math.Cos(y) + Math.Sin(y) * Math.Cos(z) + Math.Sin(z) * Math.Cos(x);
        // Aproximação de distância assinada -- suficiente para voxelização por isosuperfície,
        // não uma distância euclidiana exata à superfície gyroid (que não tem forma fechada).
        return (float)((gyroid - _isovalue) * (_cellSizeMm / (2.0 * Math.PI)));
    }
}

public static class GyroidScaffoldBuilder
{
    public sealed class BuildResult
    {
        public SimpleMesh Mesh { get; init; } = new();
    }

    public static BuildResult BuildAndExport(JobInput job, string stlOutputPath)
    {
        var recipe = job.Recipe;
        var domain = recipe.Domain;
        var topology = recipe.Topology;
        double voxelSizeMm = recipe.Resolution.VoxelSizeMm;

        SimpleMesh? resultMesh = null;

        Library.Go((float)voxelSizeMm, () =>
        {
            BBox3 bounds = domain.Shape switch
            {
                "block" => new BBox3(
                    new Vector3((float)-(domain.DimensionsMm.XMm!.Value / 2), (float)-(domain.DimensionsMm.YMm!.Value / 2), (float)-(domain.DimensionsMm.ZMm!.Value / 2)),
                    new Vector3((float)(domain.DimensionsMm.XMm!.Value / 2), (float)(domain.DimensionsMm.YMm!.Value / 2), (float)(domain.DimensionsMm.ZMm!.Value / 2))),
                "cylinder" => new BBox3(
                    new Vector3((float)-domain.DimensionsMm.RadiusMm!.Value, (float)-domain.DimensionsMm.RadiusMm!.Value, 0f),
                    new Vector3((float)domain.DimensionsMm.RadiusMm!.Value, (float)domain.DimensionsMm.RadiusMm!.Value, (float)domain.DimensionsMm.HeightMm!.Value)),
                _ => throw new NotSupportedException($"Domínio não suportado: {domain.Shape}"),
            };

            var gyroidImplicit = new GyroidImplicit(topology.CellSizeMm, topology.Isovalue);
            var voxels = new Voxels(gyroidImplicit, bounds);
            var mesh = new Mesh(voxels);

            mesh.SaveToStlFile(stlOutputPath);

            var simpleMesh = new SimpleMesh();
            int triangleCount = mesh.nTriangleCount();
            for (int i = 0; i < triangleCount; i++)
            {
                mesh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
                simpleMesh.AddTriangle(new Vec3(a.X, a.Y, a.Z), new Vec3(b.X, b.Y, b.Z), new Vec3(c.X, c.Y, c.Z));
            }
            resultMesh = new SimpleMesh();
            resultMesh.Vertices.AddRange(simpleMesh.Vertices);
            resultMesh.Triangles.AddRange(simpleMesh.Triangles);
        });

        return new BuildResult { Mesh = resultMesh ?? new SimpleMesh() };
    }
}
