using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

// Testes do contrato ITopologyProvider / TopologyProviderRegistry (Incremento 2.2, Seção 4).
// Cobre exatamente o que foi pedido: Gyroid registrado como implementação real, rejeição de
// provider desconhecido, e a versão exposta -- que precisa bater com a string espelhada em
// apps/api/src/biomatcad_api/services/topology_providers.py::_REGISTRY["gyroid"].version.
public class TopologyProviderRegistryTests
{
    [Fact]
    public void TryGet_Gyroid_RetornaOProviderRealRegistrado()
    {
        bool found = TopologyProviderRegistry.TryGet("gyroid", out var provider);

        Assert.True(found);
        Assert.NotNull(provider);
        Assert.IsType<GyroidTopologyProvider>(provider);
        Assert.Equal("gyroid", provider!.Kind);
    }

    [Fact]
    public void TryGet_KindDesconhecido_RetornaFalse()
    {
        // Regressão direta pedida no escopo: "rejeite provider/topologia desconhecida" -- nunca
        // deve haver um provider "default" ou silencioso para um kind não registrado.
        bool found = TopologyProviderRegistry.TryGet("voronoi", out var provider);

        Assert.False(found);
        Assert.Null(provider);
    }

    [Fact]
    public void TryGet_StringVazia_RetornaFalse()
    {
        bool found = TopologyProviderRegistry.TryGet("", out var provider);

        Assert.False(found);
        Assert.Null(provider);
    }

    [Fact]
    public void KnownKinds_ContemGyroidEVoronoiCellEdgesV1NestaRodada()
    {
        // Incremento 2.2 (rodada Voronoi, Secao 8): "voronoi_cell_edges_v1" passa a ser a
        // segunda entrada REAL do registro (implementacao real testada por tras, ver
        // VoronoiScaffoldBuilder.cs/VoronoiTopologyProvider.cs) -- o placeholder bare "voronoi"
        // (reservado, nunca implementado nesta rodada) continua deliberadamente ausente.
        var kinds = TopologyProviderRegistry.KnownKinds;

        Assert.Contains("gyroid", kinds);
        Assert.Contains("voronoi_cell_edges_v1", kinds);
        Assert.DoesNotContain("voronoi", kinds);
        Assert.Equal(2, kinds.Count);
    }

    [Fact]
    public void GyroidTopologyProvider_VersaoBateComORegistroPythonEspelhado()
    {
        // Mantido em sincronia manual com
        // apps/api/src/biomatcad_api/services/topology_providers.py::_REGISTRY["gyroid"].version
        // -- se um dos dois lados mudar sem o outro, este teste (e o equivalente Python) falha.
        var provider = new GyroidTopologyProvider();

        Assert.Equal("gyroid", provider.Kind);
        Assert.Equal("1.0.0", provider.ProviderVersion);
    }

    [Fact]
    public void TryGet_VoronoiCellEdgesV1_RetornaOProviderRealRegistrado()
    {
        bool found = TopologyProviderRegistry.TryGet("voronoi_cell_edges_v1", out var provider);

        Assert.True(found);
        Assert.NotNull(provider);
        Assert.IsType<VoronoiTopologyProvider>(provider);
        Assert.Equal("voronoi_cell_edges_v1", provider!.Kind);
    }

    [Fact]
    public void VoronoiTopologyProvider_VersaoBateComORegistroPythonEspelhado()
    {
        // Mantido em sincronia manual com
        // apps/api/src/biomatcad_api/services/topology_providers.py::_REGISTRY["voronoi_cell_edges_v1"].version
        // -- se um dos dois lados mudar sem o outro, este teste (e o equivalente Python) falha.
        var provider = new VoronoiTopologyProvider();

        Assert.Equal("voronoi_cell_edges_v1", provider.Kind);
        Assert.Equal("0.1.0", provider.ProviderVersion);
    }
}
