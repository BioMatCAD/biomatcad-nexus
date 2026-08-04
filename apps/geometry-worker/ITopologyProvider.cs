// Contrato versionado e explícito de topologia (Incremento 2.2, Seção 4; generalizado na Seção 8
// para suportar um segundo provider real, Voronoi).
//
// Permite registrar novas topologias (outras TPMS, Voronoi, híbridas, espacialmente graduadas)
// sem alterar o fluxo de projeto/receita/job/artefato/visualização -- o único ponto de mudança
// é adicionar uma nova classe que implemente esta interface e registrá-la em
// TopologyProviderRegistry.
//
// Deliberadamente NÃO há nenhum mecanismo de carregamento dinâmico: nenhuma reflection insegura
// para descobrir implementações automaticamente, nenhum carregamento de assembly externo em
// tempo de execução, nenhum eval, nenhuma possibilidade de um provider vir de código enviado
// pelo navegador ou por uma requisição HTTP. Toda implementação de ITopologyProvider é código
// C# compilado estaticamente neste mesmo assembly, revisado como qualquer outro código do
// worker.
//
// Incremento 2.2, Seção 8: BuildAndExport agora retorna o tipo abstrato TopologyBuildResult (em
// vez do antigo GyroidScaffoldBuilder.BuildResult concreto) -- generalização necessária para o
// segundo provider real (Voronoi). Para que Program.cs permaneça 100% genérico (nenhum "if"
// disperso por topology.kind ao montar a saída), duas responsabilidades que antes viviam
// hardcoded em Program.cs foram movidas PARA DENTRO de cada provider concreto, que conhece seu
// próprio tipo de resultado e pode fazer o downcast internamente (sempre seguro, pois cada
// provider só recebe de volta o resultado que ele mesmo produziu):
//   - DescribeEffectiveParameters: monta o objeto EffectiveParameters completo (campos comuns
//     preenchidos normalmente; campos específicos da topologia via EffectiveParameters.Extra,
//     mesclados genericamente no JSON via [JsonExtensionData] -- ver JobEnvelope.cs).
//   - PopulateMetricsExtra: preenche APENAS os campos extras específicos da topologia em
//     GeometryMetrics.Extra (os campos comuns -- volume, área, watertight, etc. -- já foram
//     calculados genericamente por GeometryMetricsCalculator.ComputeAll, topologia-agnóstico,
//     antes desta chamada).
namespace BioMatCadGeometryWorker;

public interface ITopologyProvider
{
    /// <summary>Deve bater exatamente com recipe.topology.kind (contrato JSON) e com a entrada
    /// equivalente em apps/api/src/biomatcad_api/services/topology_providers.py -- os dois
    /// lados são mantidos em sincronia manual, e testes de regressão em cada lado travam o
    /// valor esperado (kind e ProviderVersion) para que uma divergência silenciosa nunca passe
    /// despercebida.</summary>
    string Kind { get; }

    string ProviderVersion { get; }

    TopologyBuildResult BuildAndExport(JobInput job, string stlOutputPath);

    /// <summary>Monta o EffectiveParameters completo desta execução. measuredMetrics é o
    /// GeometryMetrics JÁ CALCULADO genericamente (Program.cs chama
    /// GeometryMetricsCalculator.ComputeAll antes desta função) -- necessário porque campos como
    /// measured_porosity_error_pct_points dependem da porosidade REALMENTE medida sobre a malha
    /// exportada, não de nenhuma estimativa em memória separada.</summary>
    EffectiveParameters DescribeEffectiveParameters(
        JobInput job, TopologyBuildResult result, GeometryMetrics measuredMetrics,
        long estimatedVoxelCount, double estimatedMemoryMb);

    /// <summary>Preenche metrics.Extra com os campos métricos específicos desta topologia (ex.:
    /// contagem de sítios/nós/arestas/componentes do Voronoi). Implementação do Gyroid: não faz
    /// nada, não há métricas extras específicas do Gyroid nesta rodada.</summary>
    void PopulateMetricsExtra(GeometryMetrics metrics, TopologyBuildResult result);
}
