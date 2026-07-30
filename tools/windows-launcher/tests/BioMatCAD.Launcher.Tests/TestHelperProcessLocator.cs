using BioMatCAD.Launcher;

namespace BioMatCAD.Launcher.Tests;

/// <summary>
/// Resolve e invoca o TestHelperProcess (ver seu .csproj para o porquê de existir) de forma
/// genuinamente multiplataforma, SEM depender de sh/sleep/python3/cmd.exe timeout do sistema
/// operacional. O "dotnet" usado para executar o helper é resolvido pela MESMA lógica de
/// produção já testada em <see cref="DependencyDetector.DetectDotnet"/> (que por sua vez usa
/// <see cref="PathResolver"/>) -- ou seja, os testes usam a resolução real do launcher (como
/// sugerido explicitamente pelo usuário), em vez de reinventar uma segunda forma de achar
/// "dotnet" só para os testes.
/// </summary>
public static class TestHelperProcessLocator
{
    private static readonly Lazy<string> DotnetPathLazy = new(() =>
    {
        var result = DependencyDetector.DetectDotnet(
            Environment.GetEnvironmentVariable("PATH"),
            Environment.GetEnvironmentVariable("PATHEXT"),
            OperatingSystem.IsWindows());

        if (!result.Found || result.ResolvedPath is null)
        {
            throw new InvalidOperationException(
                "Não foi possível resolver um executável 'dotnet' real para o processo auxiliar de testes " +
                $"(TestHelperProcess). Erro reportado: {result.Error}");
        }

        return result.ResolvedPath;
    });

    /// <summary>Caminho absoluto para o "dotnet" real usado para invocar o helper (e, quando útil
    /// isoladamente, qualquer outro cenário de teste que precise de um executável real garantido
    /// existir, sem lançar Win32Exception por arquivo inexistente).</summary>
    public static string DotnetPath => DotnetPathLazy.Value;

    private static readonly Lazy<string> HelperDllPathLazy = new(() =>
    {
        var path = Path.Combine(AppContext.BaseDirectory, "TestHelperProcess.dll");
        if (!File.Exists(path))
        {
            throw new InvalidOperationException(
                $"TestHelperProcess.dll não encontrado em '{path}'. Verifique se o projeto " +
                "tests/TestHelperProcess está referenciado (ProjectReference) por " +
                "BioMatCAD.Launcher.Tests.csproj, para que seu build seja copiado automaticamente " +
                "para o diretório de saída dos testes.");
        }
        return path;
    });

    /// <summary>
    /// Monta (FileName, Args) prontos para <c>ProcessSupervisor.StartTracked</c>/<c>RunToCompletion</c>,
    /// invocando o TestHelperProcess no modo <paramref name="mode"/> com os argumentos dados.
    /// </summary>
    public static (string FileName, string[] Args) Command(string mode, params string[] extraArgs)
    {
        var args = new string[extraArgs.Length + 2];
        args[0] = HelperDllPathLazy.Value;
        args[1] = mode;
        Array.Copy(extraArgs, 0, args, 2, extraArgs.Length);
        return (DotnetPath, args);
    }
}
