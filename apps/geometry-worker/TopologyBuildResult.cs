// Base comum para o resultado de qualquer ITopologyProvider.BuildAndExport -- Incremento 2.2,
// Seção 8 da instrução ("PROVIDER E WORKER").
//
// Generaliza o que ANTES era um tipo concreto único (GyroidScaffoldBuilder.BuildResult, usado
// diretamente pela interface ITopologyProvider desde a Seção 4) para uma base abstrata mínima --
// mudança aditiva e de baixo risco: GyroidScaffoldBuilder.BuildResult passa a herdar desta classe
// e perde apenas sua ANTIGA propriedade Mesh própria (agora herdada, mesmo nome/tipo/semântica,
// nenhuma mudança de comportamento). Todos os demais campos específicos do Gyroid permanecem
// exatamente como antes, na classe derivada.
//
// Program.cs nunca precisa fazer downcast para TopologyBuildResult -- apenas usa result.Mesh
// (comum a qualquer topologia) e delega toda a montagem de EffectiveParameters/métricas extras
// de volta ao próprio ITopologyProvider (DescribeEffectiveParameters/PopulateMetricsExtra), que
// SIM pode (e deve) fazer o downcast para seu próprio tipo concreto conhecido -- isto mantém o
// conhecimento específico de cada topologia encapsulado dentro do seu próprio provider, sem
// nenhum "if" disperso por Program.cs quando uma nova topologia for adicionada no futuro.
namespace BioMatCadGeometryWorker;

public abstract class TopologyBuildResult
{
    public SimpleMesh Mesh { get; init; } = new();
}
