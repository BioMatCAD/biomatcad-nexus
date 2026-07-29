// Exceção de calibração de porosidade -- deliberadamente SEM referência ao PicoGK, apenas ao
// resultado puro (GyroidMath.MonotonicCalibrationResult), para permanecer testável em isolamento
// (xunit real, sem runtime nativo) mesmo estando ligada ao fluxo de geração real em
// GyroidScaffoldBuilder.cs (arquivo PicoGK-dependente que lança esta exceção).
namespace BioMatCadGeometryWorker;

/// <summary>Lançada quando target_porosity_pct foi solicitado e a calibração fechada contra a
/// malha real do PicoGK não converge dentro da tolerância medida após o número máximo de
/// iterações -- nunca finge sucesso científico. Capturada por Program.cs e mapeada para o
/// error_code estruturado POROSITY_TARGET_NOT_REACHED.
///
/// Correção pós-execução real (Incremento 2.1.1): a auditoria do usuário no Windows com as três
/// golden recipes revelou que a calibração puramente analítica (que só mede contra uma
/// estimativa contínua, nunca contra a malha efetivamente voxelizada) declarava
/// "porosity_calibration_converged=true" mesmo quando a malha real divergia MUITO do alvo -- em
/// modo preview, alvo 60% / medido no STL 78,804521% (erro real +18,804521 p.p.), quando a
/// estimativa analítica sozinha indicava 59,402332% (aparentemente dentro da tolerância). O bloco
/// e o cilindro em modo final tiveram erro real menor (-1,330121 p.p. e -2,243137 p.p.,
/// respectivamente), mas o problema de fundo -- nunca conferir contra a malha real -- era o mesmo
/// nos três casos, só não tinha sido grande o bastante para ficar óbvio.</summary>
public sealed class PorosityTargetNotReachedException : Exception
{
    public GyroidMath.MonotonicCalibrationResult CalibrationResult { get; }

    public PorosityTargetNotReachedException(GyroidMath.MonotonicCalibrationResult calibrationResult)
        : base(
            $"Porosidade medida na malha real ({calibrationResult.MeasuredPorosityPct:F6}%) não atingiu a " +
            $"tolerância de {calibrationResult.ToleranceUsedPctPoints:F2} pontos percentuais em torno do alvo " +
            $"após {calibrationResult.Iterations} iteração(ões) de calibração contra a malha real. " +
            $"Erro residual medido: {calibrationResult.ResidualErrorPctPoints:F6} p.p.")
    {
        CalibrationResult = calibrationResult;
    }
}
