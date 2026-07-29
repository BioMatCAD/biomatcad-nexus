// Núcleo matemático do scaffold Gyroid -- Incremento 2.1.1 (item 2).
// TOTALMENTE INDEPENDENTE do PicoGK: nenhuma referência a PicoGK.Library/Voxels/Mesh neste
// arquivo. É por isso testável de verdade (xunit real, sem runtime nativo) mesmo com o PicoGK
// bloqueado no sandbox Linux -- ver apps/geometry-worker/tests/.
//
// Fórmula da superfície mínima periódica (TPMS) de Alan Schoen (1970), domínio público:
//   F(x,y,z) = sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)
//
// Formulações de distância assinada para bloco e cilindro usam a técnica padrão de "campos de
// distância" (max/min de componentes) amplamente descrita em literatura de modelagem implícita
// (ex.: Inigo Quilez, "distance functions", técnica pública, não proprietária) -- EXATAS para
// bloco e cilindro (primitivas convexas simples). A distância da superfície gyroid em si NÃO tem
// forma fechada conhecida -- o valor usado é uma APROXIMAÇÃO documentada (ver
// SignedBandDistanceMmApprox), nunca chamada de "distância euclidiana exata".
namespace BioMatCadGeometryWorker;

public static class GyroidMath
{
    /// <summary>F(x,y,z) = sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x), em coordenadas de campo
    /// (radianos), já com a fase de semente aplicada. xMm/yMm/zMm são coordenadas reais em mm;
    /// cellSizeMm converte mm -> radianos (2π por célula unitária).</summary>
    public static double EvaluateGyroidField(double xMm, double yMm, double zMm, double cellSizeMm, double phaseShiftRad)
    {
        double scale = 2.0 * Math.PI / cellSizeMm;
        double x = xMm * scale + phaseShiftRad;
        double y = yMm * scale + phaseShiftRad;
        double z = zMm * scale + phaseShiftRad;
        return Math.Sin(x) * Math.Cos(y) + Math.Sin(y) * Math.Cos(z) + Math.Sin(z) * Math.Cos(x);
    }

    /// <summary>Transformação determinística e documentada de seed -> deslocamento de fase em
    /// radianos, no intervalo [0, 2π). Mesma seed sempre produz o mesmo deslocamento (requisito
    /// de determinismo, item 2). Não é criptográfico nem pretende ser: é apenas uma função
    /// injetiva o suficiente para separar visivelmente seeds diferentes (seeds adjacentes já
    /// produzem fases visivelmente diferentes por causa do fator de escala grande).</summary>
    public static double SeedToPhaseShiftRad(long seed)
    {
        const ulong modulus = 4294967296UL; // 2^32, mesmo intervalo do campo seed do schema
        ulong u = unchecked((ulong)seed) % modulus;
        // Multiplicador ímpar arbitrário (não é gerador criptográfico) apenas para espalhar
        // seeds próximas ao longo de [0, 2π) em vez de deslocamentos lineares diminutos.
        ulong scrambled = unchecked(u * 2654435761UL) % modulus;
        return (scrambled / (double)modulus) * 2.0 * Math.PI;
    }

    /// <summary>Distância assinada exata a uma caixa alinhada aos eixos, centrada na origem,
    /// com meia-extensão (halfX, halfY, halfZ). Negativo dentro, positivo fora, zero na
    /// superfície -- convenção padrão de SDF.</summary>
    public static double BoxSignedDistanceMm(double xMm, double yMm, double zMm, double halfX, double halfY, double halfZ)
    {
        double qx = Math.Abs(xMm) - halfX;
        double qy = Math.Abs(yMm) - halfY;
        double qz = Math.Abs(zMm) - halfZ;
        double outsideX = Math.Max(qx, 0);
        double outsideY = Math.Max(qy, 0);
        double outsideZ = Math.Max(qz, 0);
        double outsideDist = Math.Sqrt(outsideX * outsideX + outsideY * outsideY + outsideZ * outsideZ);
        double insideDist = Math.Min(Math.Max(qx, Math.Max(qy, qz)), 0.0);
        return outsideDist + insideDist;
    }

    /// <summary>Distância assinada a um cilindro sólido finito, eixo Z, base em z=0, topo em
    /// z=heightMm. Exata na região puramente radial e na região puramente das tampas; próxima da
    /// aresta de encontro entre parede lateral e tampa, é uma aproximação da distância real
    /// (comportamento padrão desta formulação -- ver comentário do BoxSignedDistanceMm). O
    /// importante para a voxelização é a classificação correta de dentro/fora, que é exata em
    /// toda a extensão do domínio.</summary>
    public static double CappedCylinderSignedDistanceMm(double xMm, double yMm, double zMm, double radiusMm, double heightMm)
    {
        double dr = Math.Sqrt(xMm * xMm + yMm * yMm) - radiusMm;
        double dz = Math.Max(-zMm, zMm - heightMm);
        double outsideDr = Math.Max(dr, 0);
        double outsideDz = Math.Max(dz, 0);
        double outsideDist = Math.Sqrt(outsideDr * outsideDr + outsideDz * outsideDz);
        double insideDist = Math.Min(Math.Max(dr, dz), 0.0);
        return outsideDist + insideDist;
    }

    /// <summary>Interseção booleana implícita de dois campos de distância assinada por max() --
    /// técnica padrão de CSG implícito (interseção de dois sólidos {f&lt;=0} é {max(fA,fB)&lt;=0}).
    /// Usada para recortar o gyroid pelo volume real do domínio (bloco ou cilindro), em vez de
    /// apenas pela bounding box.</summary>
    public static double IntersectSignedDistance(double fieldA, double fieldB) => Math.Max(fieldA, fieldB);

    /// <summary>Converte wall_thickness_mm em meia-largura de banda no espaço de campo
    /// (adimensional). Aproximação documentada: usa a magnitude média do gradiente de F em
    /// coordenadas normalizadas, estimada analiticamente como sqrt(2)*escala (escala = 2π/cell).
    /// Este é o único ponto de conversão espessura-mm -> banda-isovalor do sistema -- não há
    /// fórmula de distância euclidiana exata para o gyroid (não tem forma fechada conhecida).</summary>
    public static double WallThicknessMmToHalfBandWidth(double wallThicknessMm, double cellSizeMm)
    {
        double scale = 2.0 * Math.PI / cellSizeMm;
        double avgGradMagnitude = Math.Sqrt(2.0) * scale;
        return (wallThicknessMm / 2.0) * avgGradMagnitude;
    }

    /// <summary>Inversa de WallThicknessMmToHalfBandWidth -- usada para reportar, a partir de uma
    /// meia-largura de banda calibrada, qual seria a espessura em mm "efetiva" equivalente.</summary>
    public static double HalfBandWidthToWallThicknessMm(double halfBandWidth, double cellSizeMm)
    {
        double scale = 2.0 * Math.PI / cellSizeMm;
        double avgGradMagnitude = Math.Sqrt(2.0) * scale;
        if (avgGradMagnitude <= 0) return 0;
        return (halfBandWidth / avgGradMagnitude) * 2.0;
    }

    /// <summary>Distância assinada aproximada da banda gyroid [isovalue-halfBand, isovalue+halfBand]
    /// convertida de volta para uma escala em mm (mesma conversão aproximada de sempre, ver
    /// GyroidImplicit original do Incremento 2.1). Negativo dentro da banda (parede sólida),
    /// positivo fora.</summary>
    public static double SignedBandDistanceMmApprox(double fieldValue, double isovalueCenter, double halfBandWidth, double cellSizeMm)
    {
        double distanceFromCenterInField = Math.Abs(fieldValue - isovalueCenter) - halfBandWidth;
        return distanceFromCenterInField * (cellSizeMm / (2.0 * Math.PI));
    }

    /// <summary>Estima a fração de volume sólido (fase dentro da banda) por amostragem em grade
    /// regular sobre um período completo [0,2π)^3 do campo gyroid -- PURAMENTE ANALÍTICO, não usa
    /// PicoGK/voxels. Determinístico (grade fixa, sem aleatoriedade), portanto reproduzível. A
    /// resolução da grade (samplesPerAxis) é um parâmetro documentado de precisão vs. custo.</summary>
    public static double EstimateSolidFractionForBand(double halfBandWidth, double isovalueCenter, double phaseShiftRad, int samplesPerAxis = 28)
    {
        if (samplesPerAxis < 2) throw new ArgumentOutOfRangeException(nameof(samplesPerAxis));
        long inside = 0;
        long total = 0;
        double step = (2.0 * Math.PI) / samplesPerAxis;
        for (int i = 0; i < samplesPerAxis; i++)
        {
            double x = i * step + phaseShiftRad;
            for (int j = 0; j < samplesPerAxis; j++)
            {
                double y = j * step + phaseShiftRad;
                for (int k = 0; k < samplesPerAxis; k++)
                {
                    double z = k * step + phaseShiftRad;
                    double f = Math.Sin(x) * Math.Cos(y) + Math.Sin(y) * Math.Cos(z) + Math.Sin(z) * Math.Cos(x);
                    if (Math.Abs(f - isovalueCenter) <= halfBandWidth) inside++;
                    total++;
                }
            }
        }
        return total == 0 ? 0.0 : (double)inside / total;
    }

    public sealed class PorosityCalibrationResult
    {
        public double EffectiveHalfBandWidth { get; init; }
        public double EffectiveWallThicknessMm { get; init; }
        public double EstimatedPorosityPct { get; init; }
        public double ResidualErrorPct { get; init; }
        public int Iterations { get; init; }
        public bool Converged { get; init; }
    }

    /// <summary>Calibração determinística por bisseção da meia-largura de banda para atingir
    /// target_porosity_pct, usando EstimateSolidFractionForBand como oráculo analítico (sem
    /// PicoGK). Premissa documentada: porosidade é monotonicamente DECRESCENTE conforme a
    /// meia-largura de banda aumenta (mais banda sólida = menos poro) -- válida para a faixa de
    /// parâmetros aceita pelo schema. Retorna também o erro residual entre a porosidade estimada
    /// por esta calibração analítica e o alvo solicitado; ver GeometryMetricsCalculator para a
    /// porosidade REAL medida após a malha final ser gerada (valor de referência definitivo).</summary>
    public static PorosityCalibrationResult CalibratePorosityByBisection(
        double targetPorosityPct,
        double isovalueCenter,
        double phaseShiftRad,
        double cellSizeMm,
        double initialWallThicknessMm,
        double toleranceAbsPct = 0.75,
        int maxIterations = 22)
    {
        double lo = 1e-6;
        double hi = cellSizeMm / 2.0 - 1e-6;
        if (hi <= lo)
        {
            throw new InvalidOperationException("cell_size_mm demasiado pequeno para calibrar porosidade.");
        }

        double bestHalfBand = WallThicknessMmToHalfBandWidth(Math.Clamp(initialWallThicknessMm, lo, hi), cellSizeMm);
        double bestPorosityPct = 0;
        int iterations = 0;
        bool converged = false;

        double loHalfBand = WallThicknessMmToHalfBandWidth(lo, cellSizeMm);
        double hiHalfBand = WallThicknessMmToHalfBandWidth(hi, cellSizeMm);

        for (; iterations < maxIterations; iterations++)
        {
            bestHalfBand = (loHalfBand + hiHalfBand) / 2.0;
            double solidFraction = EstimateSolidFractionForBand(bestHalfBand, isovalueCenter, phaseShiftRad);
            bestPorosityPct = (1.0 - solidFraction) * 100.0;
            double error = bestPorosityPct - targetPorosityPct;
            if (Math.Abs(error) <= toleranceAbsPct)
            {
                converged = true;
                iterations++;
                break;
            }
            // Porosidade decresce com meia-largura de banda crescente (premissa documentada).
            if (bestPorosityPct > targetPorosityPct) loHalfBand = bestHalfBand; else hiHalfBand = bestHalfBand;
        }

        double effectiveWallThicknessMm = HalfBandWidthToWallThicknessMm(bestHalfBand, cellSizeMm);
        return new PorosityCalibrationResult
        {
            EffectiveHalfBandWidth = bestHalfBand,
            EffectiveWallThicknessMm = effectiveWallThicknessMm,
            EstimatedPorosityPct = bestPorosityPct,
            ResidualErrorPct = bestPorosityPct - targetPorosityPct,
            Iterations = iterations,
            Converged = converged,
        };
    }

    /// <summary>Resultado de uma calibração genérica por bisseção monotônica sobre uma
    /// grandeza medida por um oráculo injetado (ver CalibrateByMonotonicBisection). Usado tanto
    /// para a calibração analítica quanto para a calibração baseada em malha real do PicoGK
    /// (Incremento 2.1.1, correção pós-execução real: a auditoria do usuário no Windows revelou
    /// que a calibração puramente analítica diverge muito da porosidade real em modo preview
    /// -- alvo 60%, medido no STL 78,80%, erro real +18,80 p.p. -- porque a estimativa analítica
    /// nunca era conferida contra a malha efetivamente voxelizada/gerada).</summary>
    public sealed class MonotonicCalibrationResult
    {
        public double EffectiveWallThicknessMm { get; init; }
        public double MeasuredPorosityPct { get; init; }
        public double ResidualErrorPctPoints { get; init; }
        public double ToleranceUsedPctPoints { get; init; }
        public int Iterations { get; init; }
        public bool Converged { get; init; }
    }

    /// <summary>Tolerância padrão (pontos percentuais) para considerar a porosidade MEDIDA
    /// (contra a malha real, não a estimativa analítica) dentro do alvo. Modo `final` exige mais
    /// precisão (a malha é gerada na resolução solicitada); modo `preview` tolera mais erro
    /// (voxel size tem piso de 0.3mm -- GyroidMath.PreviewMinVoxelSizeMm -- então a malha
    /// discretizada diverge mais da estimativa contínua).</summary>
    public const double DefaultPorosityToleranceFinalPctPoints = 2.0;
    public const double DefaultPorosityTolerancePreviewPctPoints = 5.0;

    public static double DefaultPorosityTolerancePctPointsForMode(string mode) =>
        mode == "preview" ? DefaultPorosityTolerancePreviewPctPoints : DefaultPorosityToleranceFinalPctPoints;

    /// <summary>Número máximo de iterações da calibração baseada em malha REAL (cada uma gera
    /// Voxels+Mesh de verdade contra o PicoGK -- caro, ao contrário da calibração puramente
    /// analítica). 12 iterações de bisseção já reduzem o intervalo de busca em 2^12 = 4096x,
    /// muito além da precisão prática de wall_thickness_mm.</summary>
    public const int DefaultMeshCalibrationMaxIterations = 12;

    /// <summary>Calibração genérica por bisseção monotônica de wall_thickness_mm, dentro de
    /// limites físicos seguros [minWallThicknessMm, maxWallThicknessMm], usando
    /// measurePorosityForThickness como oráculo de MEDIÇÃO -- injetado propositalmente para que
    /// este método permaneça testável sem PicoGK (oráculo sintético nos testes) e, em produção,
    /// o oráculo real gere Voxels/Mesh de verdade contra o PicoGK e meça o volume da malha
    /// resultante (ver GyroidScaffoldBuilder.BuildAndExport). Premissa documentada: porosidade
    /// medida é monotonicamente DECRESCENTE conforme wall_thickness_mm cresce (mais parede
    /// sólida = menos poro) -- válida para a faixa de parâmetros aceita pelo schema.
    ///
    /// NUNCA declara Converged=true fora da tolerância efetivamente medida por
    /// measurePorosityForThickness -- ao contrário da calibração puramente analítica
    /// (CalibratePorosityByBisection), que só mede contra uma estimativa contínua e pode
    /// convergir "no papel" enquanto a malha real discretizada diverge muito do alvo (bug real
    /// encontrado nesta sessão em modo preview).</summary>
    public static MonotonicCalibrationResult CalibrateByMonotonicBisection(
        double targetPorosityPct,
        double initialWallThicknessMm,
        double minWallThicknessMm,
        double maxWallThicknessMm,
        double toleranceAbsPctPoints,
        int maxIterations,
        Func<double, double> measurePorosityForThickness)
    {
        if (maxWallThicknessMm <= minWallThicknessMm)
            throw new ArgumentException("maxWallThicknessMm deve ser maior que minWallThicknessMm.", nameof(maxWallThicknessMm));
        if (maxIterations < 1)
            throw new ArgumentOutOfRangeException(nameof(maxIterations), "maxIterations deve ser >= 1.");
        if (toleranceAbsPctPoints < 0)
            throw new ArgumentOutOfRangeException(nameof(toleranceAbsPctPoints), "toleranceAbsPctPoints deve ser >= 0.");

        double lo = minWallThicknessMm;
        double hi = maxWallThicknessMm;
        double bestThickness = Math.Clamp(initialWallThicknessMm, lo, hi);
        double bestPorosityPct = 0.0;
        int iterations = 0;
        bool converged = false;

        for (; iterations < maxIterations; iterations++)
        {
            bestPorosityPct = measurePorosityForThickness(bestThickness);
            double error = bestPorosityPct - targetPorosityPct;
            if (Math.Abs(error) <= toleranceAbsPctPoints)
            {
                converged = true;
                iterations++;
                break;
            }
            // Porosidade decresce com espessura crescente (premissa documentada acima).
            if (bestPorosityPct > targetPorosityPct) lo = bestThickness; else hi = bestThickness;
            bestThickness = (lo + hi) / 2.0;
        }

        return new MonotonicCalibrationResult
        {
            EffectiveWallThicknessMm = bestThickness,
            MeasuredPorosityPct = bestPorosityPct,
            ResidualErrorPctPoints = bestPorosityPct - targetPorosityPct,
            ToleranceUsedPctPoints = toleranceAbsPctPoints,
            Iterations = iterations,
            Converged = converged,
        };
    }

    /// <summary>Diferença real preview vs. final (item 2): em modo preview, o voxel size
    /// EFETIVO nunca é mais fino que um piso documentado, mesmo que a receita peça algo mais
    /// fino -- garante iteração rápida real, não apenas rótulo. Em modo final, o voxel size
    /// solicitado é respeitado integralmente (sujeito aos limites de compute_limits, verificados
    /// separadamente).</summary>
    public const double PreviewMinVoxelSizeMm = 0.3;

    public static double EffectiveVoxelSizeMm(double requestedVoxelSizeMm, string mode)
    {
        if (mode == "preview") return Math.Max(requestedVoxelSizeMm, PreviewMinVoxelSizeMm);
        return requestedVoxelSizeMm;
    }

    /// <summary>Estimativa PRÉVIA (antes de qualquer alocação real) do número de voxels que a
    /// bounding box do domínio ocuparia no voxel size efetivo -- estimativa de LIMITE SUPERIOR
    /// (assume grade densa), não o número real que o PicoGK (grade esparsa, baseada em OpenVDB)
    /// viria a alocar. Usada apenas para rejeitar receitas antes da execução (item 3).</summary>
    public static long EstimateVoxelCount(RecipeDomain domain, double effectiveVoxelSizeMm)
    {
        if (effectiveVoxelSizeMm <= 0) throw new ArgumentOutOfRangeException(nameof(effectiveVoxelSizeMm));
        double dimX, dimY, dimZ;
        var d = domain.DimensionsMm;
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
        double nx = Math.Ceiling(dimX / effectiveVoxelSizeMm);
        double ny = Math.Ceiling(dimY / effectiveVoxelSizeMm);
        double nz = Math.Ceiling(dimZ / effectiveVoxelSizeMm);
        double total = nx * ny * nz;
        if (total > long.MaxValue) return long.MaxValue;
        return (long)total;
    }

    /// <summary>Estimativa PRÉVIA e CONSERVADORA (limite superior de grade densa: 4 bytes/voxel,
    /// como se fosse um grid float32 denso) de memória em MB. O PicoGK/OpenVDB usa estrutura
    /// esparsa e tipicamente consome muito menos que isto para geometrias porosas -- este número
    /// NUNCA é apresentado como "limite físico garantido", apenas como estimativa preventiva
    /// (item 3: "não declare hard memory limit se houver apenas estimativa preventiva").</summary>
    public const double ConservativeBytesPerVoxelDenseGrid = 4.0;

    public static double EstimateMemoryMbUpperBound(long voxelCount)
    {
        double bytes = voxelCount * ConservativeBytesPerVoxelDenseGrid;
        return bytes / (1024.0 * 1024.0);
    }
}
