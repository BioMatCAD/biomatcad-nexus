// Geração real do scaffold Voronoi (voronoi_cell_edges_v1) via PicoGK -- Incremento 2.2, rodada
// Voronoi, Seções 6 e 7 da instrução ("STRUTS E SUAVIZAÇÃO DOS NÓS" e "CALIBRAÇÃO DE
// POROSIDADE").
//
// Este arquivo é DEPENDENTE do runtime nativo do PicoGK (libpicogk), que não está disponível
// para linux-x64 (ver WORKER_STATUS.md/ADR-0007, mesmo bloqueio já documentado para
// GyroidScaffoldBuilder.cs) -- compila, mas sua execução real (voxelização/meshing de verdade)
// não pôde ser verificada neste sandbox Linux. Toda a matemática de que depende a CORREÇÃO
// deste arquivo (geração de sítios, tesselação de Voronoi, SDF de cápsula/esfera, smooth-min,
// SDF de domínio, calibração) está isolada em VoronoiSiteGenerator.cs, VoronoiTessellation.cs,
// VoronoiImplicitMath.cs e GyroidMath.cs (reaproveitado) -- todos testáveis sem PicoGK, ver
// tests/BioMatCadGeometryWorker.Tests.
//
// Estratégia fixa desta rodada (decidida na auditoria matemática, Seção 6): cada aresta real de
// célula de Voronoi (produzida por VoronoiTessellation, nunca uma aresta de adjacência de sítios
// de Delaunay) vira uma cápsula implícita; cada nó (extremidade de aresta) vira uma esfera
// implícita; a união entre todos os primitivos é feita por smooth-min polinomial
// (implicit_smooth_union) -- NÃO Catmull-Clark (documentado como alternativa futura, nunca
// alegada como equivalente).
//
// Limitação documentada honestamente (ver auditoria matemática e VoronoiImplicitMath.cs): a
// avaliação da união suave em cada voxel percorre TODOS os primitivos (struts+nós) sem uma
// estrutura de aceleração espacial (grade/bucket) -- aceitável para as receitas pequenas e
// conservadoras exigidas nesta rodada (site_count <= 500), mas um candidato natural de
// otimização futura se receitas maiores forem habilitadas. Como a execução real do PicoGK não
// pode ser verificada neste sandbox de qualquer forma, introduzir uma estrutura de aceleração
// não testável aqui traria risco sem poder ser comprovado nesta rodada -- adiado deliberadamente.
using System.Numerics;
using PicoGK;

namespace BioMatCadGeometryWorker;

/// <summary>Implicit combinado: união suave de cápsulas (struts) e esferas (nós), interseção com
/// o SDF do domínio (bloco ou cilindro real, mesma convenção e mesmo código de domínio já usado
/// por GyroidDomainImplicit -- reaproveitado via GyroidMath, nunca uma segunda definição
/// divergente de "dentro do domínio").</summary>
public sealed class VoronoiStrutsImplicit : IImplicit
{
    private readonly IReadOnlyList<(Vec3 A, Vec3 B)> _edges;
    private readonly IReadOnlyList<Vec3> _nodes;
    private readonly double _strutRadiusMm;
    private readonly double _nodeRadiusMm;
    private readonly double _smoothingLengthMm;
    private readonly string _domainShape;
    private readonly double _halfX, _halfY, _halfZ;
    private readonly double _radiusMm, _heightMm, _cylinderCenterZOffsetMm;

    public VoronoiStrutsImplicit(
        IReadOnlyList<(Vec3 A, Vec3 B)> edges, IReadOnlyList<Vec3> nodes,
        double strutRadiusMm, double nodeRadiusMm, double smoothingLengthMm,
        string domainShape, double halfX, double halfY, double halfZ,
        double radiusMm, double heightMm, double cylinderCenterZOffsetMm)
    {
        _edges = edges;
        _nodes = nodes;
        _strutRadiusMm = strutRadiusMm;
        _nodeRadiusMm = nodeRadiusMm;
        _smoothingLengthMm = smoothingLengthMm;
        _domainShape = domainShape;
        _halfX = halfX; _halfY = halfY; _halfZ = halfZ;
        _radiusMm = radiusMm; _heightMm = heightMm;
        _cylinderCenterZOffsetMm = cylinderCenterZOffsetMm;
    }

    public float fSignedDistance(in Vector3 vec)
    {
        var p = new Vec3(vec.X, vec.Y, vec.Z);

        var distances = new List<double>(_edges.Count + _nodes.Count);
        foreach (var (a, b) in _edges)
        {
            distances.Add(VoronoiImplicitMath.CapsuleSignedDistanceMm(p, a, b, _strutRadiusMm));
        }
        foreach (var node in _nodes)
        {
            distances.Add(VoronoiImplicitMath.SphereSignedDistanceMm(p, node, _nodeRadiusMm));
        }

        double strutsUnion = VoronoiImplicitMath.SmoothUnionAll(distances, _smoothingLengthMm);

        double domainDistance = _domainShape switch
        {
            "block" => GyroidMath.BoxSignedDistanceMm(vec.X, vec.Y, vec.Z, _halfX, _halfY, _halfZ),
            "cylinder" => GyroidMath.CappedCylinderSignedDistanceMm(vec.X, vec.Y, vec.Z + _cylinderCenterZOffsetMm, _radiusMm, _heightMm),
            _ => throw new NotSupportedException($"Domínio não suportado: {_domainShape}"),
        };

        double combined = GyroidMath.IntersectSignedDistance(strutsUnion, domainDistance);
        return (float)combined;
    }
}

public static class VoronoiScaffoldBuilder
{
    /// <summary>Limite superior conservador para a busca de calibração do raio do strut --
    /// mesmo valor máximo já declarado no schema da receita (strut_radius_mm &lt;= 3mm), nunca
    /// um valor derivado de forma implícita/mágica.</summary>
    public const double MaxStrutRadiusSearchMm = 3.0;

    public sealed class BuildResult : TopologyBuildResult
    {
        // Mesh agora é herdado de TopologyBuildResult (Incremento 2.2, Seção 8) -- mesmo
        // nome/tipo/semântica de antes, nenhuma mudança de comportamento.
        public VoronoiSiteGenerator.SiteGenerationResult SiteGeneration { get; init; } = null!;
        public VoronoiTessellationResult Tessellation { get; init; } = null!;
        // Calibração fechada contra a malha REAL do PicoGK -- só populada quando
        // target_porosity_pct foi solicitado. Reaproveita INTEGRALMENTE
        // GyroidMath.CalibrateByMonotonicBisection (já topologia-agnóstico, zero mudança de
        // código) e PorosityTargetNotReachedException (idem).
        public GyroidMath.MonotonicCalibrationResult? MeshPorosityCalibration { get; init; }
        public double PorosityToleranceUsedPctPoints { get; init; }
        public double StrutRadiusRequestedMm { get; init; }
        public double StrutRadiusEffectiveMm { get; init; }
        public double NodeRadiusEffectiveMm { get; init; }
        public double NodeSmoothingLengthMm { get; init; }
        public double VoxelSizeEffectiveMm { get; init; }
    }

    private static VoronoiSiteDistribution ParseDistribution(string? distribution) => distribution switch
    {
        "uniform_random" => VoronoiSiteDistribution.UniformRandom,
        "jittered_grid" => VoronoiSiteDistribution.JitteredGrid,
        null => throw new InvalidOperationException("topology.distribution ausente na receita Voronoi."),
        _ => throw new NotSupportedException(
            $"distribution não suportada por esta versão do worker: '{distribution}' (anatomy_guided é um " +
            "ponto de extensão reservado, ainda não implementado)."),
    };

    public static BuildResult BuildAndExport(JobInput job, string stlOutputPath)
    {
        var recipe = job.Recipe;
        var domain = recipe.Domain;
        var topology = recipe.Topology;

        int siteCount = topology.SiteCount ?? throw new InvalidOperationException("topology.site_count ausente na receita Voronoi.");
        var distribution = ParseDistribution(topology.Distribution);
        double requestedStrutRadiusMm = topology.StrutRadiusMm ?? throw new InvalidOperationException("topology.strut_radius_mm ausente na receita Voronoi.");
        double nodeSmoothingFactor = topology.NodeSmoothing ?? 0.5;
        double nodeRadiusFactor = topology.NodeRadiusFactor ?? 1.3;

        double voxelSizeEffectiveMm = GyroidMath.EffectiveVoxelSizeMm(recipe.Resolution.VoxelSizeMm, recipe.Mode);
        double domainVolumeMm3 = GeometryMetricsCalculator.ComputeDomainVolumeMm3(domain);
        double toleranceUsedPctPoints = GyroidMath.DefaultPorosityTolerancePctPointsForMode(recipe.Mode);

        // Sítios e tesselação são DETERMINÍSTICOS e independem de qual candidato de raio a
        // calibração está testando no momento -- calculados UMA ÚNICA VEZ fora do laço de
        // calibração (só o raio do strut/nó muda a cada candidato, nunca os sítios/arestas).
        var siteResult = VoronoiSiteGenerator.Generate(domain, siteCount, distribution, recipe.Seed, topology.SeedSiteMinSeparationMm);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        if (tessellation.Edges.Count == 0)
        {
            throw new VoronoiTessellationException(
                "nenhuma aresta de célula de Voronoi sobreviveu ao recorte pelo domínio -- nenhuma " +
                "geometria de strut pode ser gerada para esta combinação de sítios/domínio.");
        }

        // Apenas nós referenciados por pelo menos uma aresta sobrevivente viram esferas
        // implícitas -- um nó isolado (grau 0, já reportado honestamente nas métricas de
        // conectividade) não deve aparecer como uma esfera solta flutuando no espaço, pois não
        // representa uma junção real de struts.
        var usedNodeIndices = new HashSet<int>();
        foreach (var (a, b) in tessellation.Edges) { usedNodeIndices.Add(a); usedNodeIndices.Add(b); }
        var usedNodes = usedNodeIndices.Select(i => tessellation.Nodes[i]).ToList();
        var edgePositions = tessellation.Edges
            .Select(e => (A: tessellation.Nodes[e.A], B: tessellation.Nodes[e.B]))
            .ToList();

        SimpleMesh? resultMesh = null;
        GyroidMath.MonotonicCalibrationResult? meshCalibration = null;
        double effectiveStrutRadiusMm = requestedStrutRadiusMm;

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
                cylinderCenterZOffsetMm = heightMm / 2.0;
                bounds = new BBox3(
                    new Vector3((float)-radiusMm, (float)-radiusMm, (float)(-heightMm / 2.0)),
                    new Vector3((float)radiusMm, (float)radiusMm, (float)(heightMm / 2.0)));
            }
            else
            {
                throw new NotSupportedException($"Domínio não suportado: {domain.Shape}");
            }

            SimpleMesh BuildRawMeshForStrutRadius(double candidateStrutRadiusMm)
            {
                double candidateNodeRadiusMm = candidateStrutRadiusMm * nodeRadiusFactor;
                double candidateSmoothingLengthMm = VoronoiImplicitMath.NodeSmoothingFactorToLengthMm(nodeSmoothingFactor, candidateStrutRadiusMm);
                var implicitForCandidate = new VoronoiStrutsImplicit(
                    edgePositions, usedNodes,
                    candidateStrutRadiusMm, candidateNodeRadiusMm, candidateSmoothingLengthMm,
                    domain.Shape, halfX, halfY, halfZ, radiusMm, heightMm, cylinderCenterZOffsetMm);
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
                SimpleMesh? lastCandidateMesh = null;

                double MeasureMeshPorosityForStrutRadius(double candidateStrutRadiusMm)
                {
                    var candidateRawMesh = BuildRawMeshForStrutRadius(candidateStrutRadiusMm);
                    lastCandidateMesh = candidateRawMesh;
                    double solidVolumeMm3 = GeometryMetricsCalculator.ComputeVolumeMm3(candidateRawMesh);
                    return GeometryMetricsCalculator.EstimatePorosityPct(solidVolumeMm3, domainVolumeMm3);
                }

                double minStrutRadiusMm = 1e-4;
                double maxStrutRadiusMm = MaxStrutRadiusSearchMm;

                meshCalibration = GyroidMath.CalibrateByMonotonicBisection(
                    targetPorosityPct: targetPorosityPct,
                    initialWallThicknessMm: requestedStrutRadiusMm,
                    minWallThicknessMm: minStrutRadiusMm,
                    maxWallThicknessMm: maxStrutRadiusMm,
                    toleranceAbsPctPoints: toleranceUsedPctPoints,
                    maxIterations: GyroidMath.DefaultMeshCalibrationMaxIterations,
                    measurePorosityForThickness: MeasureMeshPorosityForStrutRadius);

                if (!meshCalibration.Converged)
                {
                    // Nunca finge sucesso científico: interrompe ANTES de soldar/exportar
                    // qualquer STL. Program.cs mapeia para POROSITY_TARGET_NOT_REACHED, mesmo
                    // caminho já usado pelo Gyroid (exceção genérica, reaproveitada sem mudança).
                    throw new PorosityTargetNotReachedException(meshCalibration);
                }

                effectiveStrutRadiusMm = meshCalibration.EffectiveWallThicknessMm;
                finalRawMesh = lastCandidateMesh!;
            }
            else
            {
                finalRawMesh = BuildRawMeshForStrutRadius(effectiveStrutRadiusMm);
            }

            var weldedMesh = finalRawMesh.Weld();
            StlExporter.WriteBinary(weldedMesh, stlOutputPath);
            resultMesh = weldedMesh;
        }, bEndAppWithTask: true);

        double finalNodeRadiusMm = effectiveStrutRadiusMm * nodeRadiusFactor;
        double finalSmoothingLengthMm = VoronoiImplicitMath.NodeSmoothingFactorToLengthMm(nodeSmoothingFactor, effectiveStrutRadiusMm);

        return new BuildResult
        {
            Mesh = resultMesh ?? new SimpleMesh(),
            SiteGeneration = siteResult,
            Tessellation = tessellation,
            MeshPorosityCalibration = meshCalibration,
            PorosityToleranceUsedPctPoints = toleranceUsedPctPoints,
            StrutRadiusRequestedMm = requestedStrutRadiusMm,
            StrutRadiusEffectiveMm = effectiveStrutRadiusMm,
            NodeRadiusEffectiveMm = finalNodeRadiusMm,
            NodeSmoothingLengthMm = finalSmoothingLengthMm,
            VoxelSizeEffectiveMm = voxelSizeEffectiveMm,
        };
    }
}
