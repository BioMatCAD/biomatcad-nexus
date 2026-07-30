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
        // Comparação insensível a maiúsculas/minúsculas: caminhos no Windows são
        // case-insensitive (NTFS preserva mas não distingue caixa) -- bug real relatado pelo
        // usuário: comparar com StringComparison ordinal padrão (sensível a caixa) fazia este
        // teste falhar no Windows real por diferenças de caixa que não têm nenhum significado
        // funcional ali.
        Assert.EndsWith("npm.cmd", resolved, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("npm.cmd.", Path.GetFileName(resolved), StringComparison.OrdinalIgnoreCase); // nunca "npm.cmd.EXE"
    }

    [Fact]
    public void WhichCommand_NoWindows_ComNomeSemExtensao_TentaCadaSufixoDoPathExtEmOrdem()
    {
        // "python" (sem extensão) deve testar .COM, .EXE, .BAT, .CMD nessa ordem -- só existe
        // python.exe aqui, então deve encontrá-lo mesmo não sendo o primeiro candidato testado.
        Touch("python.exe");

        var resolved = PathResolver.WhichCommand("python", _fakeWindowsPathDir, ".COM;.EXE;.BAT;.CMD", isWindows: true);

        Assert.NotNull(resolved);
        // Bug real relatado pelo usuário: em filesystem case-insensitive (Windows real), o
        // File.Exists("python.EXE") já retorna true na primeira tentativa (suf. ".EXE" vindo
        // do PATHEXT, maiúsculo), então o caminho resolvido preserva essa caixa ("python.EXE"),
        // nunca chegando ao fallback interno de minúsculas do WhichCommand -- que só é
        // exercitado em filesystems case-sensitive (Linux). Isso é funcionalmente correto nos
        // dois SOs (o arquivo certo é sempre encontrado), então a asserção precisa comparar
        // sem diferenciar caixa, em vez de amarrar o teste à casing de um SO específico.
        Assert.EndsWith("python.exe", resolved, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void WhichCommand_NoWindows_ComPathExtAusente_UsaValorPadraoDeUmWindowsLimpo()
    {
        Touch("dotnet.exe");

        var resolved = PathResolver.WhichCommand("dotnet", _fakeWindowsPathDir, pathExtValue: null, isWindows: true);

        Assert.NotNull(resolved);
        // Mesmo motivo de case-insensitivity do teste acima (PATHEXT padrão é maiúsculo).
        Assert.EndsWith("dotnet.exe", resolved, StringComparison.OrdinalIgnoreCase);
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
            // Mesmo motivo de case-insensitivity: em Windows real, o sufixo ".EXE" do PATHEXT
            // (maiúsculo) já casa com "node.exe" (minúsculo) na primeira tentativa via
            // File.Exists, preservando a caixa do PATHEXT no caminho retornado.
            Assert.Equal(Path.GetFullPath(Path.Combine(secondDir, "node.exe")), resolved, ignoreCase: true);
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

    [Fact]
    public void WhichCommand_NoWindows_PathExtEmMaiusculoEncontraArquivoRealEmMinusculo_ComparadoSemDiferenciarCaixa()
    {
        // Regressão dedicada de case-insensitividade de PATH/PATHEXT (item 4 do relatório real
        // de falhas de validação no Windows): PATHEXT do Windows lista sufixos em MAIÚSCULAS por
        // convenção (".EXE", ".CMD", ...), mas os binários instalados de verdade normalmente têm
        // extensão em minúsculas ("python.exe"). Prova explicitamente esse descasamento de caixa
        // (bem diferente do outro caso já coberto, "npm.cmd" vs "npm" sem extensão -- aqui é a
        // MESMA extensão, só com caixa diferente) e compara o resultado sem diferenciar
        // maiúsculas/minúsculas, que é a forma correta de comparar caminhos no Windows.
        Touch("python.exe");

        var resolved = PathResolver.WhichCommand("python", _fakeWindowsPathDir, pathExtValue: ".COM;.EXE", isWindows: true);

        Assert.NotNull(resolved);
        Assert.Equal(Path.GetFullPath(Path.Combine(_fakeWindowsPathDir, "python.exe")), resolved, ignoreCase: true);
    }
}
