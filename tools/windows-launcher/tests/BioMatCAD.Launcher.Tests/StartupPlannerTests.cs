using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class StartupPlannerTests
{
    [Fact]
    public void PlanService_ComPortaJaOcupada_DecideReaproveitarSemIniciarNovoProcesso()
    {
        // "API/frontend já ativos": prova a decisão pura, sem precisar realmente ter uma API
        // ou frontend reais rodando -- só o dado "porta já ocupada".
        var plan = StartupPlanner.PlanService(new ServicePlanInput("API", 8000, PortAlreadyInUse: true));

        Assert.Equal(ServiceAction.ReuseExisting, plan.Action);
        Assert.Contains("já está em uso", plan.Message);
        Assert.Contains("NÃO", plan.Message);
    }

    [Fact]
    public void PlanService_ComPortaLivre_DecideIniciarNovoProcesso()
    {
        var plan = StartupPlanner.PlanService(new ServicePlanInput("Frontend", 5173, PortAlreadyInUse: false));

        Assert.Equal(ServiceAction.StartNew, plan.Action);
        Assert.Contains("livre", plan.Message);
    }

    private static DependencyCheckResult Ok(string name) => new(name, true, "/usr/bin/" + name, "1.0.0", (1, 0, 0), null);
    private static DependencyCheckResult Missing(string name) => new(name, false, null, null, null, "não encontrado");

    [Fact]
    public void EvaluateDependencies_ComTudoPresente_PermiteProsseguir()
    {
        var gate = StartupPlanner.EvaluateDependencies(Ok("python"), Ok("node"), Ok("npm"), Ok("dotnet"));

        Assert.True(gate.CanProceed);
        Assert.Empty(gate.BlockingReasons);
    }

    [Fact]
    public void EvaluateDependencies_ComDependenciaFaltando_BloqueiaEExplicaQual()
    {
        // "início parcial" também cobre o caso onde falta uma dependência obrigatória: a
        // decisão deve ser bloquear com uma razão clara, não seguir em frente e falhar de
        // forma confusa mais tarde.
        var gate = StartupPlanner.EvaluateDependencies(Ok("python"), Missing("node"), Ok("npm"), Ok("dotnet"));

        Assert.False(gate.CanProceed);
        Assert.Single(gate.BlockingReasons);
        Assert.Contains("Node.js", gate.BlockingReasons[0]);
    }

    [Fact]
    public void EvaluateDependencies_ComVariasFaltando_ListaTodasAsRazoes()
    {
        var gate = StartupPlanner.EvaluateDependencies(Missing("python"), Missing("node"), Ok("npm"), Missing("dotnet"));

        Assert.False(gate.CanProceed);
        Assert.Equal(3, gate.BlockingReasons.Count);
    }
}
