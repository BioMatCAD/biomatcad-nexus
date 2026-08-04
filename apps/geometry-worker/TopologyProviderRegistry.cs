// Registro estático e explícito dos providers de topologia conhecidos pelo worker
// (Incremento 2.2, Seção 4).
//
// Deliberadamente NÃO usa reflection para descobrir implementações automaticamente (ex.:
// escanear o assembly por todo tipo que implemente ITopologyProvider) -- cada entrada é
// adicionada aqui manualmente e de forma auditável. Não há carregamento dinâmico de assemblies
// externos, não há eval, não há nenhuma possibilidade de um provider vir de código enviado pelo
// navegador ou por uma requisição de rede: toda topologia suportada é uma classe C# compilada
// estaticamente neste projeto.
//
// Outras topologias futuras (TPMS adicionais, híbridas, espacialmente graduadas) só devem ser
// adicionadas aqui quando tiverem uma implementação real e testada -- nunca antes.
//
// Incremento 2.2 (rodada Voronoi, Seção 8): "voronoi_cell_edges_v1" registrado como segunda
// entrada real -- struts construídos sobre as ARESTAS REAIS de uma tesselação de Voronoi 3D
// (ver docs/architecture/voronoi-cell-edges-v1-math-audit.md), nunca confundido com um grafo de
// adjacência de sítios de Delaunay.
namespace BioMatCadGeometryWorker;

public static class TopologyProviderRegistry
{
    private static readonly Dictionary<string, ITopologyProvider> _providers = new()
    {
        ["gyroid"] = new GyroidTopologyProvider(),
        ["voronoi_cell_edges_v1"] = new VoronoiTopologyProvider(),
    };

    public static bool TryGet(string kind, out ITopologyProvider? provider) =>
        _providers.TryGetValue(kind, out provider);

    public static IReadOnlyCollection<string> KnownKinds => _providers.Keys;
}
