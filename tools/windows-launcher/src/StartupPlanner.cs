namespace BioMatCAD.Launcher;

public enum ServiceAction
{
    StartNew,
    ReuseExisting,
}

public sealed record ServicePlanInput(string Name, int Port, bool PortAlreadyInUse);

public sealed record ServicePlan(string Name, int Port, ServiceAction Action, string Message);

public sealed record DependencyGateResult(bool CanProceed, IReadOnlyList<string> BlockingReasons);

/// <summary>
/// Lógica de decisão PURA (sem I/O, sem processos reais) para as perguntas "o que fazer" da
/// orquestração: se uma porta já está ocupada, se dependências obrigatórias estão faltando.
/// Mantida separada da execução real (ProcessSupervisor, DependencyDetector, PortChecker) para
/// que "início parcial" e "API/frontend já ativos" sejam testáveis com dados sintéticos, sem
/// precisar subir processos de verdade em cada teste.
/// </summary>
public static class StartupPlanner
{
    public static ServicePlan PlanService(ServicePlanInput input)
    {
        if (input.PortAlreadyInUse)
        {
            return new ServicePlan(
                input.Name,
                input.Port,
                ServiceAction.ReuseExisting,
                $"{input.Name}: porta {input.Port} já está em uso -- assumindo que o serviço já está rodando; " +
                "o launcher NÃO vai iniciar uma nova instância.");
        }

        return new ServicePlan(
            input.Name,
            input.Port,
            ServiceAction.StartNew,
            $"{input.Name}: porta {input.Port} livre -- iniciando novo processo.");
    }

    public static DependencyGateResult EvaluateDependencies(
        DependencyCheckResult python,
        DependencyCheckResult node,
        DependencyCheckResult npm,
        DependencyCheckResult dotnet)
    {
        var reasons = new List<string>();
        if (!python.Found) reasons.Add("Python não encontrado no PATH (necessário para a API).");
        if (!node.Found) reasons.Add("Node.js não encontrado no PATH (necessário para o frontend).");
        if (!npm.Found) reasons.Add("npm não encontrado no PATH (necessário para instalar/rodar o frontend).");
        if (!dotnet.Found) reasons.Add(".NET SDK/Runtime não encontrado no PATH (necessário para o worker geométrico PicoGK).");
        return new DependencyGateResult(reasons.Count == 0, reasons);
    }
}
