// Segunda implementação real do contrato ITopologyProvider -- Incremento 2.2, rodada Voronoi,
// Seções 8 e 9 da instrução ("PROVIDER E WORKER" e "MÉTRICAS VORONOI").
//
// Delega a geração de geometria para VoronoiScaffoldBuilder.BuildAndExport -- este arquivo é
// responsável apenas por (1) expor o Kind/ProviderVersion para o registro, e (2) traduzir o
// resultado rico de VoronoiScaffoldBuilder.BuildResult para o contrato JSON compartilhado
// (EffectiveParameters/GeometryMetrics), usando os dicionários Extra genéricos ([JsonExtensionData]
// em JobEnvelope.cs) para os campos que não têm equivalente no Gyroid -- nunca reaproveitando ou
// sobrescrevendo os campos Gyroid-específicos já existentes (wall_thickness_*, isovalue_center,
// seed_phase_shift_rad, analytical_*), que permanecem em seus valores-padrão (0.0/null) para
// jobs Voronoi -- documentado aqui explicitamente para que ninguém confunda esse default com um
// valor real.
namespace BioMatCadGeometryWorker;

public sealed class VoronoiTopologyProvider : ITopologyProvider
{
    // Deve bater EXATAMENTE com o valor "const" de topology.kind no ramo voronoi_cell_edges_v1
    // do JSON Schema (schemas/biomatcem/geometry-recipe-v1.schema.json) e com a chave
    // equivalente em apps/api/src/biomatcad_api/services/topology_providers.py::_REGISTRY.
    public string Kind => "voronoi_cell_edges_v1";

    // Primeira versão real (distinta de "1.0.0" do Gyroid, já maduro com 3 golden recipes
    // aprovadas) -- sinaliza que esta é a primeira vertical Voronoi, ainda não validada com
    // execução real do PicoGK (ver ADR-0007/roteiro de validação Windows, Seção 13). Mantido em
    // sincronia manual com topology_providers.py::_REGISTRY["voronoi_cell_edges_v1"].version.
    public string ProviderVersion => "0.1.0";

    public TopologyBuildResult BuildAndExport(JobInput job, string stlOutputPath) =>
        VoronoiScaffoldBuilder.BuildAndExport(job, stlOutputPath);

    public EffectiveParameters DescribeEffectiveParameters(
        JobInput job, TopologyBuildResult result, GeometryMetrics measuredMetrics,
        long estimatedVoxelCount, double estimatedMemoryMb)
    {
        var buildResult = (VoronoiScaffoldBuilder.BuildResult)result;
        var topology = job.Recipe.Topology;

        bool hasCalibration = buildResult.MeshPorosityCalibration is not null;
        double? measuredPorosityErrorPctPoints = hasCalibration
            ? measuredMetrics.PorosityPctMeasured - topology.TargetPorosityPct!.Value
            : null;
        bool? measuredPorosityWithinTolerance = hasCalibration
            ? Math.Abs(measuredPorosityErrorPctPoints!.Value) <= buildResult.PorosityToleranceUsedPctPoints
            : null;

        return new EffectiveParameters
        {
            // Campos Gyroid-específicos (wall_thickness_*, isovalue_center, seed_phase_shift_rad,
            // analytical_*) NÃO são preenchidos aqui -- ficam nos seus defaults (0.0/null),
            // documentado como intencional (ver cabeçalho deste arquivo). Os equivalentes
            // Voronoi vivem em Extra, abaixo.
            TargetPorosityPctRequested = topology.TargetPorosityPct,
            MeasuredPorosityPct = hasCalibration ? measuredMetrics.PorosityPctMeasured : null,
            PorosityTolerancePctPoints = hasCalibration ? buildResult.PorosityToleranceUsedPctPoints : null,
            MeasuredPorosityErrorPctPoints = measuredPorosityErrorPctPoints,
            MeasuredPorosityWithinTolerance = measuredPorosityWithinTolerance,
            MeshCalibrationIterations = buildResult.MeshPorosityCalibration?.Iterations,
            Seed = job.Recipe.Seed,
            Mode = job.Recipe.Mode,
            VoxelSizeRequestedMm = job.Recipe.Resolution.VoxelSizeMm,
            VoxelSizeEffectiveMm = buildResult.VoxelSizeEffectiveMm,
            EstimatedVoxelCount = estimatedVoxelCount,
            EstimatedMemoryMbUpperBound = estimatedMemoryMb,
            Extra = new Dictionary<string, object?>
            {
                ["site_count_requested"] = buildResult.SiteGeneration.RequestedSiteCount,
                ["site_count_effective"] = buildResult.SiteGeneration.Sites.Count,
                ["distribution_used"] = topology.Distribution,
                ["site_min_separation_mm_used"] = buildResult.SiteGeneration.MinSeparationMmUsed,
                ["site_generation_rejected_attempts"] = buildResult.SiteGeneration.RejectedAttempts,
                ["sites_sha256"] = buildResult.SiteGeneration.SitesSha256,
                ["nodes_and_edges_sha256"] = buildResult.Tessellation.NodesAndEdgesSha256,
                ["strut_radius_requested_mm"] = buildResult.StrutRadiusRequestedMm,
                ["strut_radius_effective_mm"] = buildResult.StrutRadiusEffectiveMm,
                ["node_radius_effective_mm"] = buildResult.NodeRadiusEffectiveMm,
                ["node_smoothing_requested"] = topology.NodeSmoothing,
                ["node_smoothing_length_mm"] = buildResult.NodeSmoothingLengthMm,
                ["boundary_behavior_used"] = topology.BoundaryBehavior ?? "clip",
                // Estratégia de suavização fixa desta rodada (Incremento 2.2, Seção 6 da
                // auditoria matemática) -- exposta como string explícita no manifesto em vez de
                // deixar implícita apenas na documentação do schema. Catmull-Clark é apenas uma
                // alternativa FUTURA documentada, nunca implementada nem equivalente.
                ["smoothing_strategy"] = "implicit_smooth_union",
            },
        };
    }

    public void PopulateMetricsExtra(GeometryMetrics metrics, TopologyBuildResult result)
    {
        var buildResult = (VoronoiScaffoldBuilder.BuildResult)result;
        var tessellation = buildResult.Tessellation;

        var edgeLengthsMm = tessellation.Edges
            .Select(e => (tessellation.Nodes[e.A] - tessellation.Nodes[e.B]).Length())
            .ToList();
        double totalStrutLengthMm = edgeLengthsMm.Sum();
        double meanStrutLengthMm = edgeLengthsMm.Count > 0 ? edgeLengthsMm.Average() : 0.0;
        double minStrutLengthMm = edgeLengthsMm.Count > 0 ? edgeLengthsMm.Min() : 0.0;
        double maxStrutLengthMm = edgeLengthsMm.Count > 0 ? edgeLengthsMm.Max() : 0.0;
        double strutLengthStdDevMm = edgeLengthsMm.Count > 1
            ? Math.Sqrt(edgeLengthsMm.Select(l => (l - meanStrutLengthMm) * (l - meanStrutLengthMm)).Average())
            : 0.0;

        var degreeByNode = new int[tessellation.Nodes.Count];
        foreach (var (a, b) in tessellation.Edges) { degreeByNode[a]++; degreeByNode[b]++; }
        double meanNodeDegree = degreeByNode.Length > 0 ? degreeByNode.Average() : 0.0;
        int minNodeDegree = degreeByNode.Length > 0 ? degreeByNode.Min() : 0;
        int maxNodeDegree = degreeByNode.Length > 0 ? degreeByNode.Max() : 0;
        double nodeDegreeStdDev = degreeByNode.Length > 1
            ? Math.Sqrt(degreeByNode.Select(d => (d - meanNodeDegree) * (d - meanNodeDegree)).Average())
            : 0.0;

        metrics.Extra = new Dictionary<string, object?>
        {
            // Conectividade TOPOLÓGICA do grafo (nunca confundir com conectividade biológica ou
            // validação experimental -- ver auditoria matemática e aviso obrigatório no frontend).
            ["site_count"] = tessellation.SiteCount,
            ["delaunay_cell_count"] = tessellation.DelaunayCellCount,
            ["degenerate_cell_count"] = tessellation.DegenerateCellCount,
            ["node_count"] = tessellation.Nodes.Count,
            ["edge_count"] = tessellation.Edges.Count,
            ["internal_edge_count"] = tessellation.InternalEdgeCount,
            ["boundary_ray_edge_count"] = tessellation.BoundaryRayEdgeCount,
            ["discarded_boundary_ray_count"] = tessellation.DiscardedBoundaryRayCount,
            ["discarded_internal_edge_count"] = tessellation.DiscardedInternalEdgeCount,
            ["connected_component_count"] = tessellation.ConnectedComponentCount,
            ["isolated_node_count"] = tessellation.IsolatedNodeCount,
            ["total_strut_length_mm"] = totalStrutLengthMm,
            ["mean_strut_length_mm"] = meanStrutLengthMm,
            ["min_strut_length_mm"] = minStrutLengthMm,
            ["max_strut_length_mm"] = maxStrutLengthMm,
            ["strut_length_stddev_mm"] = strutLengthStdDevMm,
            ["mean_node_degree"] = meanNodeDegree,
            ["min_node_degree"] = minNodeDegree,
            ["max_node_degree"] = maxNodeDegree,
            ["node_degree_stddev"] = nodeDegreeStdDev,
            // Contagem de células REALMENTE válidas (Delaunay total menos as descartadas por
            // degenerescência quase-coplanar) -- item "células válidas" da lista de métricas
            // pedida (Incremento 2.2, Seção 9), derivado por subtração exata (nunca uma segunda
            // contagem independente que poderia divergir).
            ["valid_cell_count"] = tessellation.DelaunayCellCount - tessellation.DegenerateCellCount,
            // Auditoria real de contenção no domínio (item "domain containment" da mesma lista):
            // maior violação de SDF observada entre os nós finais (0.0 = todos estritamente
            // dentro ou exatamente na superfície, dentro da tolerância de bissecção usada para
            // localizar recortes de fronteira -- ver VoronoiTessellation.DomainContainmentToleranceMm).
            ["max_node_containment_violation_mm"] = tessellation.MaxNodeContainmentViolationMm,
            ["domain_containment_verified"] =
                tessellation.MaxNodeContainmentViolationMm <= VoronoiTessellation.DomainContainmentToleranceMm,
        };
    }
}
