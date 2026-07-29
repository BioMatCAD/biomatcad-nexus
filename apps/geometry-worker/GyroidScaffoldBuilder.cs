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
    public sealed class BuildResult
    {
        public SimpleMesh Mesh { get; init; } = new();
        public GyroidMath.PorosityCalibrationResult? PorosityCalibration { get; init; }
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

        // Calibração de porosidade (item 2): se target_porosity_pct foi solicitado, a espessura
        // EFETIVA usada na construção vem da calibração analítica por bisseção (GyroidMath, sem
        // PicoGK); caso contrário, wall_thickness_mm solicitado é usado diretamente.
        GyroidMath.PorosityCalibrationResult? calibration = null;
        double effectiveWallThicknessMm = topology.WallThicknessMm;
        if (topology.TargetPorosityPct is double targetPct)
        {
            calibration = GyroidMath.CalibratePorosityByBisection(
                targetPorosityPct: targetPct,
                isovalueCenter: isovalueCenter,
                phaseShiftRad: phaseShiftRad,
                cellSizeMm: topology.CellSizeMm,
                initialWallThicknessMm: topology.WallThicknessMm);
            effectiveWallThicknessMm = calibration.EffectiveWallThicknessMm;
        }

        double halfBandWidth = GyroidMath.WallThicknessMmToHalfBandWidth(effectiveWallThicknessMm, topology.CellSizeMm);

        SimpleMesh? resultMesh = null;

        // bEndAppWithTask: true -- Incremento 2.1.1 (correção pós-execução real no Windows).
        // Execução real do worker (block-gyroid-v1, Windows x64, PicoGK Core 26.2.0) mostrou
        // que a janela do viewer permanecia aberta após o STL já ter sido gravado, exigindo
        // fechamento manual e inflando duration_seconds com tempo de espera humana (não de
        // geração geométrica). Assinatura real de Library.Go confirmada nesta sessão via
        // reflexão contra o PicoGK.dll 2.2.0 efetivamente instalado (não documentação
        // presumida nem parâmetro inventado):
        //   Go(float fVoxelSizeMM, ThreadStart fnTask, string strLogFilePath = "",
        //      bool bEndAppWithTask = false, string strWindowTitle = "PicoGK",
        //      string strLightsFile = "")
        // O parâmetro bEndAppWithTask é o único e oficial mecanismo documentado (XML doc do
        // pacote: "If true, the viewer exits when your task is done") para o viewer encerrar
        // sozinho ao final de fnTask -- o valor padrão do parâmetro é false, e o worker nunca
        // o definia explicitamente, daí o comportamento relatado. Passado aqui como argumento
        // nomeado para deixar a intenção explícita e à prova de futuras mudanças de ordem de
        // parâmetros na assinatura.
        Library.Go((float)voxelSizeEffectiveMm, () =>
        {
            BBox3 bounds;
            IImplicit combinedImplicit;

            if (domain.Shape == "block")
            {
                double halfX = domain.DimensionsMm.XMm!.Value / 2.0;
                double halfY = domain.DimensionsMm.YMm!.Value / 2.0;
                double halfZ = domain.DimensionsMm.ZMm!.Value / 2.0;
                bounds = new BBox3(
                    new Vector3((float)-halfX, (float)-halfY, (float)-halfZ),
                    new Vector3((float)halfX, (float)halfY, (float)halfZ));
                combinedImplicit = new GyroidDomainImplicit(
                    topology.CellSizeMm, isovalueCenter, halfBandWidth, phaseShiftRad,
                    "block", halfX, halfY, halfZ, 0, 0, 0);
            }
            else if (domain.Shape == "cylinder")
            {
                double radiusMm = domain.DimensionsMm.RadiusMm!.Value;
                double heightMm = domain.DimensionsMm.HeightMm!.Value;
                // Voxels centraliza a bbox em torno da origem; o cilindro é modelado com base em
                // z=0 internamente (GyroidMath.CappedCylinderSignedDistanceMm), então a bbox vai
                // de -height/2 a +height/2 e aplicamos um deslocamento de +height/2 nas consultas
                // ao SDF (cylinderCenterZOffsetMm) para recentralizar sem alterar a fórmula do SDF.
                bounds = new BBox3(
                    new Vector3((float)-radiusMm, (float)-radiusMm, (float)(-heightMm / 2.0)),
                    new Vector3((float)radiusMm, (float)radiusMm, (float)(heightMm / 2.0)));
                combinedImplicit = new GyroidDomainImplicit(
                    topology.CellSizeMm, isovalueCenter, halfBandWidth, phaseShiftRad,
                    "cylinder", 0, 0, 0, radiusMm, heightMm, heightMm / 2.0);
            }
            else
            {
                throw new NotSupportedException($"Domínio não suportado: {domain.Shape}");
            }

            var voxels = new Voxels(combinedImplicit, bounds);
            var mesh = new Mesh(voxels);

            var rawMesh = new SimpleMesh();
            int triangleCount = mesh.nTriangleCount();
            for (int i = 0; i < triangleCount; i++)
            {
                mesh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
                rawMesh.AddTriangle(new Vec3(a.X, a.Y, a.Z), new Vec3(b.X, b.Y, b.Z), new Vec3(c.X, c.Y, c.Z));
            }

            // Solda os vértices ANTES de exportar/medir (item 2/11): corrige a divergência de
            // contagem de vértices encontrada na auditoria (STL sempre grava 3 vértices "soltos"
            // por triângulo por limitação do próprio formato -- mas a malha em memória usada para
            // métricas e para o teste de watertight deve refletir vértices únicos reais).
            var weldedMesh = rawMesh.Weld();
            StlExporter.WriteBinary(weldedMesh, stlOutputPath);

            resultMesh = weldedMesh;
        }, bEndAppWithTask: true);

        return new BuildResult
        {
            Mesh = resultMesh ?? new SimpleMesh(),
            PorosityCalibration = calibration,
            EffectiveWallThicknessMm = effectiveWallThicknessMm,
            IsovalueCenter = isovalueCenter,
            SeedPhaseShiftRad = phaseShiftRad,
            VoxelSizeEffectiveMm = voxelSizeEffectiveMm,
        };
    }
}
