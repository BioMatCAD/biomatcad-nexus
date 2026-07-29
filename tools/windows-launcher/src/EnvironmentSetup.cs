namespace BioMatCAD.Launcher;

public sealed record StepResult(string Name, bool Ok, string Message);

/// <summary>
/// Passos de preparação do ambiente da API (venv + pip install -e .) e do frontend
/// (node_modules), item 3-5 do comportamento pedido. Usa apenas comandos já resolvidos por
/// <see cref="PathResolver"/> e executados via <see cref="ProcessSupervisor.RunToCompletion"/>
/// (ArgumentList, sem shell).
/// </summary>
public static class EnvironmentSetup
{
    public static string VenvPythonPath(string venvDir, bool isWindows) =>
        isWindows
            ? Path.Combine(venvDir, "Scripts", "python.exe")
            : Path.Combine(venvDir, "bin", "python3");

    /// <summary>
    /// Garante que apps/api/.venv existe, criando-o com o Python do sistema se necessário.
    /// Retorna o caminho para o interpretador Python DENTRO do venv.
    /// </summary>
    public static (StepResult Result, string? VenvPythonPath) EnsureApiVenv(
        string apiDir,
        string systemPythonPath,
        bool isWindows)
    {
        var venvDir = Path.Combine(apiDir, ".venv");
        var venvPython = VenvPythonPath(venvDir, isWindows);

        if (File.Exists(venvPython))
        {
            return (new StepResult("venv_api", true, $"Ambiente virtual já existe em {venvDir}."), venvPython);
        }

        var (exitCode, output) = ProcessSupervisor.RunToCompletion(
            systemPythonPath,
            ["-m", "venv", venvDir],
            apiDir,
            timeout: TimeSpan.FromMinutes(3));

        if (exitCode != 0 || !File.Exists(venvPython))
        {
            return (new StepResult("venv_api", false, $"Falha ao criar venv em {venvDir}. Saída: {Truncate(output)}"), null);
        }

        return (new StepResult("venv_api", true, $"Ambiente virtual criado em {venvDir}."), venvPython);
    }

    /// <summary>
    /// Instala a API em modo editável (pip install -e .) dentro do venv, apenas se um marcador
    /// de instalação (o próprio pacote importável) ainda não existir -- evita reinstalar em
    /// toda inicialização quando nada mudou.
    /// </summary>
    public static StepResult EnsureApiInstalled(string apiDir, string venvPythonPath)
    {
        var (checkExitCode, _) = ProcessSupervisor.RunToCompletion(
            venvPythonPath,
            ["-c", "import biomatcad_api"],
            apiDir,
            timeout: TimeSpan.FromSeconds(30));

        if (checkExitCode == 0)
        {
            return new StepResult("pip_install_api", true, "Pacote biomatcad_api já instalado no venv -- pip install -e . não é necessário.");
        }

        var (exitCode, output) = ProcessSupervisor.RunToCompletion(
            venvPythonPath,
            ["-m", "pip", "install", "-e", "."],
            apiDir,
            timeout: TimeSpan.FromMinutes(10));

        return exitCode == 0
            ? new StepResult("pip_install_api", true, "pip install -e . concluído com sucesso.")
            : new StepResult("pip_install_api", false, $"pip install -e . falhou. Saída: {Truncate(output)}");
    }

    /// <summary>
    /// Garante que node_modules existe e está minimamente coerente com package-lock.json,
    /// rodando "npm ci" (instalação limpa e reprodutível) apenas quando necessário.
    /// </summary>
    public static StepResult EnsureFrontendDependencies(string webDir, string npmPath)
    {
        var nodeModulesDir = Path.Combine(webDir, "node_modules");
        var packageLock = Path.Combine(webDir, "package-lock.json");

        if (Directory.Exists(nodeModulesDir) && Directory.EnumerateFileSystemEntries(nodeModulesDir).Any())
        {
            return new StepResult("npm_install_frontend", true, $"node_modules já existe em {nodeModulesDir}.");
        }

        var installArgs = File.Exists(packageLock) ? new[] { "ci" } : new[] { "install" };
        var (exitCode, output) = ProcessSupervisor.RunToCompletion(
            npmPath,
            installArgs,
            webDir,
            timeout: TimeSpan.FromMinutes(10));

        return exitCode == 0
            ? new StepResult("npm_install_frontend", true, $"npm {installArgs[0]} concluído com sucesso.")
            : new StepResult("npm_install_frontend", false, $"npm {installArgs[0]} falhou. Saída: {Truncate(output)}");
    }

    private static string Truncate(string s, int max = 2000) => s.Length <= max ? s : s[..max] + "... [truncado]";
}
