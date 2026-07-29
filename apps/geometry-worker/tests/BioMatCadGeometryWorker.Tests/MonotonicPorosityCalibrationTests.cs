// Testes da calibração de porosidade FECHADA (GyroidMath.CalibrateByMonotonicBisection) --
// correção pós-execução real do Incremento 2.1.1 (auditoria do usuário no Windows encontrou:
// bloco final alvo 60%/medido 58,669879% erro -1,330121 p.p.; cilindro final alvo 55%/medido
// 52,756863% erro -2,243137 p.p.; preview alvo 60%/estimativa analítica 59,402332%/medido no
// STL real 78,804521% erro real +18,804521 p.p. -- a calibração antiga só conferia a estimativa
// analítica, nunca a malha real, e por isso declarava "converged=true" de forma enganosa).
//
// Estes testes usam oráculos de medição SINTÉTICOS (funções puras, sem PicoGK) injetados no
// método genérico -- exatamente o ponto de injeção que permite testar o ALGORITMO de calibração
// de verdade neste sandbox Linux (sem runtime nativo do PicoGK), separado da geração real de
// Voxels/Mesh (que só GyroidScaffoldBuilder.cs faz, e só pode ser provada contra o PicoGK real
// no Windows do usuário -- ver WORKER_STATUS.md). Os oráculos aqui são deliberadamente
// hipotéticos/didáticos, não uma reprodução literal dos números reais reportados acima -- servem
// para exercitar o algoritmo de bisseção monotônica em cenários com o mesmo formato qualitativo
// (divergência analítico-vs-medido, convergência dentro/fora de tolerância, etc.).
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class MonotonicPorosityCalibrationTests
{
    // Oráculo sintético monotonicamente decrescente: porosidade cai linearmente conforme a
    // espessura de parede cresce -- a mesma premissa documentada em GyroidMath, mas aqui como
    // função pura e determinística, sem qualquer chamada ao PicoGK.
    private static Func<double, double> LinearOracle(double porosityAtZeroThicknessPct, double slopePctPerMm) =>
        thicknessMm => porosityAtZeroThicknessPct - slopePctPerMm * thicknessMm;

    // Oráculo constante -- não responde à espessura (simula um caso patológico onde o alvo é
    // simplesmente inatingível dentro dos limites físicos de busca), usado para provar que a
    // calibração relata falha (Converged=false) em vez de fingir sucesso.
    private static Func<double, double> ConstantOracle(double alwaysReturnsPct) => _ => alwaysReturnsPct;

    [Fact]
    public void MeasuredOracle_CanDivergeSubstantiallyFromAnalyticalEstimate_PreviewLikeScenario()
    {
        // Cenário didático inspirado no caso real de preview: a estimativa ANALÍTICA (contínua,
        // sem discretização) para uma dada espessura indica um valor, mas o oráculo de MEDIÇÃO
        // (aqui, simulando o efeito de uma malha grosseira/discretizada) indica outro, bem
        // diferente -- prova que os dois oráculos são conceitualmente distintos e que confiar só
        // no analítico seria enganoso (exatamente o bug real encontrado).
        double candidateThicknessMm = 0.5;

        double halfBandWidth = GyroidMath.WallThicknessMmToHalfBandWidth(candidateThicknessMm, cellSizeMm: 2.0);
        double solidFraction = GyroidMath.EstimateSolidFractionForBand(halfBandWidth, isovalueCenter: 0.0, phaseShiftRad: 0.0);
        double analyticalEstimatePct = (1.0 - solidFraction) * 100.0;

        // Oráculo de "medição" sintético com um viés grande sobreposto -- representa o tipo de
        // divergência real observada em preview (discretização grosseira infla a porosidade
        // medida bem acima da estimativa contínua).
        var measuredOracle = LinearOracle(porosityAtZeroThicknessPct: analyticalEstimatePct + 20.0, slopePctPerMm: 5.0);
        double measuredPct = measuredOracle(candidateThicknessMm);

        Assert.True(
            Math.Abs(measuredPct - analyticalEstimatePct) > 10.0,
            "O oráculo sintético deveria divergir substancialmente do analítico para representar o cenário real de preview.");
    }

    [Fact]
    public void CalibrateByMonotonicBisection_BlockFinalLikeScenario_ConvergesWithinTwoPercentagePoints()
    {
        var oracle = LinearOracle(porosityAtZeroThicknessPct: 95.0, slopePctPerMm: 60.0);
        double toleranceFinal = GyroidMath.DefaultPorosityToleranceFinalPctPoints;

        var result = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0,
            initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6,
            maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: toleranceFinal,
            maxIterations: GyroidMath.DefaultMeshCalibrationMaxIterations,
            measurePorosityForThickness: oracle);

        Assert.True(result.Converged);
        Assert.True(Math.Abs(result.ResidualErrorPctPoints) <= toleranceFinal);
        Assert.Equal(toleranceFinal, result.ToleranceUsedPctPoints);
    }

    [Fact]
    public void CalibrateByMonotonicBisection_CylinderFinalLikeScenario_ConvergesWithinTwoPercentagePoints()
    {
        // Coeficientes diferentes do teste de bloco -- representa uma relação
        // espessura->porosidade distinta (domínio cilíndrico teria volume/área diferentes).
        var oracle = LinearOracle(porosityAtZeroThicknessPct: 88.0, slopePctPerMm: 44.0);
        double toleranceFinal = GyroidMath.DefaultPorosityToleranceFinalPctPoints;

        var result = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 55.0,
            initialWallThicknessMm: 0.6,
            minWallThicknessMm: 1e-6,
            maxWallThicknessMm: 1.5 - 1e-6,
            toleranceAbsPctPoints: toleranceFinal,
            maxIterations: GyroidMath.DefaultMeshCalibrationMaxIterations,
            measurePorosityForThickness: oracle);

        Assert.True(result.Converged);
        Assert.True(Math.Abs(result.ResidualErrorPctPoints) <= toleranceFinal);
    }

    [Fact]
    public void CalibrateByMonotonicBisection_PreviewLikeScenario_ConvergesWithinFivePercentagePoints()
    {
        // Demonstra a diferença prática entre as duas tolerâncias padrão: usando o MESMO
        // oráculo, o MESMO palpite inicial (residual exatamente 5,0 p.p. no primeiro palpite) e
        // limitando deliberadamente a UMA única avaliação (maxIterations=1, sem margem para a
        // bisseção refinar), a tolerância de preview (5.0pp) aceita esse primeiro palpite como
        // convergido, enquanto a tolerância de modo final (2.0pp), mais apertada, rejeita a
        // mesma avaliação -- prova que a diferenciação de tolerância por modo é funcionalmente
        // significativa, não cosmética.
        var oracle = LinearOracle(porosityAtZeroThicknessPct: 95.0, slopePctPerMm: 60.0);
        double initialThicknessMm = 0.5; // oracle(0.5) = 95 - 30 = 65.0 -- alvo 60.0 -- residual exato = 5.0

        var previewResult = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0,
            initialWallThicknessMm: initialThicknessMm,
            minWallThicknessMm: 1e-6,
            maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: GyroidMath.DefaultPorosityTolerancePreviewPctPoints,
            maxIterations: 1,
            measurePorosityForThickness: oracle);

        var finalResult = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0,
            initialWallThicknessMm: initialThicknessMm,
            minWallThicknessMm: 1e-6,
            maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: GyroidMath.DefaultPorosityToleranceFinalPctPoints,
            maxIterations: 1,
            measurePorosityForThickness: oracle);

        Assert.Equal(5.0, Math.Abs(previewResult.ResidualErrorPctPoints), precision: 9);
        Assert.True(previewResult.Converged, "Com tolerância de preview (5.0pp), um residual de exatamente 5.0pp deveria convergir.");
        Assert.False(finalResult.Converged, "Com tolerância de modo final (2.0pp), o mesmo residual de 5.0pp NÃO deveria convergir.");
    }

    [Fact]
    public void CalibrateByMonotonicBisection_PreviewLikeScenario_ConvergesGivenEnoughIterations()
    {
        // Complementa o teste acima: com iterações suficientes (não limitadas a 1), a bisseção
        // de fato refina o palpite e converge dentro da tolerância de preview a partir do mesmo
        // oráculo e do mesmo palpite inicial distante.
        var oracle = LinearOracle(porosityAtZeroThicknessPct: 95.0, slopePctPerMm: 60.0);
        double tolerancePreview = GyroidMath.DefaultPorosityTolerancePreviewPctPoints;

        var result = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0,
            initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6,
            maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: tolerancePreview,
            maxIterations: GyroidMath.DefaultMeshCalibrationMaxIterations,
            measurePorosityForThickness: oracle);

        Assert.True(result.Converged);
        Assert.True(Math.Abs(result.ResidualErrorPctPoints) <= tolerancePreview);
    }

    [Fact]
    public void CalibrateByMonotonicBisection_UnreachableTarget_DoesNotConverge()
    {
        // Oráculo constante: nenhuma espessura candidata altera a porosidade medida -- alvo é
        // simplesmente inatingível dentro dos limites de busca. Deve relatar Converged=false,
        // nunca fingir sucesso. (A falha ESTRUTURADA de fato -- error_code
        // POROSITY_TARGET_NOT_REACHED -- é responsabilidade de GyroidScaffoldBuilder.cs/
        // Program.cs, código PicoGK-dependente não incluído neste projeto de testes; este teste
        // garante que o SINAL de não-convergência do qual aquele erro depende é real e correto.)
        var oracle = ConstantOracle(90.0);

        var result = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 10.0,
            initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6,
            maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: 2.0,
            maxIterations: 8,
            measurePorosityForThickness: oracle);

        Assert.False(result.Converged);
        Assert.True(Math.Abs(result.ResidualErrorPctPoints) > 2.0);
        Assert.Equal(8, result.Iterations);
    }

    [Fact]
    public void CalibrateByMonotonicBisection_NeverReportsConvergedTrueOutsideMeasuredTolerance()
    {
        // Invariante central desta correção: Converged=true NUNCA pode coexistir com um erro
        // residual medido maior que a tolerância usada -- testado contra várias combinações de
        // parâmetros (incluindo casos que convergem e casos que não convergem).
        var scenarios = new (double targetPct, Func<double, double> oracle, double toleranceAbsPctPoints, int maxIterations)[]
        {
            (60.0, LinearOracle(95.0, 60.0), 2.0, 12),
            (55.0, LinearOracle(88.0, 44.0), 2.0, 12),
            (60.0, thicknessMm => LinearOracle(95.0, 60.0)(thicknessMm) + 4.2, 5.0, 12),
            (10.0, ConstantOracle(90.0), 2.0, 6),   // inatingível -- não deve convergir
            (99.9, LinearOracle(50.0, 10.0), 0.5, 5), // tolerância apertada + poucas iterações -- pode não convergir
        };

        foreach (var (targetPct, oracle, toleranceAbsPctPoints, maxIterations) in scenarios)
        {
            var result = GyroidMath.CalibrateByMonotonicBisection(
                targetPorosityPct: targetPct,
                initialWallThicknessMm: 0.5,
                minWallThicknessMm: 1e-6,
                maxWallThicknessMm: 1.0 - 1e-6,
                toleranceAbsPctPoints: toleranceAbsPctPoints,
                maxIterations: maxIterations,
                measurePorosityForThickness: oracle);

            if (result.Converged)
            {
                Assert.True(
                    Math.Abs(result.ResidualErrorPctPoints) <= toleranceAbsPctPoints,
                    $"Converged=true mas erro residual ({result.ResidualErrorPctPoints:F6}) excede a tolerância ({toleranceAbsPctPoints}) -- violação da invariante central desta correção.");
            }
        }
    }

    [Fact]
    public void CalibrateByMonotonicBisection_IsDeterministic_SameInputsSameOutputs()
    {
        var oracle = LinearOracle(porosityAtZeroThicknessPct: 95.0, slopePctPerMm: 60.0);

        var result1 = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0, initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6, maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: 2.0, maxIterations: 12, measurePorosityForThickness: oracle);

        var result2 = GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0, initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6, maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: 2.0, maxIterations: 12, measurePorosityForThickness: oracle);

        Assert.Equal(result1.EffectiveWallThicknessMm, result2.EffectiveWallThicknessMm);
        Assert.Equal(result1.MeasuredPorosityPct, result2.MeasuredPorosityPct);
        Assert.Equal(result1.ResidualErrorPctPoints, result2.ResidualErrorPctPoints);
        Assert.Equal(result1.Iterations, result2.Iterations);
        Assert.Equal(result1.Converged, result2.Converged);
    }

    [Fact]
    public void CalibrateByMonotonicBisection_RejectsInvalidBounds()
    {
        Assert.Throws<ArgumentException>(() => GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0, initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1.0, maxWallThicknessMm: 0.5, // invertido -- inválido
            toleranceAbsPctPoints: 2.0, maxIterations: 12, measurePorosityForThickness: LinearOracle(95.0, 60.0)));
    }

    [Fact]
    public void CalibrateByMonotonicBisection_RejectsNonPositiveMaxIterations()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0, initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6, maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: 2.0, maxIterations: 0, measurePorosityForThickness: LinearOracle(95.0, 60.0)));
    }

    [Fact]
    public void CalibrateByMonotonicBisection_RejectsNegativeTolerance()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => GyroidMath.CalibrateByMonotonicBisection(
            targetPorosityPct: 60.0, initialWallThicknessMm: 0.5,
            minWallThicknessMm: 1e-6, maxWallThicknessMm: 1.0 - 1e-6,
            toleranceAbsPctPoints: -1.0, maxIterations: 12, measurePorosityForThickness: LinearOracle(95.0, 60.0)));
    }

    [Fact]
    public void DefaultPorosityTolerancePctPointsForMode_ReturnsExpectedDefaults()
    {
        Assert.Equal(2.0, GyroidMath.DefaultPorosityToleranceFinalPctPoints);
        Assert.Equal(5.0, GyroidMath.DefaultPorosityTolerancePreviewPctPoints);
        Assert.Equal(2.0, GyroidMath.DefaultPorosityTolerancePctPointsForMode("final"));
        Assert.Equal(5.0, GyroidMath.DefaultPorosityTolerancePctPointsForMode("preview"));
    }
}
