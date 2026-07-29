using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class DependencyDetectorTests
{
    // --- Parsing de versão: numérico, nunca lexicográfico -------------------------------------

    [Theory]
    [InlineData("Python 3.14.0", 3, 14, 0)]
    [InlineData("Python 3.9.18", 3, 9, 18)]
    [InlineData("Python 3.14.0rc1", 3, 14, 0)]
    [InlineData("v22.22.3", 22, 22, 3)]
    [InlineData("npm 10.9.8", 10, 9, 8)]
    public void ParseVersion_ExtraiComponentesNumericosCorretamente(string raw, int major, int minor, int patch)
    {
        var parsed = DependencyDetector.ParseVersion(raw);
        Assert.NotNull(parsed);
        Assert.Equal((major, minor, patch), parsed);
    }

    [Fact]
    public void ParseVersion_Python314_NaoEConfundidoComVersaoMenor()
    {
        // Item explicitamente pedido: "Python 3.14". Prova que 3.14 é reconhecido como MAIOR
        // que 3.9 numericamente -- se a comparação fosse por string, "3.14" < "3.9" (o '1'
        // perde para o '9' na comparação lexicográfica de caracteres), o que seria o bug
        // clássico que este código deliberadamente evita.
        var v314 = DependencyDetector.ParseVersion("Python 3.14.0")!.Value;
        var v39 = DependencyDetector.ParseVersion("Python 3.9.18")!.Value;

        Assert.True(DependencyDetector.IsAtLeast(v314, (3, 9, 0)));
        Assert.False(DependencyDetector.IsAtLeast(v39, (3, 14, 0)));

        // Comparação ingênua de string, só para documentar o bug que este teste evita:
        Assert.True(string.CompareOrdinal("3.14.0", "3.9.18") < 0, "Prova que comparação por string seria enganosa aqui.");
    }

    [Fact]
    public void IsAtLeast_ComparaMajorMinorPatchNumericamente()
    {
        Assert.True(DependencyDetector.IsAtLeast((3, 14, 1), (3, 14, 0)));
        Assert.False(DependencyDetector.IsAtLeast((3, 14, 0), (3, 14, 1)));
        Assert.True(DependencyDetector.IsAtLeast((4, 0, 0), (3, 99, 99)));
    }

    [Fact]
    public void ParseVersion_ComTextoSemNumeros_RetornaNull()
    {
        Assert.Null(DependencyDetector.ParseVersion("comando não encontrado"));
        Assert.Null(DependencyDetector.ParseVersion(""));
        Assert.Null(DependencyDetector.ParseVersion(null));
    }

    // --- Detecção real, contra os binários genuinamente instalados neste sandbox --------------
    // Não usa fakes/mocks aqui: python3, node, npm e dotnet estão realmente instalados no
    // ambiente de execução dos testes, então a detecção é exercida de verdade via subprocess
    // "--version", provando que PathResolver + DependencyDetector funcionam de ponta a ponta.

    [Fact]
    public void DetectPython_NoSandboxLinuxReal_EncontraPython3()
    {
        var result = DependencyDetector.DetectPython(Environment.GetEnvironmentVariable("PATH"), null, isWindows: false);
        Assert.True(result.Found, result.Error);
        Assert.NotNull(result.VersionParsed);
        Assert.True(result.VersionParsed!.Value.Major >= 3);
    }

    [Fact]
    public void DetectNode_NoSandboxLinuxReal_EncontraNode()
    {
        var result = DependencyDetector.DetectNode(Environment.GetEnvironmentVariable("PATH"), null, isWindows: false);
        Assert.True(result.Found, result.Error);
        Assert.NotNull(result.VersionParsed);
    }

    [Fact]
    public void DetectNpm_NoSandboxLinuxReal_EncontraNpm()
    {
        var result = DependencyDetector.DetectNpm(Environment.GetEnvironmentVariable("PATH"), null, isWindows: false);
        Assert.True(result.Found, result.Error);
    }

    [Fact]
    public void DetectDotnet_NoSandboxLinuxReal_EncontraDotnet()
    {
        var result = DependencyDetector.DetectDotnet(Environment.GetEnvironmentVariable("PATH"), null, isWindows: false);
        Assert.True(result.Found, result.Error);
    }

    [Fact]
    public void DetectPython_ComPathVazio_RetornaNaoEncontradoSemLancarExcecao()
    {
        // "detecção de dependências" também cobre o caminho negativo: PATH vazio/ausente não
        // deve lançar exceção, deve reportar Found=false com uma mensagem de erro útil.
        var result = DependencyDetector.DetectPython(pathEnv: "", pathExtEnv: null, isWindows: false);
        Assert.False(result.Found);
        Assert.NotNull(result.Error);
    }
}
