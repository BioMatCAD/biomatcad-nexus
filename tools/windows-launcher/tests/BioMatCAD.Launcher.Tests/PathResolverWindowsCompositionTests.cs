using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

/// <summary>
/// "Composição de comandos Windows": exercita PathResolver.WhichCommand em MODO WINDOWS
/// (isWindows: true) usando um PATH/PATHEXT sintéticos apontando para uma árvore de diretórios
/// temporária real com arquivos reais (npm.cmd, python.exe, node.exe, dotnet.exe), mesmo
/// rodando estes testes em Linux -- a lógica de composição de nome+extensão é pura o
/// suficiente para ser testada em qualquer SO host, apenas simulando como o PATH real de um
/// Windows se pareceria.
/// </summary>
public class PathResolverWindowsCompositionTests : IDisposable
{
    private readonly string _fakeWindowsPathDir;

    public PathResolverWindowsCompositionTests()
    {
        _fakeWindowsPathDir = Directory.CreateTempSubdirectory("biomatcad-fake-win-path-").FullName;
    }

    public void Dispose() => Directory.Delete(_fakeWindowsPathDir, recursive: true);

    private void Touch(string relativeFileName) =>
        File.WriteAllText(Path.Combine(_fakeWindowsPathDir, relativeFileName), "@echo off\n");

    [Fact]
    public void WhichCommand_NoWindows_EncontraNpmCmdAntesDeQualquerOutraExtensao()
    {
        // Reproduz o cenário real do instalador do Node no Windows: só existe npm.cmd, nunca
        // um npm.exe nativo.
        Touch("npm.cmd");

        var resolved = PathResolver.WhichCommand("npm.cmd", _fakeWindowsPathDir, ".COM;.EXE;.BAT;.CMD", isWindows: true);

        Assert.NotNull(resolved);
        Assert.EndsWith("npm.cmd", resolved);
        Assert.DoesNotContain("npm.cmd.", Path.GetFileName(resolved)); // nunca "npm.cmd.EXE"
    }

    [Fact]
    public void WhichCommand_NoWindows_ComNomeSemExtensao_TentaCadaSufixoDoPathExtEmOrdem()
    {
        // "python" (sem extensão) deve testar .COM, .EXE, .BAT, .CMD nessa ordem -- só existe
        // python.exe aqui, então deve encontrá-lo mesmo não sendo o primeiro candidato testado.
        Touch("python.exe");

        var resolved = PathResolver.WhichCommand("python", _fakeWindowsPathDir, ".COM;.EXE;.BAT;.CMD", isWindows: true);

        Assert.NotNull(resolved);
        Assert.EndsWith("python.exe", resolved);
    }

    [Fact]
    public void WhichCommand_NoWindows_ComPathExtAusente_UsaValorPadraoDeUmWindowsLimpo()
    {
        Touch("dotnet.exe");

        var resolved = PathResolver.WhichCommand("dotnet", _fakeWindowsPathDir, pathExtValue: null, isWindows: true);

        Assert.NotNull(resolved);
        Assert.EndsWith("dotnet.exe", resolved);
    }

    [Fact]
    public void WhichCommand_NoWindows_QuandoNadaExisteEmNenhumDiretorio_RetornaNull()
    {
        var resolved = PathResolver.WhichCommand("comando-inexistente", _fakeWindowsPathDir, ".EXE", isWindows: true);
        Assert.Null(resolved);
    }

    [Fact]
    public void WhichCommand_NoWindows_ProcuraEmMultiplosDiretoriosDoPathNaOrdem()
    {
        var secondDir = Directory.CreateTempSubdirectory("biomatcad-fake-win-path-2-").FullName;
        try
        {
            File.WriteAllText(Path.Combine(secondDir, "node.exe"), "");
            var combinedPath = _fakeWindowsPathDir + Path.PathSeparator + secondDir;

            var resolved = PathResolver.WhichCommand("node", combinedPath, ".EXE", isWindows: true);

            Assert.NotNull(resolved);
            Assert.Equal(Path.GetFullPath(Path.Combine(secondDir, "node.exe")), resolved);
        }
        finally
        {
            Directory.Delete(secondDir, recursive: true);
        }
    }

    [Fact]
    public void ResolveNpmCandidateNames_NoWindows_PrioriaNpmCmdSobreNpmSemExtensao()
    {
        var candidates = PathResolver.ResolveNpmCandidateNames(isWindows: true);
        Assert.Equal("npm.cmd", candidates[0]);
    }

    [Fact]
    public void ResolvePythonCandidateNames_NoWindows_UsaPythonEPyLancador()
    {
        var candidates = PathResolver.ResolvePythonCandidateNames(isWindows: true);
        Assert.Contains("python", candidates);
    }

    [Fact]
    public void ResolvePythonCandidateNames_ForaDoWindows_UsaPython3Primeiro()
    {
        var candidates = PathResolver.ResolvePythonCandidateNames(isWindows: false);
        Assert.Equal("python3", candidates[0]);
    }
}
