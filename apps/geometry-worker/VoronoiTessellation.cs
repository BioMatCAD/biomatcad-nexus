// Tesselação de Voronoi 3D limitada pelo domínio -- Incremento 2.2, rodada Voronoi, Seção 5 da
// instrução ("TESSELAÇÃO E GRAFO"). Ver definição matemática completa e algoritmo em
// docs/architecture/voronoi-cell-edges-v1-math-audit.md.
//
// TOTALMENTE INDEPENDENTE do PicoGK (nenhuma referência a PicoGK.Library/Voxels/Mesh neste
// arquivo) -- testável de verdade (xunit real, sem runtime nativo) mesmo com o PicoGK bloqueado
// no sandbox Linux.
//
// Resumo do que este arquivo NÃO faz, por decisão explícita (ver auditoria matemática, Seção 6):
// não usa MIConvexHull.VoronoiMesh/Triangulation.CreateVoronoi (a leitura do código-fonte da
// biblioteca confirmou que essa função pronta descarta silenciosamente as faces de fronteira do
// casco convexo, isto é, nunca produz as arestas não-limitadas que esta implementação precisa) --
// usa apenas MIConvexHull.Triangulation.CreateDelaunay (tetraedralização de Delaunay) e implementa
// por conta própria, aqui, a extração de arestas de Voronoi a partir da dualidade Delaunay/Voronoi
// (face de Delaunay <-> aresta de Voronoi), incluindo o tratamento de raios de fronteira.
using MIConvexHull;

namespace BioMatCadGeometryWorker;

/// <summary>Vértice mínimo exigido pela interface MIConvexHull.IVertex, carregando o índice do
/// sítio original (na ordem canônica produzida por VoronoiSiteGenerator) para que o resultado da
/// tesselação sempre possa ser rastreado de volta ao sítio que o gerou (auditoria).</summary>
public sealed class VoronoiDelaunayVertex : MIConvexHull.IVertex
{
    public double[] Position { get; set; }
    public int OriginalSiteIndex { get; }

    public VoronoiDelaunayVertex(Vec3 site, int originalSiteIndex)
    {
        Position = new[] { site.X, site.Y, site.Z };
        OriginalSiteIndex = originalSiteIndex;
    }
}

/// <summary>Lançada quando a tesselação de Delaunay 3D não pôde ser concluída de forma confiável
/// (ex.: menos de 4 sítios, todos os sítios coplanares/colineares, ou a biblioteca subjacente
/// reporta falha) -- nunca substituída silenciosamente por uma aproximação (ex.: grafo de
/// adjacência de sítios) rotulada incorretamente como "arestas de Voronoi".</summary>
public sealed class VoronoiTessellationException : Exception
{
    public string Reason { get; }

    public VoronoiTessellationException(string reason)
        : base($"Não foi possível concluir a tesselação de Voronoi 3D de forma confiável: {reason}")
    {
        Reason = reason;
    }
}

public sealed class VoronoiTessellationResult
{
    /// <summary>Nós do grafo (circuncentros de células de Delaunay válidas + pontos de recorte de
    /// raios de fronteira na superfície do domínio), em ordem CANÔNICA (X, depois Y, depois Z).</summary>
    public IReadOnlyList<Vec3> Nodes { get; init; } = Array.Empty<Vec3>();

    /// <summary>Arestas como pares de índices em Nodes, com A &lt; B sempre, ordenadas
    /// canonicamente (por A, depois por B) -- determinístico e independente da ordem de
    /// descoberta interna.</summary>
    public IReadOnlyList<(int A, int B)> Edges { get; init; } = Array.Empty<(int, int)>();

    public int SiteCount { get; init; }
    public int DelaunayCellCount { get; init; }
    public int DegenerateCellCount { get; init; }
    public int InternalEdgeCount { get; init; }
    public int BoundaryRayEdgeCount { get; init; }
    public int DiscardedBoundaryRayCount { get; init; }
    public int DiscardedInternalEdgeCount { get; init; }
    public int ConnectedComponentCount { get; init; }
    public int IsolatedNodeCount { get; init; }
    public string NodesAndEdgesSha256 { get; init; } = "";

    /// <summary>Auditoria real de contenção no domínio (Incremento 2.2, Seção 9 -- item
    /// "domain containment" da lista de métricas pedida): maior valor, entre todos os nós
    /// finais (internos + pontos de recorte de raio de fronteira), da SDF do domínio avaliada
    /// naquele nó, restrita a >= 0 (nós estritamente internos têm SDF negativa e não contam
    /// aqui). Um nó verdadeiramente interno ou exatamente na superfície contribui 0 (ou um valor
    /// próximo de 0 vindo apenas do erro de ponto flutuante da bissecção que localizou o recorte,
    /// ver DomainContainmentToleranceMm); qualquer valor MAIOR que essa tolerância indica um nó
    /// genuinamente fora do domínio -- um bug real, nunca esperado por construção, e nunca
    /// escondido ou arredondado para zero.</summary>
    public double MaxNodeContainmentViolationMm { get; init; }
}

public static class VoronoiTessellation
{
    /// <summary>Tolerância relativa (adimensional) usada para detectar tetraedros degenerados
    /// (quase-coplanares): o determinante do sistema 3x3 do circuncentro é comparado contra
    /// relativeDegenerateTolerance * (comprimento característico do tetraedro)^3 -- ver auditoria
    /// matemática, Seção "Circuncentro e degenerescências".</summary>
    public const double DefaultRelativeDegenerateTolerance = 1e-9;

    /// <summary>Fator de segurança aplicado ao comprimento da diagonal do domínio para limitar a
    /// distância máxima de marcha de um raio de fronteira -- um domínio convexo garante que,
    /// partindo de um ponto interno, a fronteira sempre é alcançada bem antes desta distância;
    /// se não for alcançada, é tratado como um caso degenerado estruturado, nunca como loop
    /// infinito.</summary>
    private const double BoundaryRayMaxLengthSafetyFactor = 3.0;

    /// <summary>Tolerância (mm) usada apenas para AUDITORIA pós-hoc de contenção no domínio
    /// (MaxNodeContainmentViolationMm) -- mesma ordem de grandeza de nodeDedupeToleranceMm, uma
    /// margem pequena e explícita para o erro de ponto flutuante acumulado da bissecção que
    /// localiza pontos de recorte na superfície (bisectionToleranceMm=1e-6 por passo, múltiplos
    /// passos por raio). Não afeta nenhum cálculo geométrico -- só rotula o resultado.</summary>
    public const double DomainContainmentToleranceMm = 1e-4;

    private static Vec3 Add(Vec3 a, Vec3 b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
    private static Vec3 Scale(Vec3 a, double s) => new(a.X * s, a.Y * s, a.Z * s);

    private static Vec3 Normalize(Vec3 v)
    {
        double len = v.Length();
        if (len <= 0.0 || double.IsNaN(len) || double.IsInfinity(len))
        {
            throw new VoronoiTessellationException(
                "vetor de direção nulo ou inválido ao normalizar (face degenerada de área zero)");
        }
        return new Vec3(v.X / len, v.Y / len, v.Z / len);
    }

    private static bool IsFiniteVec3(Vec3 v) =>
        !double.IsNaN(v.X) && !double.IsNaN(v.Y) && !double.IsNaN(v.Z) &&
        !double.IsInfinity(v.X) && !double.IsInfinity(v.Y) && !double.IsInfinity(v.Z);

    /// <summary>Diagonal da caixa delimitadora do domínio -- usada como comprimento
    /// característico para tolerâncias relativas e como limite de marcha de raios de fronteira.</summary>
    private static double DomainDiagonalMm(RecipeDomain domain)
    {
        var d = domain.DimensionsMm;
        return domain.Shape switch
        {
            "block" => new Vec3(d.XMm ?? 0, d.YMm ?? 0, d.ZMm ?? 0).Length(),
            "cylinder" => Math.Sqrt(
                4.0 * (d.RadiusMm ?? 0) * (d.RadiusMm ?? 0) + (d.HeightMm ?? 0) * (d.HeightMm ?? 0)),
            _ => throw new NotSupportedException($"Domínio não suportado: {domain.Shape}"),
        };
    }

    private static double SignedDistanceToDomain(Vec3 p, RecipeDomain domain)
    {
        var d = domain.DimensionsMm;
        return domain.Shape switch
        {
            "block" => GyroidMath.BoxSignedDistanceMm(
                p.X, p.Y, p.Z, (d.XMm ?? 0) / 2.0, (d.YMm ?? 0) / 2.0, (d.ZMm ?? 0) / 2.0),
            "cylinder" => GyroidMath.CappedCylinderSignedDistanceMm(
                p.X, p.Y, p.Z + (d.HeightMm ?? 0) / 2.0, d.RadiusMm ?? 0, d.HeightMm ?? 0),
            _ => throw new NotSupportedException($"Domínio não suportado: {domain.Shape}"),
        };
    }

    /// <summary>Circuncentro de um tetraedro via solução direta do sistema linear 3x3 (regra de
    /// Cramer) -- ver fórmula fechada na auditoria matemática. Retorna false (sem lançar exceção)
    /// quando o tetraedro é degenerado (quase-coplanar): o CHAMADOR decide o que fazer (aqui:
    /// descartar a célula e contar como degenerada), nunca propagamos NaN/Infinity adiante.</summary>
    internal static bool TryComputeCircumcenter(Vec3 p0, Vec3 p1, Vec3 p2, Vec3 p3, out Vec3 circumcenter,
        double relativeDegenerateTolerance = DefaultRelativeDegenerateTolerance)
    {
        circumcenter = default;

        // Linha i: 2*(Pi - P0), i = 1,2,3. Lado direito: |Pi|^2 - |P0|^2.
        double ax = 2 * (p1.X - p0.X), ay = 2 * (p1.Y - p0.Y), az = 2 * (p1.Z - p0.Z);
        double bx = 2 * (p2.X - p0.X), by = 2 * (p2.Y - p0.Y), bz = 2 * (p2.Z - p0.Z);
        double cx = 2 * (p3.X - p0.X), cy = 2 * (p3.Y - p0.Y), cz = 2 * (p3.Z - p0.Z);

        double p0sq = p0.X * p0.X + p0.Y * p0.Y + p0.Z * p0.Z;
        double r1 = (p1.X * p1.X + p1.Y * p1.Y + p1.Z * p1.Z) - p0sq;
        double r2 = (p2.X * p2.X + p2.Y * p2.Y + p2.Z * p2.Z) - p0sq;
        double r3 = (p3.X * p3.X + p3.Y * p3.Y + p3.Z * p3.Z) - p0sq;

        double det = ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx);

        // Comprimento característico do tetraedro (média das distâncias de p0 aos outros 3
        // vértices) -- usado para tornar a tolerância de degenerescência relativa à escala do
        // modelo, nunca um valor absoluto arbitrário (ver auditoria matemática).
        double charLength = ((p1 - p0).Length() + (p2 - p0).Length() + (p3 - p0).Length()) / 3.0;
        double scaleCubed = charLength * charLength * charLength;
        if (scaleCubed <= 0.0 || Math.Abs(det) < relativeDegenerateTolerance * scaleCubed)
        {
            return false;
        }

        // Regra de Cramer: substitui cada coluna pelo vetor (r1,r2,r3) e divide pelo determinante
        // principal.
        double detX =
            r1 * (by * cz - bz * cy) - ay * (r2 * cz - bz * r3) + az * (r2 * cy - by * r3);
        double detY =
            ax * (r2 * cz - bz * r3) - r1 * (bx * cz - bz * cx) + az * (bx * r3 - r2 * cx);
        double detZ =
            ax * (by * r3 - r2 * cy) - ay * (bx * r3 - r2 * cx) + r1 * (bx * cy - by * cx);

        var c = new Vec3(detX / det, detY / det, detZ / det);
        if (!IsFiniteVec3(c)) return false;

        circumcenter = c;
        return true;
    }

    /// <summary>Normal de face APONTANDO PARA FORA do tetraedro (para longe do vértice oposto) --
    /// calculada diretamente a partir dos 3 vértices da face, sem depender do campo Normal do
    /// MIConvexHull (que não é preenchido por Triangulation.CreateDelaunay, apenas por
    /// ConvexHull.Create -- verificado empiricamente, não assumido).</summary>
    internal static Vec3 OutwardFaceNormal(Vec3 faceA, Vec3 faceB, Vec3 faceC, Vec3 oppositeVertex)
    {
        var normal = Vec3.Cross(faceB - faceA, faceC - faceA);
        if (Vec3.Dot(normal, oppositeVertex - faceA) > 0)
        {
            normal = Scale(normal, -1.0);
        }
        return Normalize(normal);
    }

    /// <summary>Marcha um raio a partir de origin (assumido dentro do domínio, SDF &lt;= 0) na
    /// direção (unitária) direction até encontrar o cruzamento com a fronteira do domínio
    /// (SDF = 0), refinando por bisseção -- mesma técnica de bisseção genérica já usada em
    /// GyroidMath (CalibrateByMonotonicBisection), aplicada aqui a uma função geométrica em vez de
    /// uma função de porosidade. Retorna false se nenhum cruzamento for encontrado dentro do
    /// limite de marcha (não deveria ocorrer para um domínio convexo com origem interna --
    /// tratado como caso degenerado estruturado pelo chamador).</summary>
    internal static bool TryClipRayToDomainBoundary(
        Vec3 origin, Vec3 direction, RecipeDomain domain, out Vec3 boundaryPoint,
        double bisectionToleranceMm = 1e-6, int maxBisectionIterations = 60)
    {
        boundaryPoint = default;
        double maxLength = DomainDiagonalMm(domain) * BoundaryRayMaxLengthSafetyFactor;
        double stepMm = Math.Max(maxLength / 512.0, 1e-4);

        double sdfAtOrigin = SignedDistanceToDomain(origin, domain);
        if (sdfAtOrigin > 0.0) return false; // chamador deve verificar isto antes; guarda defensiva

        double tPrevInside = 0.0;
        double distanceMarched = 0.0;
        while (distanceMarched < maxLength)
        {
            double tNext = distanceMarched + stepMm;
            var candidate = Add(origin, Scale(direction, tNext));
            double sdf = SignedDistanceToDomain(candidate, domain);
            if (sdf > 0.0)
            {
                // Cruzamento entre tPrevInside (dentro) e tNext (fora) -- refina por bisseção.
                double lo = tPrevInside, hi = tNext;
                for (int i = 0; i < maxBisectionIterations && (hi - lo) > bisectionToleranceMm; i++)
                {
                    double mid = (lo + hi) / 2.0;
                    var midPoint = Add(origin, Scale(direction, mid));
                    double midSdf = SignedDistanceToDomain(midPoint, domain);
                    if (midSdf > 0.0) hi = mid; else lo = mid;
                }
                boundaryPoint = Add(origin, Scale(direction, (lo + hi) / 2.0));
                return IsFiniteVec3(boundaryPoint);
            }
            tPrevInside = tNext;
            distanceMarched = tNext;
        }
        return false;
    }

    /// <summary>Recorta o SEGMENTO entre um ponto confirmadamente dentro do domínio
    /// (insidePoint, SDF &lt;= 0) e um ponto confirmadamente fora (outsidePoint, SDF &gt; 0),
    /// por bisseção direta no parâmetro t em [0,1] -- ao contrário de TryClipRayToDomainBoundary
    /// (usado para raios não-limitados de fronteira, que precisam de uma marcha inicial para
    /// encontrar QUALQUER cruzamento), aqui já temos as duas pontas do intervalo de bisseção de
    /// antemão (o próprio segmento interno candidato entre dois circuncentros), então a bisseção
    /// direta é suficiente e não precisa de passo de marcha.</summary>
    internal static bool TryClipSegmentToDomainBoundary(
        Vec3 insidePoint, Vec3 outsidePoint, RecipeDomain domain, out Vec3 boundaryPoint,
        double bisectionToleranceMm = 1e-6, int maxBisectionIterations = 60)
    {
        boundaryPoint = default;
        double sdfInside = SignedDistanceToDomain(insidePoint, domain);
        double sdfOutside = SignedDistanceToDomain(outsidePoint, domain);
        if (sdfInside > 0.0 || sdfOutside <= 0.0) return false; // guarda defensiva; chamador já verificou

        double segmentLength = (outsidePoint - insidePoint).Length();
        if (segmentLength <= 0.0 || double.IsNaN(segmentLength) || double.IsInfinity(segmentLength)) return false;

        double lo = 0.0, hi = 1.0;
        Vec3 PointAt(double t) => Add(insidePoint, Scale(outsidePoint - insidePoint, t));
        for (int i = 0; i < maxBisectionIterations && (hi - lo) * segmentLength > bisectionToleranceMm; i++)
        {
            double mid = (lo + hi) / 2.0;
            double sdfMid = SignedDistanceToDomain(PointAt(mid), domain);
            if (sdfMid > 0.0) hi = mid; else lo = mid;
        }
        boundaryPoint = PointAt((lo + hi) / 2.0);
        return IsFiniteVec3(boundaryPoint);
    }

    private sealed class UnionFind
    {
        private readonly int[] _parent;
        public UnionFind(int n) { _parent = new int[n]; for (int i = 0; i < n; i++) _parent[i] = i; }
        public int Find(int x) => _parent[x] == x ? x : (_parent[x] = Find(_parent[x]));
        public void Union(int a, int b) { int ra = Find(a), rb = Find(b); if (ra != rb) _parent[ra] = rb; }
    }

    /// <summary>Ponto de entrada principal: recebe os sítios canônicos (já gerados por
    /// VoronoiSiteGenerator) e o domínio, e produz o grafo real de arestas de células de Voronoi
    /// 3D recortado pelo domínio. Lança VoronoiTessellationException em vez de prosseguir
    /// silenciosamente se a tesselação de Delaunay subjacente não puder ser concluída.</summary>
    public static VoronoiTessellationResult Compute(
        IReadOnlyList<Vec3> sites, RecipeDomain domain,
        double nodeDedupeToleranceMm = 1e-4,
        double relativeDegenerateTolerance = DefaultRelativeDegenerateTolerance)
    {
        if (sites.Count < 4)
        {
            throw new VoronoiTessellationException(
                $"são necessários pelo menos 4 sítios não-coplanares para uma tesselação 3D válida " +
                $"(recebidos: {sites.Count})");
        }

        var vertices = new List<VoronoiDelaunayVertex>(sites.Count);
        for (int i = 0; i < sites.Count; i++) vertices.Add(new VoronoiDelaunayVertex(sites[i], i));

        ITriangulation<VoronoiDelaunayVertex, DefaultTriangulationCell<VoronoiDelaunayVertex>> triangulation;
        try
        {
            triangulation = Triangulation.CreateDelaunay(vertices);
        }
        catch (Exception ex)
        {
            // Nunca substitui por uma aproximação mal rotulada -- declara o bloqueio de forma
            // estruturada (ver instrução do usuário, Seção 5: "Se a tesselação real não puder ser
            // concluída de forma confiável nesta rodada, pare e declare o bloqueio").
            throw new VoronoiTessellationException(
                $"MIConvexHull.Triangulation.CreateDelaunay falhou: {ex.GetType().Name}: {ex.Message}");
        }

        var cells = triangulation.Cells.ToList();
        if (cells.Count == 0)
        {
            throw new VoronoiTessellationException(
                "a tetraedralização de Delaunay não produziu nenhuma célula (sítios provavelmente " +
                "coplanares/colineares/coincidentes)");
        }

        // Passo 1: circuncentro de cada célula; células degeneradas são marcadas inválidas (nunca
        // propagadas como NaN/Infinity) mas mantêm seu índice posicional na lista `cells` para que
        // Adjacency[i] (índice posicional na lista original do MIConvexHull) continue válido.
        var circumcenters = new Vec3[cells.Count];
        var cellIsValid = new bool[cells.Count];
        int degenerateCount = 0;
        // Mapa célula-MIConvexHull -> índice posicional na lista `cells` (identidade de
        // referência, já que TriangulationCell não sobrescreve Equals/GetHashCode de forma útil
        // para isto -- usamos ReferenceEqualityComparer explicitamente por segurança).
        var cellIndexByRef = new Dictionary<DefaultTriangulationCell<VoronoiDelaunayVertex>, int>(
            ReferenceEqualityComparer.Instance);
        for (int i = 0; i < cells.Count; i++) cellIndexByRef[cells[i]] = i;

        for (int i = 0; i < cells.Count; i++)
        {
            var v = cells[i].Vertices;
            bool ok = TryComputeCircumcenter(
                new Vec3(v[0].Position[0], v[0].Position[1], v[0].Position[2]),
                new Vec3(v[1].Position[0], v[1].Position[1], v[1].Position[2]),
                new Vec3(v[2].Position[0], v[2].Position[1], v[2].Position[2]),
                new Vec3(v[3].Position[0], v[3].Position[1], v[3].Position[2]),
                out var cc, relativeDegenerateTolerance);
            cellIsValid[i] = ok;
            circumcenters[i] = ok ? cc : default;
            if (!ok) degenerateCount++;
        }

        // Passo 2: nós canônicos com deduplicação por tolerância explícita (varredura linear --
        // aceitável para as receitas pequenas exigidas nesta rodada; ver auditoria matemática,
        // Seção "Complexidade").
        var nodeList = new List<Vec3>();

        int FindOrAddNode(Vec3 p)
        {
            for (int i = 0; i < nodeList.Count; i++)
            {
                var d = p - nodeList[i];
                if (d.Length() <= nodeDedupeToleranceMm) return i;
            }
            nodeList.Add(p);
            return nodeList.Count - 1;
        }

        // circumcenterNodeId[i] só é atribuído SOB DEMANDA, e SOMENTE quando o circuncentro da
        // célula i está de fato dentro do domínio (SDF <= 0) -- um circuncentro fora do domínio
        // nunca vira nó por si só; ele só participa do grafo através de um ponto de recorte
        // calculado (ver GetInsideCircumcenterNodeId / recorte de segmento abaixo). Isto evita
        // que circuncentros de tetraedros válidos mas muito obtusos/"sliver" perto da fronteira
        // (numericamente corretos, porém geometricamente distantes do domínio -- um efeito
        // conhecido da dualidade Delaunay/Voronoi, não um bug de tetraedro degenerado) apareçam
        // como nós soltos muito fora do domínio no grafo final.
        var circumcenterNodeId = new int[cells.Count];
        for (int i = 0; i < circumcenterNodeId.Length; i++) circumcenterNodeId[i] = -1;

        int GetInsideCircumcenterNodeId(int cellIdx)
        {
            if (circumcenterNodeId[cellIdx] == -1)
            {
                circumcenterNodeId[cellIdx] = FindOrAddNode(circumcenters[cellIdx]);
            }
            return circumcenterNodeId[cellIdx];
        }

        // Passo 3: extração das arestas reais das células de Voronoi (dualidade face de Delaunay
        // <-> aresta de Voronoi). Internas: segmento entre os circuncentros de duas células
        // adjacentes válidas -- RECORTADO pelo domínio se um ou ambos os circuncentros caírem
        // fora dele (não apenas as arestas de fronteira/raio precisam de recorte: um tetraedro de
        // Delaunay interno e válido ainda pode ter um circuncentro geometricamente distante,
        // inclusive fora do domínio, perto da fronteira -- ver auditoria matemática). Fronteira:
        // raio não-limitado do circuncentro na direção da normal externa da face de fronteira,
        // recortado pela SDF do domínio.
        var edgeSet = new HashSet<(int A, int B)>();
        int internalEdgeCount = 0, boundaryRayCount = 0;
        int discardedBoundaryRayCount = 0, discardedInternalEdgeCount = 0;

        void AddEdge(int a, int b)
        {
            if (a == b) return;
            var key = a < b ? (a, b) : (b, a);
            edgeSet.Add(key);
        }

        for (int i = 0; i < cells.Count; i++)
        {
            if (!cellIsValid[i]) continue;
            var cell = cells[i];
            var verts = cell.Vertices;
            var adjacency = cell.Adjacency; // Adjacency[k] = célula vizinha através da face OPOSTA a Vertices[k] (convenção empiricamente verificada -- ver probe descartável e VoronoiMathTests.MIConvexHull_ConvençãoDeAdjacência_OpostaAoVértice_ÉAConvençãoReal)

            for (int slot = 0; slot < 4; slot++)
            {
                var neighborCell = adjacency[slot];
                if (neighborCell is not null)
                {
                    if (!cellIndexByRef.TryGetValue(neighborCell, out int neighborIndex))
                    {
                        continue; // não deveria ocorrer; defensivo
                    }
                    if (neighborIndex <= i) continue; // processa cada par de células apenas uma vez
                    if (!cellIsValid[neighborIndex]) continue; // vizinho degenerado: aresta interna descartada

                    var ccA = circumcenters[i];
                    var ccB = circumcenters[neighborIndex];
                    bool aInside = SignedDistanceToDomain(ccA, domain) <= 0.0;
                    bool bInside = SignedDistanceToDomain(ccB, domain) <= 0.0;

                    if (aInside && bInside)
                    {
                        AddEdge(GetInsideCircumcenterNodeId(i), GetInsideCircumcenterNodeId(neighborIndex));
                        internalEdgeCount++;
                    }
                    else if (aInside && !bInside)
                    {
                        if (TryClipSegmentToDomainBoundary(ccA, ccB, domain, out var clipped))
                        {
                            AddEdge(GetInsideCircumcenterNodeId(i), FindOrAddNode(clipped));
                            internalEdgeCount++;
                        }
                        else discardedInternalEdgeCount++;
                    }
                    else if (!aInside && bInside)
                    {
                        if (TryClipSegmentToDomainBoundary(ccB, ccA, domain, out var clipped))
                        {
                            AddEdge(FindOrAddNode(clipped), GetInsideCircumcenterNodeId(neighborIndex));
                            internalEdgeCount++;
                        }
                        else discardedInternalEdgeCount++;
                    }
                    else
                    {
                        // Ambos os circuncentros fora do domínio -- descartado por simplicidade
                        // nesta primeira implementação (documentado como limitação honesta na
                        // auditoria matemática): não tentamos recuperar um eventual cruzamento
                        // duplo do segmento com um domínio convexo neste caso.
                        discardedInternalEdgeCount++;
                    }
                    continue;
                }

                // Face de fronteira (sem vizinho): raio não-limitado, recortado pelo domínio.
                var oppositeVertexPos = verts[slot].Position;
                var oppositeVertex = new Vec3(oppositeVertexPos[0], oppositeVertexPos[1], oppositeVertexPos[2]);
                Vec3 fa = default, fb = default, fc = default;
                int faceVertexCount = 0;
                for (int k = 0; k < 4; k++)
                {
                    if (k == slot) continue;
                    var p = verts[k].Position;
                    var vp = new Vec3(p[0], p[1], p[2]);
                    if (faceVertexCount == 0) fa = vp;
                    else if (faceVertexCount == 1) fb = vp;
                    else fc = vp;
                    faceVertexCount++;
                }

                var origin = circumcenters[i];
                if (SignedDistanceToDomain(origin, domain) > 0.0)
                {
                    // Circuncentro da própria célula já está fora do domínio -- o raio de
                    // fronteira associado não é utilizável de forma confiável (não há um segmento
                    // "de dentro para fora" bem definido a partir de um início externo).
                    // Descartado honestamente, contado para auditoria, nunca fabricado.
                    discardedBoundaryRayCount++;
                    continue;
                }

                Vec3 direction;
                try
                {
                    direction = OutwardFaceNormal(fa, fb, fc, oppositeVertex);
                }
                catch (VoronoiTessellationException)
                {
                    discardedBoundaryRayCount++;
                    continue;
                }

                if (!TryClipRayToDomainBoundary(origin, direction, domain, out var boundaryPoint))
                {
                    discardedBoundaryRayCount++;
                    continue;
                }

                int boundaryNodeId = FindOrAddNode(boundaryPoint);
                AddEdge(GetInsideCircumcenterNodeId(i), boundaryNodeId);
                boundaryRayCount++;
            }
        }

        // Passo 4: rejeição de NaN/Infinity remanescente (defensivo -- TryComputeCircumcenter e
        // TryClipRayToDomainBoundary já filtram na origem, mas o grafo final é verificado de novo
        // antes de ser considerado "canônico").
        for (int i = 0; i < nodeList.Count; i++)
        {
            if (!IsFiniteVec3(nodeList[i]))
            {
                throw new VoronoiTessellationException(
                    $"nó {i} do grafo de Voronoi contém coordenada NaN/Infinity após a extração -- " +
                    "bloqueio estrutural, geometria não gerada");
            }
        }

        // Passo 5: canonicalização -- reordena nós por (X,Y,Z) e remapeia todos os índices de
        // aresta, para que o resultado final não dependa de nenhuma ordem de descoberta interna
        // (apenas do CONJUNTO determinístico produzido pela seed).
        var order = Enumerable.Range(0, nodeList.Count)
            .OrderBy(i => nodeList[i].X).ThenBy(i => nodeList[i].Y).ThenBy(i => nodeList[i].Z)
            .ToList();
        var oldToNewIndex = new int[nodeList.Count];
        for (int newIdx = 0; newIdx < order.Count; newIdx++) oldToNewIndex[order[newIdx]] = newIdx;
        var canonicalNodes = order.Select(oldIdx => nodeList[oldIdx]).ToList();

        var canonicalEdges = edgeSet
            .Select(e =>
            {
                int a = oldToNewIndex[e.A];
                int b = oldToNewIndex[e.B];
                return a < b ? (A: a, B: b) : (A: b, B: a);
            })
            .Distinct()
            .OrderBy(e => e.A).ThenBy(e => e.B)
            .ToList();

        // Passo 6: conectividade (componentes) e nós isolados.
        var uf = new UnionFind(canonicalNodes.Count);
        foreach (var (a, b) in canonicalEdges) uf.Union(a, b);
        var degree = new int[canonicalNodes.Count];
        foreach (var (a, b) in canonicalEdges) { degree[a]++; degree[b]++; }
        int isolatedNodeCount = degree.Count(deg => deg == 0);
        int componentCount = Enumerable.Range(0, canonicalNodes.Count).Select(uf.Find).Distinct().Count();

        string checksum = ComputeNodesAndEdgesSha256(canonicalNodes, canonicalEdges);

        double maxContainmentViolationMm = canonicalNodes.Count > 0
            ? canonicalNodes.Max(n => Math.Max(0.0, SignedDistanceToDomain(n, domain)))
            : 0.0;

        return new VoronoiTessellationResult
        {
            Nodes = canonicalNodes,
            Edges = canonicalEdges,
            SiteCount = sites.Count,
            DelaunayCellCount = cells.Count,
            DegenerateCellCount = degenerateCount,
            InternalEdgeCount = internalEdgeCount,
            BoundaryRayEdgeCount = boundaryRayCount,
            DiscardedBoundaryRayCount = discardedBoundaryRayCount,
            DiscardedInternalEdgeCount = discardedInternalEdgeCount,
            ConnectedComponentCount = componentCount,
            IsolatedNodeCount = isolatedNodeCount,
            NodesAndEdgesSha256 = checksum,
            MaxNodeContainmentViolationMm = maxContainmentViolationMm,
        };
    }

    private static string ComputeNodesAndEdgesSha256(IReadOnlyList<Vec3> nodes, IReadOnlyList<(int A, int B)> edges)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var n in nodes)
        {
            sb.Append(n.X.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(';');
            sb.Append(n.Y.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append(';');
            sb.Append(n.Z.ToString("R", System.Globalization.CultureInfo.InvariantCulture)).Append('\n');
        }
        sb.Append("EDGES\n");
        foreach (var (a, b) in edges) sb.Append(a).Append(',').Append(b).Append('\n');
        byte[] bytes = System.Text.Encoding.UTF8.GetBytes(sb.ToString());
        byte[] hash = System.Security.Cryptography.SHA256.HashData(bytes);
        return Convert.ToHexStringLower(hash);
    }
}
