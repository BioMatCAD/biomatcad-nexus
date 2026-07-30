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

    // --- Detecção real, contra os binários genuinamente instalados NESTA máquina --------------
    // Não usa fakes/mocks aqui: python, node, npm e dotnet estão realmente instalados no
    // ambiente de execução dos testes, então a detecção é exercida de verdade via subprocess
    // "--version", provando que PathResolver + DependencyDetector funcionam de ponta a ponta.
    //
    // BUG REAL CORRIGIDO (relatado pelo usuário após validação no Windows do commit 774b5ae):
    // estes quatro testes tinham "isWindows: false" HARDCODED, mas liam o PATH REAL da máquina
    // que roda os testes. No sandbox Linux isso coincidia (PATH Linux + isWindows=false), mas ao
    // rodar exatamente esta mesma suíte em um Windows real, o PATH real é do Windows enquanto
    // isWindows continuava fixo em false -- fazendo DetectNpm resolver o "npm" SEM extensão (o
    // script POSIX que o instalador do Node também deixa em "C:\Program Files\nodejs\", ao
    // lado de "npm.cmd") em vez de "npm.cmd", e então tentar executá-lo diretamente, falhando
    // com "not a valid Win32 application". A correção é usar OperatingSystem.IsWindows() de
    // verdade (não mais hardcoded), tornando este teste uma prova real de detecção de
    // dependências NA PLATAFORMA QUE DE FATO ESTÁ RODANDO O TESTE -- tanto Linux quanto Windows.

    [Fact]
    public void DetectPython_NaPlataformaReal_EncontraPython()
    {
        var result = DependencyDetector.DetectPython(Environment.GetEnvironmentVariable("PATH"), Environment.GetEnvironmentVariable("PATHEXT"), OperatingSystem.IsWindows());
        Assert.True(result.Found, result.Error);
        Assert.NotNull(result.VersionParsed);
        Assert.True(result.VersionParsed!.Value.Major >= 3);
    }

    [Fact]
    public void DetectNode_NaPlataformaReal_EncontraNode()
    {
        var result = DependencyDetector.DetectNode(Environment.GetEnvironmentVariable("PATH"), Environment.GetEnvironmentVariable("PATHEXT"), OperatingSystem.IsWindows());
        Assert.True(result.Found, result.Error);
        Assert.NotNull(result.VersionParsed);
    }

    [Fact]
    public void DetectNpm_NaPlataformaReal_EncontraNpm()
    {
        var result = DependencyDetector.DetectNpm(Environment.GetEnvironmentVariable("PATH"), Environment.GetEnvironmentVariable("PATHEXT"), OperatingSystem.IsWindows());
        Assert.True(result.Found, result.Error);
        // No Windows, o caminho resolvido tem que ser especificamente o "npm.cmd" (nunca o
        // script POSIX sem extensão que o instalador do Node também deixa ao lado) -- é
        // exatamente essa distinção que causou a falha real relatada pelo usuário.
        if (OperatingSystem.IsWindows())
        {
            Assert.EndsWith(".cmd", result.ResolvedPath, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void DetectDotnet_NaPlataformaReal_EncontraDotnet()
    {
        var result = DependencyDetector.DetectDotnet(Environment.GetEnvironmentVariable("PATH"), Environment.GetEnvironmentVariable("PATHEXT"), OperatingSystem.IsWindows());
        Assert.True(result.Found, result.Error);
    }

    [Fact]
    public void DetectPython_ComPathVazio_RetornaNaoEncontradoSemLancarExcecao()
    {
        // "detecção de dependências" também cobre o caminho negativo: PATH vazio/ausente não
        // deve lançar exceção, deve reportar Found=false com uma mensagem de erro útil -- em
        // qualquer plataforma.
        var result = DependencyDetector.DetectPython(pathEnv: "", pathExtEnv: null, OperatingSystem.IsWindows());
        Assert.False(result.Found);
        Assert.NotNull(result.Error);
    }

    [Fact]
    public void WhichCommand_ComPathContendoNpmSemExtensaoENpmCmd_ResolveDiferenteConformeIsWindows()
    {
        // Regressao direta da CAUSA RAIZ do bug real relatado: reproduz exatamente o layout do
        // instalador do Node no Windows (um "npm" sem extensao -- script POSIX -- E "npm.cmd"
        // no MESMO diretorio). Prova a causa exata: quando "isWindows" e (incorretamente) false
        // -- como estava hardcoded nos 4 testes de deteccao antes desta correcao --, a resolucao
        // encontra o "npm" SEM extensao (o script POSIX que o Windows nao consegue executar
        // diretamente, causando "not a valid Win32 application"); quando "isWindows" e true (o
        // valor correto, que so vem de OperatingSystem.IsWindows() de verdade), a expansao de
        // PATHEXT sempre encontra "npm.cmd" primeiro. Este teste e executavel e verificavel em
        // qualquer SO, porque exercita a LOGICA de PathResolver diretamente (nao depende do SO
        // real ter Node.js instalado).
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-npm-cmd-regressao-");
        try
        {
            File.WriteAllText(Path.Combine(tmpDir.FullName, "npm"), "#!/bin/sh\necho fake\n");
            File.WriteAllText(Path.Combine(tmpDir.FullName, "npm.cmd"), "@echo off\r\necho 10.9.8\r\n");

            var resolvedComIsWindowsFalso = PathResolver.WhichCommand("npm", tmpDir.FullName, ".COM;.EXE;.BAT;.CMD", isWindows: false);
            var resolvedComIsWindowsVerdadeiro = PathResolver.WhichCommand("npm", tmpDir.FullName, ".COM;.EXE;.BAT;.CMD", isWindows: true);

            Assert.Equal(Path.Combine(tmpDir.FullName, "npm"), resolvedComIsWindowsFalso);
            Assert.EndsWith("npm.cmd", resolvedComIsWindowsVerdadeiro, StringComparison.OrdinalIgnoreCase);
            Assert.NotEqual(resolvedComIsWindowsFalso, resolvedComIsWindowsVerdadeiro);
        }
        finally
        {
            tmpDir.Delete(recursive: true);
        }
    }
}
