using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class GyroidMathTests
{
    [Fact]
    public void EvaluateGyroidField_AtOrigin_WithNoPhaseShift_IsZero()
    {
        // sin(0)cos(0) + sin(0)cos(0) + sin(0)cos(0) = 0
        double f = GyroidMath.EvaluateGyroidField(0, 0, 0, cellSizeMm: 2.0, phaseShiftRad: 0.0);
        Assert.Equal(0.0, f, 10);
    }

    [Fact]
    public void EvaluateGyroidField_IsPeriodicOverOneCell()
    {
        double cell = 2.0;
        double f1 = GyroidMath.EvaluateGyroidField(0.3, 0.7, 1.1, cell, 0.0);
        double f2 = GyroidMath.EvaluateGyroidField(0.3 + cell, 0.7, 1.1, cell, 0.0);
        Assert.Equal(f1, f2, 9);
    }

    [Fact]
    public void SeedToPhaseShiftRad_IsDeterministic_SameSeedSameShift()
    {
        double a = GyroidMath.SeedToPhaseShiftRad(42);
        double b = GyroidMath.SeedToPhaseShiftRad(42);
        Assert.Equal(a, b, 12);
    }

    [Fact]
    public void SeedToPhaseShiftRad_DifferentSeeds_ProduceDifferentShifts()
    {
        double a = GyroidMath.SeedToPhaseShiftRad(42);
        double b = GyroidMath.SeedToPhaseShiftRad(7);
        Assert.NotEqual(a, b);
    }

    [Fact]
    public void SeedToPhaseShiftRad_IsWithinZeroToTwoPi()
    {
        foreach (long seed in new long[] { 0, 1, 7, 42, 1000, 4294967295 })
        {
            double shift = GyroidMath.SeedToPhaseShiftRad(seed);
            Assert.InRange(shift, 0.0, 2.0 * Math.PI);
        }
    }

    [Fact]
    public void BoxSignedDistance_AtCenter_IsNegativeHalfOfSmallestExtent()
    {
        // Caixa 2x4x6 (meia-extensão 1,2,3): centro está a distância -1 da face mais próxima (x).
        double d = GyroidMath.BoxSignedDistanceMm(0, 0, 0, 1, 2, 3);
        Assert.Equal(-1.0, d, 9);
    }

    [Fact]
    public void BoxSignedDistance_OutsideOnAxis_IsPositiveExactDistance()
    {
        double d = GyroidMath.BoxSignedDistanceMm(5, 0, 0, 1, 2, 3);
        Assert.Equal(4.0, d, 9); // 5 - 1 (meia-extensão em x)
    }

    [Fact]
    public void BoxSignedDistance_OnSurface_IsZero()
    {
        double d = GyroidMath.BoxSignedDistanceMm(1, 0, 0, 1, 2, 3);
        Assert.Equal(0.0, d, 9);
    }

    [Fact]
    public void CappedCylinder_AtCenterOfAxis_IsNegative()
    {
        // Cilindro raio=5, altura=10 -- ponto (0,0,5) é o centro do eixo.
        double d = GyroidMath.CappedCylinderSignedDistanceMm(0, 0, 5, radiusMm: 5, heightMm: 10);
        Assert.Equal(-5.0, d, 9);
    }

    [Fact]
    public void CappedCylinder_OutsideRadially_IsPositive()
    {
        double d = GyroidMath.CappedCylinderSignedDistanceMm(8, 0, 5, radiusMm: 5, heightMm: 10);
        Assert.Equal(3.0, d, 9); // 8 - 5
    }

    [Fact]
    public void CappedCylinder_BeyondTopCap_IsPositive()
    {
        double d = GyroidMath.CappedCylinderSignedDistanceMm(0, 0, 15, radiusMm: 5, heightMm: 10);
        Assert.Equal(5.0, d, 9); // 15 - 10
    }

    [Fact]
    public void CappedCylinder_BelowBottomCap_IsPositive()
    {
        double d = GyroidMath.CappedCylinderSignedDistanceMm(0, 0, -3, radiusMm: 5, heightMm: 10);
        Assert.Equal(3.0, d, 9); // -(-3) = 3
    }

    [Fact]
    public void CappedCylinder_PointsWithinRadiusAndHeight_AreAllNegativeOrZero()
    {
        // Contenção real (item 2: "garantir mesma receita... contenção de todos os vértices
        // dentro do cilindro"): amostra pontos dentro do raio e altura nominal e confirma que
        // nenhum é classificado como fora (positivo).
        var rnd = new Random(1234);
        for (int i = 0; i < 500; i++)
        {
            double angle = rnd.NextDouble() * 2 * Math.PI;
            double r = rnd.NextDouble() * 4.99; // estritamente dentro do raio 5
            double x = r * Math.Cos(angle);
            double y = r * Math.Sin(angle);
            double z = rnd.NextDouble() * 10.0; // dentro de [0, altura]
            double d = GyroidMath.CappedCylinderSignedDistanceMm(x, y, z, radiusMm: 5, heightMm: 10);
            Assert.True(d <= 1e-9, $"Ponto ({x},{y},{z}) deveria estar dentro do cilindro (d={d}).");
        }
    }

    [Fact]
    public void IntersectSignedDistance_IsMaxOfBothFields()
    {
        Assert.Equal(3.0, GyroidMath.IntersectSignedDistance(3.0, -1.0));
        Assert.Equal(2.0, GyroidMath.IntersectSignedDistance(-5.0, 2.0));
    }

    [Fact]
    public void WallThicknessToHalfBandWidth_RoundTripsThroughInverse()
    {
        double halfBand = GyroidMath.WallThicknessMmToHalfBandWidth(0.5, cellSizeMm: 2.0);
        double backToMm = GyroidMath.HalfBandWidthToWallThicknessMm(halfBand, cellSizeMm: 2.0);
        Assert.Equal(0.5, backToMm, 9);
    }

    [Fact]
    public void WallThicknessToHalfBandWidth_IsMonotonicallyIncreasing()
    {
        double d1 = GyroidMath.WallThicknessMmToHalfBandWidth(0.2, 2.0);
        double d2 = GyroidMath.WallThicknessMmToHalfBandWidth(0.6, 2.0);
        Assert.True(d2 > d1);
    }

    [Fact]
    public void EstimateSolidFractionForBand_ZeroBandWidth_IsApproximatelyZero()
    {
        // Banda de largura ~0 só captura a superfície de medida nula -- fração sólida deve ser
        // muito próxima de 0 (não exatamente 0 por causa da grade discreta finita).
        double fraction = GyroidMath.EstimateSolidFractionForBand(halfBandWidth: 1e-6, isovalueCenter: 0.0, phaseShiftRad: 0.0, samplesPerAxis: 24);
        Assert.True(fraction < 0.02, $"Fração sólida deveria ser ~0 para banda infinitesimal, obtido {fraction}.");
    }

    [Fact]
    public void EstimateSolidFractionForBand_FullRange_IsOne()
    {
        // Banda cobrindo toda a amplitude possível do campo (|F| <= 3) captura o volume inteiro.
        double fraction = GyroidMath.EstimateSolidFractionForBand(halfBandWidth: 3.0, isovalueCenter: 0.0, phaseShiftRad: 0.0, samplesPerAxis: 16);
        Assert.Equal(1.0, fraction, 6);
    }

    [Fact]
    public void EstimateSolidFractionForBand_IsMonotonicallyIncreasingWithBandWidth()
    {
        double f1 = GyroidMath.EstimateSolidFractionForBand(0.2, 0.0, 0.0, samplesPerAxis: 24);
        double f2 = GyroidMath.EstimateSolidFractionForBand(0.5, 0.0, 0.0, samplesPerAxis: 24);
        double f3 = GyroidMath.EstimateSolidFractionForBand(1.0, 0.0, 0.0, samplesPerAxis: 24);
        Assert.True(f2 > f1);
        Assert.True(f3 > f2);
    }

    [Fact]
    public void EstimateSolidFractionForBand_IsDeterministic()
    {
        double a = GyroidMath.EstimateSolidFractionForBand(0.4, 0.0, 1.23, samplesPerAxis: 20);
        double b = GyroidMath.EstimateSolidFractionForBand(0.4, 0.0, 1.23, samplesPerAxis: 20);
        Assert.Equal(a, b);
    }

    [Fact]
    public void CalibratePorosityByBisection_ConvergesNearTarget()
    {
        var result = GyroidMath.CalibratePorosityByBisection(
            targetPorosityPct: 60.0,
            isovalueCenter: 0.0,
            phaseShiftRad: 0.0,
            cellSizeMm: 2.0,
            initialWallThicknessMm: 0.5);

        Assert.True(result.Converged, $"Deveria convergir; porosidade final={result.EstimatedPorosityPct}, erro={result.ResidualErrorPct}");
        Assert.True(Math.Abs(result.ResidualErrorPct) <= 1.0, $"Erro residual muito alto: {result.ResidualErrorPct}");
        Assert.True(result.EffectiveWallThicknessMm > 0);
    }

    [Fact]
    public void CalibratePorosityByBisection_HigherTargetPorosity_YieldsThinnerWall()
    {
        var lowPorosity = GyroidMath.CalibratePorosityByBisection(40.0, 0.0, 0.0, 2.0, 0.5);
        var highPorosity = GyroidMath.CalibratePorosityByBisection(80.0, 0.0, 0.0, 2.0, 0.5);
        Assert.True(highPorosity.EffectiveWallThicknessMm < lowPorosity.EffectiveWallThicknessMm);
    }

    [Fact]
    public void EffectiveVoxelSizeMm_Preview_NeverFinerThanFloor()
    {
        Assert.Equal(GyroidMath.PreviewMinVoxelSizeMm, GyroidMath.EffectiveVoxelSizeMm(0.05, "preview"));
        Assert.Equal(0.5, GyroidMath.EffectiveVoxelSizeMm(0.5, "preview"));
    }

    [Fact]
    public void EffectiveVoxelSizeMm_Final_RespectsRequestedValueExactly()
    {
        Assert.Equal(0.05, GyroidMath.EffectiveVoxelSizeMm(0.05, "final"));
    }

    [Fact]
    public void EstimateVoxelCount_Block_MatchesManualComputation()
    {
        var domain = new RecipeDomain { Shape = "block", DimensionsMm = new RecipeDimensions { Kind = "block", XMm = 10, YMm = 10, ZMm = 10 } };
        long count = GyroidMath.EstimateVoxelCount(domain, effectiveVoxelSizeMm: 1.0);
        Assert.Equal(1000L, count); // 10*10*10
    }

    [Fact]
    public void EstimateVoxelCount_Cylinder_UsesBoundingBoxOfDiameter()
    {
        var domain = new RecipeDomain { Shape = "cylinder", DimensionsMm = new RecipeDimensions { Kind = "cylinder", RadiusMm = 5, HeightMm = 10 } };
        long count = GyroidMath.EstimateVoxelCount(domain, effectiveVoxelSizeMm: 1.0);
        Assert.Equal(1000L, count); // diametro 10 x 10 x altura 10
    }

    [Fact]
    public void EstimateMemoryMbUpperBound_ScalesLinearlyWithVoxelCount()
    {
        double mb1 = GyroidMath.EstimateMemoryMbUpperBound(1_000_000);
        double mb2 = GyroidMath.EstimateMemoryMbUpperBound(2_000_000);
        Assert.Equal(mb2, mb1 * 2, 6);
    }
}
