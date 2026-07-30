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
    public void KnownKinds_ContemApenasGyroidNestaRodada()
    {
        // Não implemente Voronoi completo ainda -- o registro real só pode conter o que
        // realmente tem uma implementação testada por trás.
        var kinds = TopologyProviderRegistry.KnownKinds;

        Assert.Contains("gyroid", kinds);
        Assert.DoesNotContain("voronoi", kinds);
        Assert.Single(kinds);
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
}
