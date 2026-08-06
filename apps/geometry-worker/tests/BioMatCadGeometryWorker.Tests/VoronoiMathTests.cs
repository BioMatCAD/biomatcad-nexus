// Testes reais (xunit, sem PicoGK) para VoronoiSiteGenerator.cs e VoronoiTessellation.cs --
// Incremento 2.2, rodada Voronoi, Seção 12 da instrução ("TESTES"). Cobre, nesta primeira leva
// (parte pura-matemática, independente de PicoGK): determinismo/seed, contenção no domínio,
// ausência de coincidência, deduplicação, degenerescências, distinção Voronoi-vs-Delaunay,
// recorte em bloco e cilindro, componentes/nós isolados, e a invariante empírica do MIConvexHull
// (Adjacency[i] oposto a Vertices[i]) transformada em teste de regressão permanente.
using System.Linq;
using MIConvexHull;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class VoronoiSiteGeneratorTests
{
    private static RecipeDomain BlockDomain(double x, double y, double z) => new()
    {
        Shape = "block",
        DimensionsMm = new RecipeDimensions { Kind = "block", XMm = x, YMm = y, ZMm = z },
    };

    private static RecipeDomain CylinderDomain(double radius, double height) => new()
    {
        Shape = "cylinder",
        DimensionsMm = new RecipeDimensions { Kind = "cylinder", RadiusMm = radius, HeightMm = height },
    };

    [Fact]
    public void UniformRandom_MesmaSeed_ProduzMesmosSitios()
    {
        var domain = BlockDomain(10, 10, 10);
        var r1 = VoronoiSiteGenerator.GenerateUniformRandom(domain, 12, seed: 42);
        var r2 = VoronoiSiteGenerator.GenerateUniformRandom(domain, 12, seed: 42);

        Assert.Equal(r1.SitesSha256, r2.SitesSha256);
        Assert.Equal(r1.Sites.Count, r2.Sites.Count);
        for (int i = 0; i < r1.Sites.Count; i++)
        {
            Assert.Equal(r1.Sites[i].X, r2.Sites[i].X, 12);
            Assert.Equal(r1.Sites[i].Y, r2.Sites[i].Y, 12);
            Assert.Equal(r1.Sites[i].Z, r2.Sites[i].Z, 12);
        }
    }

    [Fact]
    public void UniformRandom_SeedDiferente_ProduzSitiosDiferentes()
    {
        var domain = BlockDomain(10, 10, 10);
        var r1 = VoronoiSiteGenerator.GenerateUniformRandom(domain, 12, seed: 1);
        var r2 = VoronoiSiteGenerator.GenerateUniformRandom(domain, 12, seed: 2);

        Assert.NotEqual(r1.SitesSha256, r2.SitesSha256);
    }

    [Fact]
    public void UniformRandom_TodosOsSitiosDentroDoDominioBloco()
    {
        var domain = BlockDomain(8, 6, 4);
        var result = VoronoiSiteGenerator.GenerateUniformRandom(domain, 20, seed: 7);
        foreach (var site in result.Sites)
        {
            Assert.True(VoronoiSiteGenerator.IsInsideDomain(site, domain),
                $"sítio {site} fora do domínio de bloco");
        }
    }

    [Fact]
    public void UniformRandom_TodosOsSitiosDentroDoDominioCilindro()
    {
        var domain = CylinderDomain(radius: 5, height: 10);
        var result = VoronoiSiteGenerator.GenerateUniformRandom(domain, 15, seed: 9);
        foreach (var site in result.Sites)
        {
            Assert.True(VoronoiSiteGenerator.IsInsideDomain(site, domain),
                $"sítio {site} fora do domínio de cilindro");
        }
    }

    [Fact]
    public void UniformRandom_NenhumParDeSitiosCoincidenteOuMaisPertoQueADistanciaMinima()
    {
        var domain = BlockDomain(10, 10, 10);
        var result = VoronoiSiteGenerator.GenerateUniformRandom(domain, 15, seed: 3);
        for (int i = 0; i < result.Sites.Count; i++)
        {
            for (int j = i + 1; j < result.Sites.Count; j++)
            {
                double dist = (result.Sites[i] - result.Sites[j]).Length();
                Assert.True(dist >= result.MinSeparationMmUsed - 1e-9,
                    $"sítios {i} e {j} mais próximos que a distância mínima usada ({result.MinSeparationMmUsed})");
            }
        }
    }

    [Fact]
    public void UniformRandom_SiteCountImpossivelParaODominio_LancaExcecaoEstruturada()
    {
        // Domínio minúsculo com distância mínima FORÇADA explicitamente grande demais para caber
        // 5000 sítios (esferas de exclusão de raio 0.5mm não cabem 5000 vezes em um cubo de 1mm
        // de lado por nenhuma margem) -- deve falhar de forma estruturada, nunca devolver menos
        // sítios silenciosamente. (Observação: a distância mínima DERIVADA automaticamente escala
        // com site_count e não é, por si só, garantia de infeasibilidade para qualquer contagem
        // -- por isso este teste força o parâmetro explicitamente, tornando a inviabilidade
        // inequívoca por construção, não por uma heurística.)
        var domain = BlockDomain(1, 1, 1);
        Assert.Throws<SiteGenerationException>(() =>
            VoronoiSiteGenerator.GenerateUniformRandom(
                domain, 5000, seed: 1, minSeparationMmOverride: 0.5, maxAttemptsPerSite: 20));
    }

    [Fact]
    public void JitteredGrid_MesmaSeed_Determinístico()
    {
        var domain = BlockDomain(10, 10, 10);
        var r1 = VoronoiSiteGenerator.GenerateJitteredGrid(domain, 20, seed: 5);
        var r2 = VoronoiSiteGenerator.GenerateJitteredGrid(domain, 20, seed: 5);
        Assert.Equal(r1.SitesSha256, r2.SitesSha256);
    }

    [Fact]
    public void JitteredGrid_TodosOsSitiosDentroDoDominio_MesmoEmCilindro()
    {
        var domain = CylinderDomain(radius: 6, height: 12);
        var result = VoronoiSiteGenerator.GenerateJitteredGrid(domain, 30, seed: 11);
        Assert.True(result.Sites.Count > 0, "grade jitterada não produziu nenhum sítio válido");
        foreach (var site in result.Sites)
        {
            Assert.True(VoronoiSiteGenerator.IsInsideDomain(site, domain));
        }
    }

    [Fact]
    public void JitteredGrid_ContagemEfetivaPodeSerMenorQueASolicitada_ENuncaFabricada()
    {
        // Domínio cilíndrico com grade dimensionada para um bloco tende a produzir MENOS sítios
        // que o site_count nominal (cantos da grade caem fora do cilindro) -- isto é esperado e
        // deve ser reportado com honestidade via RequestedSiteCount vs. Sites.Count, nunca
        // preenchido artificialmente até o valor solicitado.
        var domain = CylinderDomain(radius: 4, height: 4);
        var result = VoronoiSiteGenerator.GenerateJitteredGrid(domain, 64, seed: 21);
        Assert.Equal(64, result.RequestedSiteCount);
        Assert.True(result.Sites.Count <= result.RequestedSiteCount);
    }
}

public class VoronoiTessellationMathTests
{
    private static RecipeDomain BlockDomain(double x, double y, double z) => new()
    {
        Shape = "block",
        DimensionsMm = new RecipeDimensions { Kind = "block", XMm = x, YMm = y, ZMm = z },
    };

    private static RecipeDomain CylinderDomain(double radius, double height) => new()
    {
        Shape = "cylinder",
        DimensionsMm = new RecipeDimensions { Kind = "cylinder", RadiusMm = radius, HeightMm = height },
    };

    [Fact]
    public void Circumcentro_TetraedroRegularCentradoNaOrigem_ÉAProximadamenteAOrigem()
    {
        // Tetraedro regular clássico com vértices nos cantos alternados de um cubo -- seu
        // circuncentro coincide com o centróide (origem), propriedade geométrica conhecida usada
        // aqui como caso de verificação fechado (não apenas "roda sem lançar exceção").
        var p0 = new Vec3(1, 1, 1);
        var p1 = new Vec3(1, -1, -1);
        var p2 = new Vec3(-1, 1, -1);
        var p3 = new Vec3(-1, -1, 1);

        bool ok = VoronoiTessellation.TryComputeCircumcenter(p0, p1, p2, p3, out var cc);
        Assert.True(ok);
        Assert.Equal(0.0, cc.X, 9);
        Assert.Equal(0.0, cc.Y, 9);
        Assert.Equal(0.0, cc.Z, 9);
    }

    [Fact]
    public void Circumcentro_TetraedroQuaseCoplanar_ÉDetectadoComoDegenerado()
    {
        var p0 = new Vec3(0, 0, 0);
        var p1 = new Vec3(1, 0, 0);
        var p2 = new Vec3(0, 1, 0);
        var p3 = new Vec3(0.5, 0.5, 1e-12); // praticamente no mesmo plano z=0

        bool ok = VoronoiTessellation.TryComputeCircumcenter(p0, p1, p2, p3, out _);
        Assert.False(ok, "tetraedro quase-coplanar deveria ser rejeitado, não produzir um circuncentro numericamente instável");
    }

    [Fact]
    public void OutwardFaceNormal_ApontaParaLongeDoVerticeOposto()
    {
        var a = new Vec3(0, 0, 0);
        var b = new Vec3(1, 0, 0);
        var c = new Vec3(0, 1, 0);
        var opposite = new Vec3(0, 0, 1); // "acima" do plano triangular a,b,c

        var normal = VoronoiTessellation.OutwardFaceNormal(a, b, c, opposite);
        // A normal deve apontar para o lado OPOSTO ao vértice (ou seja, componente Z negativa).
        Assert.True(normal.Z < 0, $"normal {normal} deveria apontar para longe do vértice oposto (Z<0)");
        Assert.Equal(1.0, normal.Length(), 6);
    }

    [Fact]
    public void MIConvexHull_ConvençãoDeAdjacência_OpostaAoVértice_ÉAConvençãoReal()
    {
        // Regressão permanente da descoberta empírica feita via probe descartável nesta rodada:
        // duas tetraedros compartilhando uma face-base triangular -- Adjacency[slot] deve ser a
        // célula vizinha através da face formada por TODOS OS VÉRTICES EXCETO Vertices[slot].
        var v0 = new VoronoiDelaunayVertex(new Vec3(0, 0, 0), 0);
        var v1 = new VoronoiDelaunayVertex(new Vec3(1, 0, 0), 1);
        var v2 = new VoronoiDelaunayVertex(new Vec3(0, 1, 0), 2);
        var v3 = new VoronoiDelaunayVertex(new Vec3(0, 0, 1), 3);
        var v4 = new VoronoiDelaunayVertex(new Vec3(0.3, 0.3, -1), 4);

        var triangulation = Triangulation.CreateDelaunay(new List<VoronoiDelaunayVertex> { v0, v1, v2, v3, v4 });
        var cells = triangulation.Cells.ToList();
        Assert.Equal(2, cells.Count);

        foreach (var cell in cells)
        {
            var verts = cell.Vertices;
            var adjacency = cell.Adjacency;
            for (int slot = 0; slot < 4; slot++)
            {
                var neighbor = adjacency[slot];
                if (neighbor is null) continue;

                var thisFaceIndices = Enumerable.Range(0, 4)
                    .Where(k => k != slot)
                    .Select(k => verts[k].OriginalSiteIndex)
                    .OrderBy(x => x)
                    .ToArray();
                var neighborIndices = neighbor.Vertices.Select(v => v.OriginalSiteIndex).OrderBy(x => x).ToArray();
                // A face compartilhada (3 vértices desta célula, excluindo o slot) deve ser um
                // subconjunto dos vértices da célula vizinha.
                Assert.True(thisFaceIndices.All(idx => neighborIndices.Contains(idx)),
                    "face oposta ao slot não é um subconjunto dos vértices da célula vizinha -- convenção de adjacência incorreta");
            }
        }
    }

    [Fact]
    public void Compute_MenosDeQuatroSitios_LançaExceçãoEstruturada()
    {
        var domain = BlockDomain(10, 10, 10);
        var sites = new List<Vec3> { new(0, 0, 0), new(1, 0, 0), new(0, 1, 0) };
        Assert.Throws<VoronoiTessellationException>(() => VoronoiTessellation.Compute(sites, domain));
    }

    [Fact]
    public void Compute_ArestasNuncaConectamSitiosDiretamente_DistinçãoRealDeDelaunay()
    {
        // Verificação estrutural direta da distinção pedida pela auditoria matemática: um grafo
        // de ADJACÊNCIA DE DELAUNAY conectaria sítio-a-sítio; um grafo de ARESTAS DE CÉLULAS DE
        // VORONOI conecta CIRCUNCENTROS (e pontos de recorte de fronteira) -- nunca as posições
        // originais dos sítios. Nenhum nó do resultado deve coincidir com nenhum sítio de entrada.
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 10, seed: 123);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        Assert.True(tessellation.Nodes.Count > 0, "tesselação não produziu nenhum nó");
        foreach (var node in tessellation.Nodes)
        {
            foreach (var site in siteResult.Sites)
            {
                double dist = (node - site).Length();
                Assert.True(dist > 1e-6,
                    $"nó {node} coincide com um sítio original {site} -- isto seria um grafo de adjacência de Delaunay, não arestas de células de Voronoi");
            }
        }
    }

    [Fact]
    public void Compute_TodosOsNosDentroOuNaFronteiraDoDominioBloco()
    {
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 12, seed: 55);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        foreach (var node in tessellation.Nodes)
        {
            double sdf = domain.Shape == "block"
                ? GyroidMath.BoxSignedDistanceMm(node.X, node.Y, node.Z, 5, 5, 5)
                : throw new InvalidOperationException();
            Assert.True(sdf <= 1e-3, $"nó {node} fora do domínio de bloco (sdf={sdf})");
        }
    }

    [Fact]
    public void Compute_TodosOsNosDentroOuNaFronteiraDoDominioCilindro()
    {
        var domain = CylinderDomain(radius: 5, height: 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 12, seed: 77);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        foreach (var node in tessellation.Nodes)
        {
            double sdf = GyroidMath.CappedCylinderSignedDistanceMm(node.X, node.Y, node.Z + 5, 5, 10);
            Assert.True(sdf <= 1e-3, $"nó {node} fora do domínio de cilindro (sdf={sdf})");
        }
    }

    [Fact]
    public void Compute_NosSaoDeduplicadosDentroDaTolerancia()
    {
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 14, seed: 99);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain, nodeDedupeToleranceMm: 1e-4);

        for (int i = 0; i < tessellation.Nodes.Count; i++)
        {
            for (int j = i + 1; j < tessellation.Nodes.Count; j++)
            {
                double dist = (tessellation.Nodes[i] - tessellation.Nodes[j]).Length();
                Assert.True(dist > 1e-4, $"nós {i} e {j} deveriam ter sido deduplicados (distância={dist})");
            }
        }
    }

    [Fact]
    public void Compute_ArestasReferenciamIndicesValidosDeNos_ENenhumParDuplicado()
    {
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 14, seed: 100);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        var seen = new HashSet<(int, int)>();
        foreach (var (a, b) in tessellation.Edges)
        {
            Assert.InRange(a, 0, tessellation.Nodes.Count - 1);
            Assert.InRange(b, 0, tessellation.Nodes.Count - 1);
            Assert.NotEqual(a, b);
            Assert.True(a < b, "arestas devem estar em ordem canônica (A < B)");
            Assert.True(seen.Add((a, b)), $"aresta duplicada ({a},{b})");
        }
    }

    [Fact]
    public void Compute_ReportaComponentesConectadosENosIsolados_SemLancarParaCasoPequeno()
    {
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 10, seed: 200);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        Assert.True(tessellation.ConnectedComponentCount >= 1);
        Assert.True(tessellation.IsolatedNodeCount >= 0);
        Assert.True(tessellation.IsolatedNodeCount <= tessellation.Nodes.Count);
    }

    [Fact]
    public void Compute_MesmosSitiosMesmoDominio_ProduzMesmoChecksum()
    {
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 10, seed: 300);
        var t1 = VoronoiTessellation.Compute(siteResult.Sites, domain);
        var t2 = VoronoiTessellation.Compute(siteResult.Sites, domain);
        Assert.Equal(t1.NodesAndEdgesSha256, t2.NodesAndEdgesSha256);
    }

    [Fact]
    public void Compute_RegistraContagensEstruturadasDeCelulasESitios()
    {
        var domain = BlockDomain(10, 10, 10);
        var siteResult = VoronoiSiteGenerator.GenerateUniformRandom(domain, 10, seed: 400);
        var tessellation = VoronoiTessellation.Compute(siteResult.Sites, domain);

        Assert.Equal(10, tessellation.SiteCount);
        Assert.True(tessellation.DelaunayCellCount > 0);
        Assert.True(tessellation.DegenerateCellCount >= 0);
        Assert.True(tessellation.InternalEdgeCount + tessellation.BoundaryRayEdgeCount > 0);
    }
}
