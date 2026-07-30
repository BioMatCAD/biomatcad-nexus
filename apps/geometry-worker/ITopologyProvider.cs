// Contrato versionado e explícito de topologia (Incremento 2.2, Seção 4).
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

    /// <summary>Tipo de retorno reaproveita GyroidScaffoldBuilder.BuildResult por ora -- é a
    /// forma real de que Program.cs precisa hoje (malha, calibração de porosidade, parâmetros
    /// efetivos). Quando um segundo provider real for implementado (ex.: Voronoi), pode ser
    /// necessário generalizar este tipo; documentado aqui como simplificação conhecida desta
    /// rodada, não como decisão definitiva de arquitetura.</summary>
    GyroidScaffoldBuilder.BuildResult BuildAndExport(JobInput job, string stlOutputPath);
}
