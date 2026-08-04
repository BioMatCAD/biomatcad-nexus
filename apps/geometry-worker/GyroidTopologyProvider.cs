// Primeira implementação real do contrato ITopologyProvider (Incremento 2.2, Seção 4).
//
// Delega integralmente para GyroidScaffoldBuilder.BuildAndExport -- MESMA matemática, MESMO
// comportamento das 3 golden recipes já aprovadas. Nenhuma lógica de geração de geometria foi
// alterada por este contrato: ele apenas encapsula a chamada estática já existente atrás de uma
// interface, para que Program.cs possa despachar por topology.kind através de um registro em
// vez de um if/else fixo -- resultado Gyroid nunca muda silenciosamente.
//
// Incremento 2.2, Seção 8: DescribeEffectiveParameters contém EXATAMENTE a mesma lógica que
// antes vivia hardcoded em Program.cs (movida verbatim, nenhum campo/cálculo alterado) -- agora
// encapsulada aqui porque Program.cs não pode mais acessar os campos concretos de
// GyroidScaffoldBuilder.BuildResult diretamente (o tipo de retorno de BuildAndExport agora é o
// TopologyBuildResult abstrato, compartilhado com o VoronoiTopologyProvider). O downcast para
// GyroidScaffoldBuilder.BuildResult abaixo é sempre seguro: este provider só recebe de volta o
// resultado que ele mesmo produziu em BuildAndExport.
namespace BioMatCadGeometryWorker;

public sealed class GyroidTopologyProvider : ITopologyProvider
{
    public string Kind => "gyroid";

    // Mantido em sincronia manual com
    // apps/api/src/biomatcad_api/services/topology_providers.py::_REGISTRY["gyroid"].version --
    // um teste de regressão em cada lado trava esta string.
    public string ProviderVersion => "1.0.0";

    public TopologyBuildResult BuildAndExport(JobInput job, string stlOutputPath) =>
        GyroidScaffoldBuilder.BuildAndExport(job, stlOutputPath);

    public EffectiveParameters DescribeEffectiveParameters(
        JobInput job, TopologyBuildResult result, GeometryMetrics measuredMetrics,
        long estimatedVoxelCount, double estimatedMemoryMb)
    {
        var buildResult = (GyroidScaffoldBuilder.BuildResult)result;
        var topology = job.Recipe.Topology;

        // Item 6/7 (correção pós-execução real, herdada sem alteração do Incremento 2.1.1):
        // measured_porosity_pct SEMPRE vem de measuredMetrics.PorosityPctMeasured -- calculada
        // sobre buildResult.Mesh, que é EXATAMENTE a malha soldada gravada no STL (não uma
        // medição separada em memória que poderia divergir do arquivo).
        bool hasCalibration = buildResult.MeshPorosityCalibration is not null;
        double? measuredPorosityErrorPctPoints = hasCalibration
            ? measuredMetrics.PorosityPctMeasured - topology.TargetPorosityPct!.Value
            : null;
        bool? measuredPorosityWithinTolerance = hasCalibration
            ? Math.Abs(measuredPorosityErrorPctPoints!.Value) <= buildResult.PorosityToleranceUsedPctPoints
            : null;

        return new EffectiveParameters
        {
            WallThicknessRequestedMm = topology.WallThicknessMm,
            WallThicknessEffectiveMm = buildResult.EffectiveWallThicknessMm,
            IsovalueCenter = buildResult.IsovalueCenter,
            TargetPorosityPctRequested = topology.TargetPorosityPct,
            AnalyticalPorosityEstimatePct = buildResult.AnalyticalPorosityCalibration?.EstimatedPorosityPct,
            AnalyticalCalibrationConverged = buildResult.AnalyticalPorosityCalibration?.Converged,
            MeasuredPorosityPct = hasCalibration ? measuredMetrics.PorosityPctMeasured : null,
            PorosityTolerancePctPoints = hasCalibration ? buildResult.PorosityToleranceUsedPctPoints : null,
            MeasuredPorosityErrorPctPoints = measuredPorosityErrorPctPoints,
            MeasuredPorosityWithinTolerance = measuredPorosityWithinTolerance,
            MeshCalibrationIterations = buildResult.MeshPorosityCalibration?.Iterations,
            Seed = job.Recipe.Seed,
            SeedPhaseShiftRad = buildResult.SeedPhaseShiftRad,
            Mode = job.Recipe.Mode,
            VoxelSizeRequestedMm = job.Recipe.Resolution.VoxelSizeMm,
            VoxelSizeEffectiveMm = buildResult.VoxelSizeEffectiveMm,
            EstimatedVoxelCount = estimatedVoxelCount,
            EstimatedMemoryMbUpperBound = estimatedMemoryMb,
        };
    }

    // Nenhuma métrica extra específica do Gyroid nesta rodada -- metrics.Extra permanece
    // nulo/intocado, o que (verificado empiricamente) produz o MESMO JSON de antes, sem nenhuma
    // chave nova.
    public void PopulateMetricsExtra(GeometryMetrics metrics, TopologyBuildResult result)
    {
    }
}
