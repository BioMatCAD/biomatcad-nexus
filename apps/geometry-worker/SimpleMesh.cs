// Malha indexada simples, independente do PicoGK -- testável sem o runtime nativo bloqueado.
namespace BioMatCadGeometryWorker;

public readonly record struct Vec3(double X, double Y, double Z)
{
    public static Vec3 operator -(Vec3 a, Vec3 b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);

    public static Vec3 Cross(Vec3 a, Vec3 b) => new(
        a.Y * b.Z - a.Z * b.Y,
        a.Z * b.X - a.X * b.Z,
        a.X * b.Y - a.Y * b.X);

    public static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;

    public double Length() => Math.Sqrt(X * X + Y * Y + Z * Z);
}

public sealed class SimpleMesh
{
    public List<Vec3> Vertices { get; } = new();
    public List<(int A, int B, int C)> Triangles { get; } = new();

    public int AddVertex(Vec3 v)
    {
        Vertices.Add(v);
        return Vertices.Count - 1;
    }

    public void AddTriangleByIndex(int a, int b, int c) => Triangles.Add((a, b, c));

    /// <summary>Adiciona um triângulo por posição, sem deduplicar vértices (usado quando a
    /// origem dos dados -- ex.: PicoGK Mesh.GetTriangle -- já entrega posições, não índices).</summary>
    public void AddTriangle(Vec3 a, Vec3 b, Vec3 c)
    {
        int ia = AddVertex(a);
        int ib = AddVertex(b);
        int ic = AddVertex(c);
        AddTriangleByIndex(ia, ib, ic);
    }

    /// <summary>Cubo unitário (ou de lado arbitrário) com os 8 vértices compartilhados entre as
    /// 12 faces -- essencial para que a checagem de watertight (contagem de arestas) funcione;
    /// uma versão ingênua que chama AddTriangle(pos,pos,pos) por face criaria 36 vértices não
    /// compartilhados e o cubo pareceria não-watertight mesmo sendo fechado.</summary>
    public static SimpleMesh Box(double sizeX, double sizeY, double sizeZ)
    {
        var mesh = new SimpleMesh();
        double hx = sizeX / 2, hy = sizeY / 2, hz = sizeZ / 2;
        Vec3[] corners =
        {
            new(-hx, -hy, -hz), new(hx, -hy, -hz), new(hx, hy, -hz), new(-hx, hy, -hz),
            new(-hx, -hy, hz), new(hx, -hy, hz), new(hx, hy, hz), new(-hx, hy, hz),
        };
        foreach (var corner in corners) mesh.AddVertex(corner);

        int[][] faces =
        {
            new[] { 0, 1, 2 }, new[] { 0, 2, 3 }, // -z
            new[] { 4, 6, 5 }, new[] { 4, 7, 6 }, // +z
            new[] { 0, 4, 5 }, new[] { 0, 5, 1 }, // -y
            new[] { 3, 2, 6 }, new[] { 3, 6, 7 }, // +y
            new[] { 0, 3, 7 }, new[] { 0, 7, 4 }, // -x
            new[] { 1, 5, 6 }, new[] { 1, 6, 2 }, // +x
        };
        foreach (var f in faces) mesh.AddTriangleByIndex(f[0], f[1], f[2]);
        return mesh;
    }
}
