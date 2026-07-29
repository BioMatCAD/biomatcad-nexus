// Exportador STL binário independente do PicoGK -- testável sem o runtime nativo bloqueado.
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
}
