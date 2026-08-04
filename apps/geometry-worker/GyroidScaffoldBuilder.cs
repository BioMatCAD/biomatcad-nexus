// Geração real do scaffold Gyroid via PicoGK (LEAP 71, Apache-2.0) -- ver NOTICE.
// Fórmula da superfície mínima periódica (TPMS) de Alan Schoen (1970), domínio público:
//   sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x) = isovalue
//
// Este arquivo é DEPENDENTE do runtime nativo do PicoGK (libpicogk), que não está disponível
// para linux-x64 no pacote 2.2.0 (ver WORKER_STATUS.md/ADR-0007) -- compila, mas sua execução
// real (voxelização/meshing de verdade) não pôde ser verificada neste sandbox Linux. Toda a
// matemática de que depende a CORREÇÃO deste arquivo (SDF de domínio, interseção booleana,
// conversão espessura->banda, calibração de porosidade, fase por seed) está isolada em
// GyroidMath.cs, que É testável sem PicoGK -- ver tests/BioMatCadGeometryWorker.Tests.
//
// Incremento 2.1.1 (item 2) corrige, em relação ao Incremento 2.1:
//  - domínio cilíndrico agora recorta pelo volume real do cilindro (SDF), não apenas pela bbox;
//  - interseção booleana implícita real entre gyroid e domínio (max de duas SDF -- CSG padrão);
//  - wall_thickness_mm é o único controlador de espessura (isovalue só desloca o centro da banda);
//  - target_porosity_pct, quando presente, calibra a espessura efetiva por bisseção analítica;
//  - seed determina uma fase de deslocamento real da célula (não apenas está presente no job);
//  - modo preview usa um voxel size efetivo nunca mais fino que um piso documentado (diferença
//    real vs. modo final, que respeita o voxel size solicitado integralmente);
//  - a malha resultante é soldada (Weld) antes de métricas/exportação -- vértices únicos reais.
using System.Numerics;
using PicoGK;

namespace BioMatCadGeometryWorker;

/// <summary>Implicit combinado: interseção entre a banda gyroid (espessura/isovalor) e o SDF do
/// domínio (bloco ou cilindro real). fSignedDistance segue a convenção negativo-dentro/positivo-fora
/// assumida pelo PicoGK.Voxels (mesma convenção do Incremento 2.1 original) -- se a execução real
/// no Windows revelar convenção invertida, é visível imediatamente (geometria vazia ou preenchida
/// por completo) e documentado como próximo passo de correção em WORKER_STATUS.md.</summary>
public sealed class GyroidDomainImplicit : IImplicit
{
    private readonly double _cellSizeMm;
    private readonly double _isovalueCenter;
    private readonly double _halfBandWidth;
    private readonly double _phaseShiftRad;
    private readonly string _domainShape;
    private readonly double _halfX, _halfY, _halfZ;      // usado quando domainShape == "block"
    private readonly double _radiusMm, _heightMm;         // usado quando domainShape == "cylinder"
    private readonly double _cylinderCenterZOffsetMm;     // recentraliza cilindro (base em z=0) para bbox centrada em Voxels

    public GyroidDomainImplicit(
        double cellSizeMm, double isovalueCenter, double halfBandWidth, double phaseShiftRad,
        string domainShape, double halfX, double halfY, double halfZ,
        double radiusMm, double heightMm, double cylinderCenterZOffsetMm)
    {
        _cellSizeMm = cellSizeMm;
        _isovalueCenter = isovalueCenter;
        _halfBandWidth = halfBandWidth;
        _phaseShiftRad = phaseShiftRad;
        _domainShape = domainShape;
        _halfX = halfX; _halfY = halfY; _halfZ = halfZ;
        _radiusMm = radiusMm; _heightMm = heightMm;
        _cylinderCenterZOffsetMm = cylinderCenterZOffsetMm;
    }

    public float fSignedDistance(in Vector3 vec)
    {
        double gyroidField = GyroidMath.EvaluateGyroidField(vec.X, vec.Y, vec.Z, _cellSizeMm, _phaseShiftRad);
        double gyroidBandDistance = GyroidMath.SignedBandDistanceMmApprox(gyroidField, _isovalueCenter, _halfBandWidth, _cellSizeMm);

        double domainDistance = _domainShape switch
        {
            "block" => GyroidMath.BoxSignedDistanceMm(vec.X, vec.Y, vec.Z, _halfX, _halfY, _halfZ),
            "cylinder" => GyroidMath.CappedCylinderSignedDistanceMm(vec.X, vec.Y, vec.Z + _cylinderCenterZOffsetMm, _radiusMm, _heightMm),
            _ => throw new NotSupportedException($"Domínio não suportado: {_domainShape}"),
        };

        double combined = GyroidMath.IntersectSignedDistance(gyroidBandDistance, domainDistance);
        return (float)combined;
    }
}

public static class GyroidScaffoldBuilder
{
    public sealed class BuildResult : TopologyBuildResult
    {
        // Mesh agora é herdado de TopologyBuildResult (Incremento 2.2, Seção 8) -- mesmo
        // nome/tipo/semântica de antes, nenhuma mudança de comportamento.
        // Calibração analítica (Passo 1, palpite inicial) -- estimativa contínua, PicoGK-
        // independente. NUNCA usada isoladamente para declarar sucesso (ver correção pós-
        // execução real abaixo).
        public GyroidMath.PorosityCalibrationResult? AnalyticalPorosityCalibration { get; init; }
        // Calibração fechada contra a malha REAL do PicoGK (Passo 2) -- só populada quando
        // target_porosity_pct foi solicitado. É o valor de referência definitivo.
        public GyroidMath.MonotonicCalibrationResult? MeshPorosityCalibration { get; init; }
        public double PorosityToleranceUsedPctPoints { get; init; }
        public double EffectiveWallThicknessMm { get; init; }
        public double IsovalueCenter { get; init; }
        public double SeedPhaseShiftRad { get; init; }
        public double VoxelSizeEffectiveMm { get; init; }
    }

    public static BuildResult BuildAndExport(JobInput job, string stlOutputPath)
    {
        var recipe = job.Recipe;
        var domain = recipe.Domain;
        var topology = recipe.Topology;

        double isovalueCenter = topology.Isovalue;
        double phaseShiftRad = GyroidMath.SeedToPhaseShiftRad(recipe.Seed);
        double voxelSizeEffectiveMm = GyroidMath.EffectiveVoxelSizeMm(recipe.Resolution.VoxelSizeMm, recipe.Mode);
        double domainVolumeMm3 = GeometryMetricsCalculator.ComputeDomainVolumeMm3(domain);
        double toleranceUsedPctPoints = GyroidMath.DefaultPorosityTolerancePctPointsForMode(recipe.Mode);

        // Passo 1 (item 2): calibração ANALÍTICA -- serve apenas de palpite inicial rápido para
        // a bisseção real do Passo 2 (dentro de Library.Go, abaixo). Nunca é o valor final
        // reportado como "convergido" -- ver AnalyticalPorosityCalibration vs.
        // MeshPorosityCalibration no BuildResult, e os campos análogos e explicitamente
        // distintos no JSON de saída (Program.cs): analytical_calibration_converged nunca deve
        // ser confundido com measured_porosity_within_tolerance.
        GyroidMath.PorosityCalibrationResult? analyticalCalibration = null;
        double effectiveWallThicknessMm = topology.WallThicknessMm;
        if (topology.TargetPorosityPct is double targetPct)
        {
            analyticalCalibration = GyroidMath.CalibratePorosityByBisection(
                targetPorosityPct: targetPct,
                isovalueCenter: isovalueCenter,
                phaseShiftRad: phaseShiftRad,
                cellSizeMm: topology.CellSizeMm,
                initialWallThicknessMm: topology.WallThicknessMm);
            effectiveWallThicknessMm = analyticalCalibration.EffectiveWallThicknessMm;
        }

        SimpleMesh? resultMesh = null;
        GyroidMath.MonotonicCalibrationResult? meshCalibration = null;

        // bEndAppWithTask: true -- ver histórico da correção do viewer em WORKER_STATUS.md §10.1
        // (assinatura real confirmada por reflexão contra o PicoGK.dll 2.2.0 instalado).
        Library.Go((float)voxelSizeEffectiveMm, () =>
        {
            BBox3 bounds;
            double halfX = 0, halfY = 0, halfZ = 0, radiusMm = 0, heightMm = 0, cylinderCenterZOffsetMm = 0;

            if (domain.Shape == "block")
            {
                halfX = domain.DimensionsMm.XMm!.Value / 2.0;
                halfY = domain.DimensionsMm.YMm!.Value / 2.0;
                halfZ = domain.DimensionsMm.ZMm!.Value / 2.0;
                bounds = new BBox3(
                    new Vector3((float)-halfX, (float)-halfY, (float)-halfZ),
                    new Vector3((float)halfX, (float)halfY, (float)halfZ));
            }
            else if (domain.Shape == "cylinder")
            {
                radiusMm = domain.DimensionsMm.RadiusMm!.Value;
                heightMm = domain.DimensionsMm.HeightMm!.Value;
                // Voxels centraliza a bbox em torno da origem; o cilindro é modelado com base em
                // z=0 internamente (GyroidMath.CappedCylinderSignedDistanceMm), então a bbox vai
                // de -height/2 a +height/2 e aplicamos um deslocamento de +height/2 nas consultas
                // ao SDF (cylinderCenterZOffsetMm) para recentralizar sem alterar a fórmula do SDF.
                cylinderCenterZOffsetMm = heightMm / 2.0;
                bounds = new BBox3(
                    new Vector3((float)-radiusMm, (float)-radiusMm, (float)(-heightMm / 2.0)),
                    new Vector3((float)radiusMm, (float)radiusMm, (float)(heightMm / 2.0)));
            }
            else
            {
                throw new NotSupportedException($"Domínio não suportado: {domain.Shape}");
            }

            // Constrói o implicit combinado para um candidato de espessura -- reutilizado por
            // cada iteração da calibração fechada (Passo 2) sem duplicar a lógica de domínio.
            GyroidDomainImplicit BuildImplicitForThickness(double candidateWallThicknessMm)
            {
                double candidateHalfBandWidth = GyroidMath.WallThicknessMmToHalfBandWidth(candidateWallThicknessMm, topology.CellSizeMm);
                return domain.Shape == "block"
                    ? new GyroidDomainImplicit(
                        topology.CellSizeMm, isovalueCenter, candidateHalfBandWidth, phaseShiftRad,
                        "block", halfX, halfY, halfZ, 0, 0, 0)
                    : new GyroidDomainImplicit(
                        topology.CellSizeMm, isovalueCenter, candidateHalfBandWidth, phaseShiftRad,
                        "cylinder", 0, 0, 0, radiusMm, heightMm, cylinderCenterZOffsetMm);
            }

            // Gera Voxels+Mesh REAIS contra o PicoGK para um candidato de espessura, e extrai a
            // malha crua (sem solda -- volume/área não dependem de solda, só a contagem de
            // vértices únicos e o teste de watertight dependem; a solda final só acontece uma
            // vez, sobre a malha vencedora, depois do laço de calibração). Voxels/Mesh
            // implementam IDisposable -- descartados explicitamente a cada iteração (`using`)
            // para não acumular memória nativa entre candidatos (item 8: respeitar limite de
            // memória mesmo durante a calibração).
            SimpleMesh BuildRawMeshForThickness(double candidateWallThicknessMm)
            {
                var implicitForCandidate = BuildImplicitForThickness(candidateWallThicknessMm);
                using var candidateVoxels = new Voxels(implicitForCandidate, bounds);
                using var candidateMeshObj = new Mesh(candidateVoxels);
                var raw = new SimpleMesh();
                int triangleCount = candidateMeshObj.nTriangleCount();
                for (int i = 0; i < triangleCount; i++)
                {
                    candidateMeshObj.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
                    raw.AddTriangle(new Vec3(a.X, a.Y, a.Z), new Vec3(b.X, b.Y, b.Z), new Vec3(c.X, c.Y, c.Z));
                }
                return raw;
            }

            SimpleMesh finalRawMesh;

            if (topology.TargetPorosityPct is double targetPorosityPct)
            {
                // Passo 2 (correção pós-execução real): calibração FECHADA contra a malha real.
                // Cada candidato de espessura gera Voxels+Mesh de verdade e mede o volume real
                // resultante -- nunca confia apenas na estimativa analítica do Passo 1.
                SimpleMesh? lastCandidateMesh = null;

                double MeasureMeshPorosityForThickness(double candidateWallThicknessMm)
                {
                    var candidateRawMesh = BuildRawMeshForThickness(candidateWallThicknessMm);
                    lastCandidateMesh = candidateRawMesh;
                    double solidVolumeMm3 = GeometryMetricsCalculator.ComputeVolumeMm3(candidateRawMesh);
                    return GeometryMetricsCalculator.EstimatePorosityPct(solidVolumeMm3, domainVolumeMm3);
                }

                // Limites físicos seguros para a busca: mesma faixa que a checagem de
                // contradição espessura/isovalor já usa (0 exclusive .. cell_size_mm/2 exclusive
                // -- acima disso, a célula fica sem poro algum, ver TOPOLOGY_PARAMETERS_INCONSISTENT
                // em Program.cs).
                double minWallThicknessMm = 1e-6;
                double maxWallThicknessMm = topology.CellSizeMm / 2.0 - 1e-6;

                meshCalibration = GyroidMath.CalibrateByMonotonicBisection(
                    targetPorosityPct: targetPorosityPct,
                    initialWallThicknessMm: effectiveWallThicknessMm,
                    minWallThicknessMm: minWallThicknessMm,
                    maxWallThicknessMm: maxWallThicknessMm,
                    toleranceAbsPctPoints: toleranceUsedPctPoints,
                    maxIterations: GyroidMath.DefaultMeshCalibrationMaxIterations,
                    measurePorosityForThickness: MeasureMeshPorosityForThickness);

                if (!meshCalibration.Converged)
                {
                    // Não finge sucesso científico: interrompe ANTES de soldar/exportar
                    // qualquer STL. Program.cs mapeia esta exceção para
                    // POROSITY_TARGET_NOT_REACHED (erro estruturado) e aciona a limpeza de
                    // artefatos parciais normalmente (nenhum arquivo foi gravado ainda).
                    throw new PorosityTargetNotReachedException(meshCalibration);
                }

                effectiveWallThicknessMm = meshCalibration.EffectiveWallThicknessMm;
                finalRawMesh = lastCandidateMesh!;
            }
            else
            {
                // Sem target_porosity_pct: usa wall_thickness_mm solicitado diretamente, uma
                // única geração real (sem laço de calibração).
                finalRawMesh = BuildRawMeshForThickness(effectiveWallThicknessMm);
            }

            // Solda os vértices ANTES de exportar/medir (item 2/11): corrige a divergência de
            // contagem de vértices encontrada na auditoria (STL sempre grava 3 vértices "soltos"
            // por triângulo por limitação do próprio formato -- mas a malha em memória usada para
            // métricas e para o teste de watertight deve refletir vértices únicos reais).
            var weldedMesh = finalRawMesh.Weld();
            StlExporter.WriteBinary(weldedMesh, stlOutputPath);

            resultMesh = weldedMesh;
        }, bEndAppWithTask: true);

        return new BuildResult
        {
            Mesh = resultMesh ?? new SimpleMesh(),
            AnalyticalPorosityCalibration = analyticalCalibration,
            MeshPorosityCalibration = meshCalibration,
            PorosityToleranceUsedPctPoints = toleranceUsedPctPoints,
            EffectiveWallThicknessMm = effectiveWallThicknessMm,
            IsovalueCenter = isovalueCenter,
            SeedPhaseShiftRad = phaseShiftRad,
            VoxelSizeEffectiveMm = voxelSizeEffectiveMm,
        };
    }
}
