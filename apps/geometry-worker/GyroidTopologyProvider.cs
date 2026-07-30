// Primeira implementação real do contrato ITopologyProvider (Incremento 2.2, Seção 4).
//
// Delega integralmente para GyroidScaffoldBuilder.BuildAndExport -- MESMA matemática, MESMO
// comportamento das 3 golden recipes já aprovadas. Nenhuma lógica de geração de geometria foi
// alterada por este contrato: ele apenas encapsula a chamada estática já existente atrás de uma
// interface, para que Program.cs possa despachar por topology.kind através de um registro em
// vez de um if/else fixo -- resultado Gyroid nunca muda silenciosamente.
namespace BioMatCadGeometryWorker;

public sealed class GyroidTopologyProvider : ITopologyProvider
{
    public string Kind => "gyroid";

    // Mantido em sincronia manual com
    // apps/api/src/biomatcad_api/services/topology_providers.py::_REGISTRY["gyroid"].version --
    // um teste de regressão em cada lado trava esta string.
    public string ProviderVersion => "1.0.0";

    public GyroidScaffoldBuilder.BuildResult BuildAndExport(JobInput job, string stlOutputPath) =>
        GyroidScaffoldBuilder.BuildAndExport(job, stlOutputPath);
}
