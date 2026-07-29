using System.Runtime.CompilerServices;

namespace BioMatCAD.Launcher.Tests;

/// <summary>
/// Localiza arquivos-fonte do launcher (como Program.cs, que não é compilado no projeto de
/// testes por usar top-level statements) a partir do caminho REAL do arquivo de teste em
/// tempo de compilação (via [CallerFilePath]), que o compilador grava como caminho absoluto
/// independente de onde o teste é executado (bin/Debug/..., CI, etc.).
/// </summary>
public static class SourcePaths
{
    public static string ThisTestProjectDir([CallerFilePath] string here = "") => Path.GetDirectoryName(here)!;

    public static string LauncherRootDir([CallerFilePath] string here = "") =>
        Path.GetFullPath(Path.Combine(Path.GetDirectoryName(here)!, "..", ".."));

    public static string ProgramCsPath() => Path.Combine(LauncherRootDir(), "Program.cs");

    public static string ReadProgramCsSource() => File.ReadAllText(ProgramCsPath());
}
