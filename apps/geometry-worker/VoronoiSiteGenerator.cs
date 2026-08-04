// Geração determinística de sítios (sementes) para VoronoiTopologyProvider -- Incremento 2.2,
// rodada Voronoi, Seção 4 da instrução ("GERAÇÃO DOS SÍTIOS").
//
// TOTALMENTE INDEPENDENTE do PicoGK (nenhuma referência a PicoGK.Library/Voxels/Mesh neste
// arquivo) -- testável de verdade (xunit real, sem runtime nativo) mesmo com o PicoGK bloqueado
// no sandbox Linux, mesmo padrão já estabelecido por GyroidMath.cs.
//
// PRNG: SplitMix64 (Sebastiano Vigna, domínio público/CC0 -- ver
// https://prng.di.unimi.it/splitmix64.c e https://xoshiro.di.unimi.it/splitmix64.c). Escolhido
// em vez de System.Random porque o algoritmo exato de System.Random(int) não é uma garantia de
// API estável entre versões do .NET (a implementação interna já mudou entre major versions
// históricas do runtime) -- SplitMix64 é uma função pura, publicada e fixa, cujo resultado para
// uma dada seed nunca muda, independente da versão do .NET usada para compilar este worker.
// Não é um gerador criptográfico e não pretende ser: apenas uma função determinística e bem
// distribuída para amostragem espacial.
using System.Security.Cryptography;
using System.Text;

namespace BioMatCadGeometryWorker;

public enum VoronoiSiteDistribution
{
    UniformRandom,
    JitteredGrid,
}

/// <summary>Lançada quando não foi possível gerar site_count sítios respeitando a distância
/// mínima dentro do número máximo de tentativas -- nunca silenciosamente devolve menos sítios
/// do que o solicitado no modo uniform_random (ao contrário de jittered_grid, onde um número
/// efetivo menor é uma característica documentada e honestamente reportada, não uma falha).</summary>
public sealed class SiteGenerationException : Exception
{
    public int RequestedSiteCount { get; }
    public int AcceptedSiteCount { get; }
    public int RejectedAttempts { get; }

    public SiteGenerationException(int requestedSiteCount, int acceptedSiteCount, int rejectedAttempts)
        : base(
            $"Não foi possível gerar {requestedSiteCount} sítios respeitando a distância mínima " +
            $"configurada dentro do domínio -- apenas {acceptedSiteCount} aceitos após {rejectedAttempts} " +
            "tentativas rejeitadas (coincidência/violação de distância mínima). Reduza site_count ou " +
            "aumente o domínio.")
    {
        RequestedSiteCount = requestedSiteCount;
        AcceptedSiteCount = acceptedSiteCount;
        RejectedAttempts = rejectedAttempts;
    }
}

public static class VoronoiSiteGenerator
{
    /// <summary>SplitMix64 -- gerador pseudoaleatório determinístico e público (Vigna). Mesma
    /// seed produz sempre a mesma sequência, em qualquer plataforma/versão do .NET, porque é uma
    /// função aritmética pura definida por especificação, não uma API de biblioteca que possa
    /// mudar de implementação.</summary>
    public sealed class SplitMix64
    {
        private ulong _state;

        public SplitMix64(long seed)
        {
            _state = unchecked((ulong)seed);
        }

        public ulong NextUInt64()
        {
            _state += 0x9E3779B97F4A7C15UL;
            ulong z = _state;
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
            return z ^ (z >> 31);
        }

        /// <summary>Double uniforme em [0,1) -- técnica padrão (53 bits de mantissa de um
        /// ulong de 64 bits).</summary>
        public double NextDouble01() => (NextUInt64() >> 11) * (1.0 / (1UL << 53));

        /// <summary>Double uniforme em [min, max).</summary>
        public double NextDouble(double min, double max) => min + NextDouble01() * (max - min);
    }

    public sealed class SiteGenerationResult
    {
        /// <summary>Sítios em ordem CANÔNICA (ordenados por X, depois Y, depois Z) --
        /// independente da ordem em que foram efetivamente aceitos durante a amostragem, para
        /// que o checksum e qualquer consumidor posterior (tesselação) sejam determinísticos
        /// mesmo que a ordem de aceitação interna dependa de detalhes de implementação.</summary>
        public IReadOnlyList<Vec3> Sites { get; init; } = Array.Empty<Vec3>();
        public string SitesSha256 { get; init; } = "";
        public int RequestedSiteCount { get; init; }
        public int RejectedAttempts { get; init; }
        public double MinSeparationMmUsed { get; init; }
    }

    /// <summary>Distância mínima padrão entre sítios, DERIVADA do domínio e do número de sítios
    /// solicitado (não há campo dedicado no schema para isto -- ver Seção 3 da auditoria
    /// matemática). Heurística documentada: espaçamento médio esperado de um processo pontual
    /// aproximadamente uniforme é cbrt(volume/n); usamos uma fração conservadora deste valor
    /// (35%) como distância mínima "dura", grande o suficiente para evitar sítios efetivamente
    /// coincidentes/quase-coincidentes (que produziriam tetraedros de Delaunay degenerados),
    /// pequena o suficiente para não impedir a amostragem de convergir para a maioria das
    /// combinações razoáveis de site_count/domínio.</summary>
    public static double DeriveDefaultMinSeparationMm(double domainVolumeMm3, int siteCount)
    {
        if (siteCount <= 0 || domainVolumeMm3 <= 0) return 0.0;
        double meanSpacing = Math.Cbrt(domainVolumeMm3 / siteCount);
        return 0.35 * meanSpacing;
    }

    private static double DomainBoundingBoxVolumeMm3(RecipeDomain domain)
    {
        var d = domain.DimensionsMm;
        return domain.Shape switch
        {
            "block" => (d.XMm ?? 0) * (d.YMm ?? 0) * (d.ZMm ?? 0),
            // bounding box do cilindro (não o volume do próprio cilindro) -- usado apenas para
            // dimensionar a grade de jittered_grid, nunca para calibração de porosidade (que usa
            // GeometryMetricsCalculator.ComputeDomainVolumeMm3, o volume REAL do cilindro).
            "cylinder" => (2.0 * (d.RadiusMm ?? 0)) * (2.0 * (d.RadiusMm ?? 0)) * (d.HeightMm ?? 0),
            _ => throw new NotSupportedException($"Domínio não suportado: {domain.Shape}"),
        };
    }

    /// <summary>Testa se um ponto (já nas mesmas coordenadas centradas usadas pelo domínio
    /// implícito, ver GyroidDomainImplicit) está dentro do domínio -- reaproveita literalmente
    /// as mesmas SDFs de bloco/cilindro já testadas e aprovadas para Gyroid, para que a noção de
    /// "dentro do domínio" seja idêntica entre as duas topologias (nunca uma segunda definição
    /// divergente de contenção).</summary>
    public static bool IsInsideDomain(Vec3 p, RecipeDomain domain)
    {
        var d = domain.DimensionsMm;
        double signedDistance = domain.Shape switch
        {
            "block" => GyroidMath.BoxSignedDistanceMm(
                p.X, p.Y, p.Z, (d.XMm ?? 0) / 2.0, (d.YMm ?? 0) / 2.0, (d.ZMm ?? 0) / 2.0),
            "cylinder" => GyroidMath.CappedCylinderSignedDistanceMm(
                p.X, p.Y, p.Z + (d.HeightMm ?? 0) / 2.0, d.RadiusMm ?? 0, d.HeightMm ?? 0),
            _ => throw new NotSupportedException($"Domínio não suportado: {domain.Shape}"),
        };
        return signedDistance <= 0.0;
    }

    private static Vec3 SampleUniformInBoundingBox(SplitMix64 rng, RecipeDomain domain)
    {
        var d = domain.DimensionsMm;
        return domain.Shape switch
        {
            "block" => new Vec3(
                rng.NextDouble(-(d.XMm ?? 0) / 2.0, (d.XMm ?? 0) / 2.0),
                rng.NextDouble(-(d.YMm ?? 0) / 2.0, (d.YMm ?? 0) / 2.0),
                rng.NextDouble(-(d.ZMm ?? 0) / 2.0, (d.ZMm ?? 0) / 2.0)),
            "cylinder" => new Vec3(
                rng.NextDouble(-(d.RadiusMm ?? 0), d.RadiusMm ?? 0),
                rng.NextDouble(-(d.RadiusMm ?? 0), d.RadiusMm ?? 0),
                rng.NextDouble(-(d.HeightMm ?? 0) / 2.0, (d.HeightMm ?? 0) / 2.0)),
            _ => throw new NotSupportedException($"Domínio não suportado: {domain.Shape}"),
        };
    }

    private static List<Vec3> CanonicalOrder(IEnumerable<Vec3> sites) =>
        sites
            .OrderBy(s => s.X)
            .ThenBy(s => s.Y)
            .ThenBy(s => s.Z)
            .ToList();

    /// <summary>SHA-256 hexadecimal do conjunto de sítios, em ordem canônica, formato de texto
    /// fixo e determinístico ("R" round-trip -- garante que o mesmo double sempre produz a
    /// mesma string, em qualquer cultura/locale, já que "R" é invariante de cultura quando usado
    /// com CultureInfo.InvariantCulture explícito). Usado para auditoria/reprodutibilidade,
    /// mesmo princípio já usado para o checksum do STL (StlExporter.ComputeSha256Hex).</summary>
    public static string ComputeSitesSha256(IReadOnlyList<Vec3> canonicalOrderedSites)
    {
        var sb = new StringBuilder();
        foreach (var s in canonicalOrderedSites)
        {
            sb.Append(s.X.ToString("R", System.Globalization.CultureInfo.InvariantCulture));
            sb.Append(';');
            sb.Append(s.Y.ToString("R", System.Globalization.CultureInfo.InvariantCulture));
            sb.Append(';');
            sb.Append(s.Z.ToString("R", System.Globalization.CultureInfo.InvariantCulture));
            sb.Append('\n');
        }
        byte[] bytes = Encoding.UTF8.GetBytes(sb.ToString());
        byte[] hash = SHA256.HashData(bytes);
        return Convert.ToHexStringLower(hash);
    }

    /// <summary>Amostragem por rejeição: sítios uniformemente distribuídos dentro do domínio,
    /// respeitando distância mínima entre pares. Determinístico (mesma seed = mesmos sítios,
    /// mesma ordem de tentativas internas) -- a ordem de RETORNO é sempre canonicalizada
    /// (CanonicalOrder), então o resultado final não depende da ordem de aceitação interna,
    /// apenas do CONJUNTO de sítios aceitos, que por sua vez é determinístico pela seed.</summary>
    public static SiteGenerationResult GenerateUniformRandom(
        RecipeDomain domain, int siteCount, long seed, double? minSeparationMmOverride = null,
        int maxAttemptsPerSite = 500)
    {
        if (siteCount <= 0) throw new ArgumentOutOfRangeException(nameof(siteCount));
        double domainVolumeMm3 = GeometryMetricsCalculator.ComputeDomainVolumeMm3(domain);
        double minSeparationMm = minSeparationMmOverride
            ?? DeriveDefaultMinSeparationMm(domainVolumeMm3, siteCount);
        double minSeparationSqMm = minSeparationMm * minSeparationMm;

        var rng = new SplitMix64(seed);
        var accepted = new List<Vec3>(siteCount);
        int rejectedAttempts = 0;
        int maxTotalAttempts = siteCount * maxAttemptsPerSite;

        for (int attempt = 0; accepted.Count < siteCount && attempt < maxTotalAttempts; attempt++)
        {
            var candidate = SampleUniformInBoundingBox(rng, domain);
            if (!IsInsideDomain(candidate, domain))
            {
                rejectedAttempts++;
                continue;
            }
            bool tooClose = false;
            foreach (var existing in accepted)
            {
                double dx = candidate.X - existing.X, dy = candidate.Y - existing.Y, dz = candidate.Z - existing.Z;
                if (dx * dx + dy * dy + dz * dz < minSeparationSqMm)
                {
                    tooClose = true;
                    break;
                }
            }
            if (tooClose)
            {
                rejectedAttempts++;
                continue;
            }
            accepted.Add(candidate);
        }

        if (accepted.Count < siteCount)
        {
            throw new SiteGenerationException(siteCount, accepted.Count, rejectedAttempts);
        }

        var canonical = CanonicalOrder(accepted);
        return new SiteGenerationResult
        {
            Sites = canonical,
            SitesSha256 = ComputeSitesSha256(canonical),
            RequestedSiteCount = siteCount,
            RejectedAttempts = rejectedAttempts,
            MinSeparationMmUsed = minSeparationMm,
        };
    }

    /// <summary>Grade regular (dimensionada para aproximar site_count) com jitter determinístico
    /// por célula, filtrada pelo domínio real. Diferente de uniform_random: o número EFETIVO de
    /// sítios pode ser menor que site_count solicitado (células de grade cujo ponto jitterado cai
    /// fora do domínio real são descartadas, não substituídas) -- isto é uma característica
    /// documentada, não uma falha, e o número efetivo é sempre reportado com honestidade (nunca
    /// fabricado como se fosse exatamente o solicitado).</summary>
    public static SiteGenerationResult GenerateJitteredGrid(
        RecipeDomain domain, int siteCount, long seed, double jitterFractionOfCell = 0.4)
    {
        if (siteCount <= 0) throw new ArgumentOutOfRangeException(nameof(siteCount));
        var d = domain.DimensionsMm;
        double dimX, dimY, dimZ;
        switch (domain.Shape)
        {
            case "block":
                dimX = d.XMm ?? 0; dimY = d.YMm ?? 0; dimZ = d.ZMm ?? 0;
                break;
            case "cylinder":
                double diameter = 2.0 * (d.RadiusMm ?? 0);
                dimX = diameter; dimY = diameter; dimZ = d.HeightMm ?? 0;
                break;
            default:
                throw new NotSupportedException($"Domínio não suportado: {domain.Shape}");
        }

        double boundingVolume = dimX * dimY * dimZ;
        double cellSize = Math.Cbrt(boundingVolume / siteCount);
        int nx = Math.Max(1, (int)Math.Round(dimX / cellSize));
        int ny = Math.Max(1, (int)Math.Round(dimY / cellSize));
        int nz = Math.Max(1, (int)Math.Round(dimZ / cellSize));

        double halfX = dimX / 2.0, halfY = dimY / 2.0, halfZ = dimZ / 2.0;
        double cellX = dimX / nx, cellY = dimY / ny, cellZ = dimZ / nz;

        var rng = new SplitMix64(seed);
        var accepted = new List<Vec3>();
        int rejectedAttempts = 0;

        for (int i = 0; i < nx; i++)
        {
            double cx = -halfX + (i + 0.5) * cellX;
            for (int j = 0; j < ny; j++)
            {
                double cy = -halfY + (j + 0.5) * cellY;
                for (int k = 0; k < nz; k++)
                {
                    double cz = -halfZ + (k + 0.5) * cellZ;
                    double jx = rng.NextDouble(-jitterFractionOfCell, jitterFractionOfCell) * cellX;
                    double jy = rng.NextDouble(-jitterFractionOfCell, jitterFractionOfCell) * cellY;
                    double jz = rng.NextDouble(-jitterFractionOfCell, jitterFractionOfCell) * cellZ;
                    var candidate = new Vec3(cx + jx, cy + jy, cz + jz);
                    if (IsInsideDomain(candidate, domain))
                    {
                        accepted.Add(candidate);
                    }
                    else
                    {
                        rejectedAttempts++;
                    }
                }
            }
        }

        // Se a grade produziu mais pontos que o solicitado, trunca em ordem canônica (nunca
        // trunca em ordem de geração, que dependeria de detalhe de implementação do laço acima).
        var canonicalAll = CanonicalOrder(accepted);
        var final = canonicalAll.Count > siteCount ? canonicalAll.Take(siteCount).ToList() : canonicalAll;

        return new SiteGenerationResult
        {
            Sites = final,
            SitesSha256 = ComputeSitesSha256(final),
            RequestedSiteCount = siteCount,
            RejectedAttempts = rejectedAttempts,
            MinSeparationMmUsed = 0.0, // jittered_grid não aplica uma distância mínima explícita -- a própria grade já espaça os sítios
        };
    }

    public static SiteGenerationResult Generate(
        RecipeDomain domain, int siteCount, VoronoiSiteDistribution distribution, long seed,
        double? minSeparationMmOverride = null) => distribution switch
    {
        VoronoiSiteDistribution.UniformRandom => GenerateUniformRandom(domain, siteCount, seed, minSeparationMmOverride),
        VoronoiSiteDistribution.JitteredGrid => GenerateJitteredGrid(domain, siteCount, seed),
        _ => throw new NotSupportedException($"Distribuição de sítios não suportada: {distribution}"),
    };
}
