using System.Diagnostics;
using System.Text.RegularExpressions;

namespace BioMatCAD.Launcher;

public sealed record DependencyCheckResult(
    string DependencyName,
    bool Found,
    string? ResolvedPath,
    string? VersionRaw,
    (int Major, int Minor, int Patch)? VersionParsed,
    string? Error);

/// <summary>
/// Detecta Python, Node.js, npm e .NET no PATH real da máquina, sem shell (todas as chamadas
/// usam ProcessStartInfo.ArgumentList com UseShellExecute=false e um FileName já resolvido
/// para caminho absoluto via <see cref="PathResolver"/> -- nunca uma string de comando
/// concatenada). Resolver e confirmar são passos separados: primeiro localizamos o binário via
/// PATH (PathResolver, testável isoladamente), depois o executamos de verdade com "--version"
/// para confirmar que funciona e extrair a versão.
/// </summary>
public static class DependencyDetector
{
    // Aceita "Python 3.14.0", "Python 3.14.0rc1", "Python 3.9.18+", etc. -- extrai só os
    // componentes numéricos de major.minor.patch como inteiros REAIS (nunca compara versões
    // como string: "3.14" < "3.9" seria verdadeiro por comparação lexicográfica, o que é
    // exatamente o bug clássico que este parser evita -- ver PythonVersionParsingTests, que
    // testa 3.14 explicitamente).
    private static readonly Regex VersionRegex = new(@"(\d+)\.(\d+)(?:\.(\d+))?", RegexOptions.Compiled);

    public static (int Major, int Minor, int Patch)? ParseVersion(string? rawOutput)
    {
        if (string.IsNullOrWhiteSpace(rawOutput))
        {
            return null;
        }
        var match = VersionRegex.Match(rawOutput);
        if (!match.Success)
        {
            return null;
        }
        var major = int.Parse(match.Groups[1].Value);
        var minor = int.Parse(match.Groups[2].Value);
        var patch = match.Groups[3].Success ? int.Parse(match.Groups[3].Value) : 0;
        return (major, minor, patch);
    }

    /// <summary>
    /// Compara duas versões (major, minor, patch) numericamente -- nunca como string. Usado
    /// para decidir se uma versão detectada satisfaz um mínimo exigido.
    /// </summary>
    public static bool IsAtLeast((int Major, int Minor, int Patch) version, (int Major, int Minor, int Patch) minimum)
    {
        if (version.Major != minimum.Major) return version.Major > minimum.Major;
        if (version.Minor != minimum.Minor) return version.Minor > minimum.Minor;
        return version.Patch >= minimum.Patch;
    }

    private static DependencyCheckResult DetectSingle(
        string dependencyName,
        IReadOnlyList<string> candidateNames,
        string[] versionArgs,
        string? pathEnv,
        string? pathExtEnv,
        bool isWindows)
    {
        string? resolvedPath = null;
        foreach (var candidate in candidateNames)
        {
            resolvedPath = PathResolver.WhichCommand(candidate, pathEnv, pathExtEnv, isWindows);
            if (resolvedPath is not null)
            {
                break;
            }
        }

        if (resolvedPath is null)
        {
            return new DependencyCheckResult(
                dependencyName, Found: false, ResolvedPath: null, VersionRaw: null, VersionParsed: null,
                Error: $"Nenhum dos candidatos [{string.Join(", ", candidateNames)}] foi encontrado no PATH.");
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = resolvedPath,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            foreach (var arg in versionArgs)
            {
                psi.ArgumentList.Add(arg);
            }

            using var process = Process.Start(psi);
            if (process is null)
            {
                return new DependencyCheckResult(dependencyName, false, resolvedPath, null, null, "Process.Start retornou null.");
            }

            var stdout = process.StandardOutput.ReadToEnd();
            var stderr = process.StandardError.ReadToEnd();
            process.WaitForExit(10_000);

            var combined = string.IsNullOrWhiteSpace(stdout) ? stderr : stdout; // alguns comandos (ex.: python --version em versões antigas) imprimem em stderr
            var parsedVersion = ParseVersion(combined);

            return new DependencyCheckResult(dependencyName, Found: true, resolvedPath, combined.Trim(), parsedVersion, Error: null);
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            return new DependencyCheckResult(dependencyName, false, resolvedPath, null, null, ex.Message);
        }
    }

    public static DependencyCheckResult DetectPython(string? pathEnv, string? pathExtEnv, bool isWindows) =>
        DetectSingle("Python", PathResolver.ResolvePythonCandidateNames(isWindows), ["--version"], pathEnv, pathExtEnv, isWindows);

    public static DependencyCheckResult DetectNode(string? pathEnv, string? pathExtEnv, bool isWindows) =>
        DetectSingle("Node.js", [PathResolver.ResolveNodeCandidateName(isWindows)], ["--version"], pathEnv, pathExtEnv, isWindows);

    public static DependencyCheckResult DetectNpm(string? pathEnv, string? pathExtEnv, bool isWindows) =>
        DetectSingle("npm", PathResolver.ResolveNpmCandidateNames(isWindows), ["--version"], pathEnv, pathExtEnv, isWindows);

    public static DependencyCheckResult DetectDotnet(string? pathEnv, string? pathExtEnv, bool isWindows) =>
        DetectSingle(".NET", [PathResolver.ResolveDotnetCandidateName(isWindows)], ["--version"], pathEnv, pathExtEnv, isWindows);
}
