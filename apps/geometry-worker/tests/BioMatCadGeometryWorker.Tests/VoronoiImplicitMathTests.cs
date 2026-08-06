// Testes reais (xunit) para VoronoiImplicitMath.cs -- Incremento 2.2, rodada Voronoi, Seção 12.
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class VoronoiImplicitMathTests
{
    [Fact]
    public void SmoothMin_KZero_ÉoMínimoDuro()
    {
        Assert.Equal(1.0, VoronoiImplicitMath.SmoothMin(1.0, 2.0, 0.0), 9);
        Assert.Equal(1.0, VoronoiImplicitMath.SmoothMin(2.0, 1.0, 0.0), 9);
    }

    [Fact]
    public void SmoothMin_ValoresIguais_ÉoMesmoValorMenosSuavizacaoMaxima()
    {
        // Em a=b, h=0.5 -> mix=a, resultado = a - k*0.25 (ponto de máxima suavização).
        double a = 5.0, k = 1.0;
        double result = VoronoiImplicitMath.SmoothMin(a, a, k);
        Assert.Equal(a - k * 0.25, result, 9);
        Assert.True(result < a, "smooth-min em valores iguais deve ser estritamente menor que o valor (fusão real dos dois primitivos)");
    }

    [Fact]
    public void SmoothMin_ConvergeParaMinimoDuroLongeDaVizinhancaDeSuavizacao()
    {
        // Quando |a-b| >> k, o resultado deve se aproximar do mínimo duro (comportamento
        // assintótico documentado do smooth-min de Quilez).
        double result = VoronoiImplicitMath.SmoothMin(0.0, 1000.0, 0.01);
        Assert.Equal(0.0, result, 6);
    }

    [Fact]
    public void SmoothMin_SempreMenorOuIgualAoMinimoDuro()
    {
        // Invariante estrutural: a fusão suave nunca "afasta" a superfície -- sempre produz uma
        // distância menor ou igual ao mínimo duro (a topologia efetivamente cresce, nunca encolhe).
        var rng = new Random(7);
        for (int i = 0; i < 200; i++)
        {
            double a = rng.NextDouble() * 20 - 10;
            double b = rng.NextDouble() * 20 - 10;
            double k = rng.NextDouble() * 5;
            double smooth = VoronoiImplicitMath.SmoothMin(a, b, k);
            double hard = Math.Min(a, b);
            Assert.True(smooth <= hard + 1e-9, $"smooth-min ({smooth}) deveria ser <= min duro ({hard}) para a={a}, b={b}, k={k}");
        }
    }

    [Fact]
    public void SmoothUnionAll_UmUnicoPrimitivo_RetornaOProprioValor()
    {
        Assert.Equal(3.5, VoronoiImplicitMath.SmoothUnionAll(new[] { 3.5 }, 0.5), 9);
    }

    [Fact]
    public void SmoothUnionAll_ListaVazia_LancaExcecaoEstruturada()
    {
        Assert.Throws<ArgumentException>(() => VoronoiImplicitMath.SmoothUnionAll(Array.Empty<double>(), 0.5));
    }

    [Fact]
    public void CapsuleSignedDistanceMm_PontoNoEixoNoMeio_DistanciaÉMenosRaio()
    {
        var a = new Vec3(0, 0, 0);
        var b = new Vec3(10, 0, 0);
        var p = new Vec3(5, 0, 0); // exatamente sobre o eixo, no meio
        double sdf = VoronoiImplicitMath.CapsuleSignedDistanceMm(p, a, b, 1.0);
        Assert.Equal(-1.0, sdf, 9);
    }

    [Fact]
    public void CapsuleSignedDistanceMm_PontoNaSuperficieLateral_DistanciaZero()
    {
        var a = new Vec3(0, 0, 0);
        var b = new Vec3(10, 0, 0);
        var p = new Vec3(5, 2, 0); // perpendicular ao eixo, a 2mm de distância radial
        double sdf = VoronoiImplicitMath.CapsuleSignedDistanceMm(p, a, b, 2.0);
        Assert.Equal(0.0, sdf, 9);
    }

    [Fact]
    public void CapsuleSignedDistanceMm_PontoAlemDaTampaUsaDistanciaEsferica()
    {
        var a = new Vec3(0, 0, 0);
        var b = new Vec3(10, 0, 0);
        var p = new Vec3(13, 0, 0); // 3mm além da tampa em b, sobre o eixo
        double sdf = VoronoiImplicitMath.CapsuleSignedDistanceMm(p, a, b, 1.0);
        Assert.Equal(2.0, sdf, 9); // 3mm de distância ao centro da tampa - 1mm de raio
    }

    [Fact]
    public void SphereSignedDistanceMm_NoCentro_ÉMenosRaio()
    {
        var center = new Vec3(1, 2, 3);
        double sdf = VoronoiImplicitMath.SphereSignedDistanceMm(center, center, 2.5);
        Assert.Equal(-2.5, sdf, 9);
    }

    [Fact]
    public void SphereSignedDistanceMm_NaSuperficie_ÉZero()
    {
        var center = new Vec3(0, 0, 0);
        var p = new Vec3(3, 0, 0);
        double sdf = VoronoiImplicitMath.SphereSignedDistanceMm(p, center, 3.0);
        Assert.Equal(0.0, sdf, 9);
    }

    [Theory]
    [InlineData(0.0, 0.5, 0.0)]
    [InlineData(1.0, 0.5, 0.5)]
    [InlineData(0.5, 0.4, 0.2)]
    public void NodeSmoothingFactorToLengthMm_MapeamentoLinearDocumentado(double factor, double strutRadius, double expected)
    {
        Assert.Equal(expected, VoronoiImplicitMath.NodeSmoothingFactorToLengthMm(factor, strutRadius), 9);
    }

    [Fact]
    public void NodeSmoothingFactorToLengthMm_ClampaForaDeZeroUm()
    {
        Assert.Equal(0.0, VoronoiImplicitMath.NodeSmoothingFactorToLengthMm(-1.0, 1.0), 9);
        Assert.Equal(1.0, VoronoiImplicitMath.NodeSmoothingFactorToLengthMm(5.0, 1.0), 9);
    }
}
