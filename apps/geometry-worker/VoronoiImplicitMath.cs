// Matemática implícita pura (SDF de cápsula/esfera + smooth-min polinomial) para os struts e nós
// do VoronoiTopologyProvider -- Incremento 2.2, rodada Voronoi, Seção 6 da instrução
// ("STRUTS E SUAVIZAÇÃO DOS NÓS"), parte PicoGK-independente.
//
// TOTALMENTE INDEPENDENTE do PicoGK (nenhuma referência a PicoGK.Library/Voxels/Mesh neste
// arquivo) -- testável de verdade (xunit real, sem runtime nativo) mesmo com o PicoGK bloqueado
// no sandbox Linux, mesmo padrão já usado por GyroidMath.cs para a topologia Gyroid.
//
// Estratégia fixa desta rodada (decidida na auditoria matemática, Seção 6, e confirmada pela
// instrução do usuário): implicit_smooth_union -- cada aresta de Voronoi vira uma cápsula
// implícita (cilindro com tampas esféricas), cada nó vira uma esfera implícita, e a união entre
// todos os primitivos é feita por um smooth-min polinomial (Inigo Quilez, técnica de domínio
// público amplamente documentada), NÃO por uma união booleana dura (que produziria nós
// pontiagudos/vincados) e NÃO por Catmull-Clark (documentado como alternativa futura na
// auditoria matemática, nunca alegado como equivalente a este parâmetro).
namespace BioMatCadGeometryWorker;

public static class VoronoiImplicitMath
{
    /// <summary>Smooth-min polinomial de Quilez -- para k&lt;=0 degenera para o mínimo duro
    /// (união booleana sem suavização, útil como caso limite testável). Para k&gt;0, produz uma
    /// transição suave entre as duas distâncias, com o "excesso" de suavização limitado a
    /// aproximadamente k (fora dessa vizinhança, o resultado converge para o mínimo duro).</summary>
    public static double SmoothMin(double a, double b, double k)
    {
        if (k <= 0.0) return Math.Min(a, b);
        double h = Math.Clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
        double mix = b * (1.0 - h) + a * h;
        return mix - k * h * (1.0 - h);
    }

    /// <summary>Dobra (fold) o smooth-min sobre uma sequência de distâncias -- união suave de N
    /// primitivos. Lança se a sequência estiver vazia (chamador deve garantir pelo menos um
    /// primitivo; uma malha de scaffold sem nenhum strut/nó não é um caso válido para esta
    /// função, é um caso a ser tratado antes, na camada que decide se há geometria alguma a
    /// gerar).</summary>
    public static double SmoothUnionAll(IReadOnlyList<double> distances, double k)
    {
        if (distances.Count == 0)
        {
            throw new ArgumentException("SmoothUnionAll requer pelo menos uma distância -- nenhum primitivo fornecido.");
        }
        double result = distances[0];
        for (int i = 1; i < distances.Count; i++)
        {
            result = SmoothMin(result, distances[i], k);
        }
        return result;
    }

    /// <summary>SDF de uma cápsula (cilindro reto com tampas semiesféricas) entre os pontos a e
    /// b, raio r -- técnica de domínio público amplamente documentada (Quilez, "distance
    /// functions"). Convenção negativo-dentro/positivo-fora, mesma convenção assumida pelo
    /// PicoGK.Voxels já usada por GyroidDomainImplicit.</summary>
    public static double CapsuleSignedDistanceMm(Vec3 p, Vec3 a, Vec3 b, double radiusMm)
    {
        var pa = p - a;
        var ba = b - a;
        double baDot = Vec3.Dot(ba, ba);
        double h = baDot > 0.0 ? Math.Clamp(Vec3.Dot(pa, ba) / baDot, 0.0, 1.0) : 0.0;
        var closest = new Vec3(a.X + ba.X * h, a.Y + ba.Y * h, a.Z + ba.Z * h);
        return (p - closest).Length() - radiusMm;
    }

    /// <summary>SDF de uma esfera centrada em center, raio r.</summary>
    public static double SphereSignedDistanceMm(Vec3 p, Vec3 center, double radiusMm) =>
        (p - center).Length() - radiusMm;

    /// <summary>Mapeamento documentado desta primeira implementação entre o fator adimensional
    /// node_smoothing (0..1, schema da receita) e o comprimento de suavização k (mm) do
    /// smooth-min: k = node_smoothing * strut_radius_mm. Linear e simples de propósito --
    /// node_smoothing=0 produz união dura (min exato, nós potencialmente pontiagudos);
    /// node_smoothing=1 produz um comprimento de suavização igual ao próprio raio do strut
    /// (blend generoso, adequado para evitar lacunas/vincos na maioria dos casos pequenos desta
    /// rodada). Documentado como mapeamento inicial, não uma relação física exata -- sujeito a
    /// refinamento após validação visual real no Windows (ver roteiro de validação, Seção 13).</summary>
    public static double NodeSmoothingFactorToLengthMm(double nodeSmoothingFactor, double strutRadiusMm) =>
        Math.Clamp(nodeSmoothingFactor, 0.0, 1.0) * strutRadiusMm;
}
