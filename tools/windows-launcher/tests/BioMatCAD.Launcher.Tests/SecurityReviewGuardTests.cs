using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

/// <summary>
/// Testes de guarda (análise textual do código-fonte real) para as restrições de segurança
/// explicitamente pedidas: sem command injection, sem taskkill genérico, sem Docker/sudo/admin,
/// sem senhas/tokens fixos no código. Cada teste foi verificado manualmente reintroduzindo o
/// padrão proibido e confirmando que o teste correspondente falha, depois revertendo -- mesmo
/// padrão de "guarda textual" já usado em apps/web/tests/e2eGlobalSetup.test.ts.
/// </summary>
public class SecurityReviewGuardTests
{
    private static string ReadSource(string fileName) =>
        File.ReadAllText(Path.Combine(SourcePaths.LauncherRootDir(), "src", fileName));

    private static string ReadProgramSource() => SourcePaths.ReadProgramCsSource();

    /// <summary>
    /// Remove linhas que são comentário puro (// ou ///, após trim) antes de aplicar checagens
    /// de substring -- evita falso-positivo quando o próprio comentário explicativo do código
    /// CITA o termo proibido para documentar por que ele é evitado (ex.: "nunca um taskkill
    /// genérico", "nunca habilita um ambiente clínico"). Mesma técnica já usada em
    /// apps/web/tests/verticalSpecGuard.test.ts para o mesmo tipo de falso-positivo.
    /// </summary>
    private static string StripCommentOnlyLines(string source) =>
        string.Join('\n', source.Split('\n').Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));

    [Fact]
    public void ProcessSupervisor_NuncaUsaArgumentsConcatenadoComoString()
    {
        // Defesa central contra command injection: todo ProcessStartInfo deve usar
        // ArgumentList (cada argumento como token discreto), nunca a propriedade `Arguments`
        // (string única que passa por interpretação de shell em alguns casos no Windows).
        var source = ReadSource("ProcessSupervisor.cs");
        Assert.DoesNotContain(".Arguments =", source);
        Assert.DoesNotContain("psi.Arguments", source);
        Assert.Contains("ArgumentList.Add", source);
    }

    [Fact]
    public void DependencyDetector_NuncaUsaArgumentsConcatenadoComoString()
    {
        var source = ReadSource("DependencyDetector.cs");
        Assert.DoesNotContain(".Arguments =", source);
        Assert.Contains("ArgumentList.Add", source);
    }

    [Fact]
    public void ProcessosDeLongaDuracaoEDeInstalacao_NuncaUsamUseShellExecuteVerdadeiro()
    {
        // UseShellExecute=true só é aceitável para abrir a URL fixa do navegador em Program.cs
        // (ver próximo teste) -- em nenhum outro lugar do código deve aparecer.
        Assert.DoesNotContain("UseShellExecute = true", ReadSource("ProcessSupervisor.cs"));
        Assert.DoesNotContain("UseShellExecute = true", ReadSource("DependencyDetector.cs"));
    }

    [Fact]
    public void ProgramCs_UseShellExecuteVerdadeiro_SoApareceParaAbrirUrlFixaDoNavegador()
    {
        var source = ReadProgramSource();
        var occurrences = System.Text.RegularExpressions.Regex.Matches(source, "UseShellExecute = true");

        Assert.Single(occurrences);

        // A única ocorrência deve estar dentro de TryOpenBrowser, operando sobre uma URL
        // constante interna ("http://localhost:5173/login"), nunca sobre input externo.
        var tryOpenBrowserIndex = source.IndexOf("static void TryOpenBrowser", StringComparison.Ordinal);
        var useShellExecuteIndex = source.IndexOf("UseShellExecute = true", StringComparison.Ordinal);
        Assert.True(tryOpenBrowserIndex >= 0 && useShellExecuteIndex > tryOpenBrowserIndex);
    }

    [Fact]
    public void NenhumArquivoDeFonteContemTaskkillGenerico()
    {
        foreach (var file in Directory.GetFiles(Path.Combine(SourcePaths.LauncherRootDir(), "src"), "*.cs"))
        {
            Assert.DoesNotContain("taskkill", StripCommentOnlyLines(File.ReadAllText(file)), StringComparison.OrdinalIgnoreCase);
        }
        Assert.DoesNotContain("taskkill", StripCommentOnlyLines(ReadProgramSource()), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void NenhumArquivoDeFonteReferenciaDockerSudoOuElevacaoDeAdministrador()
    {
        var forbidden = new[] { "docker", "sudo", "runas", "RequireAdministrator", "UseShellExecute = true.*runas" };
        var allSourceFiles = Directory.GetFiles(Path.Combine(SourcePaths.LauncherRootDir(), "src"), "*.cs")
            .Select(File.ReadAllText)
            .Append(ReadProgramSource());

        foreach (var source in allSourceFiles)
        {
            Assert.DoesNotContain("docker", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("sudo", source, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("runas", source, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public void ProgramCs_NuncaHabilitaAmbienteClinicoENuncaFixaSenhasOuTokens()
    {
        var source = ReadProgramSource();

        // ENVIRONMENT é sempre "test" -- a única atribuição a essa chave de ambiente em todo
        // o arquivo deve ser "test", nunca "production"/"clinical"/qualquer outra coisa. Nota:
        // a palavra "clínico" aparece DE PROPÓSITO no banner permanente obrigatório
        // ("NÃO UTILIZAR DADOS CLÍNICOS REAIS") -- isso é o oposto de "habilitar" um ambiente
        // clínico, então a checagem certa não é "a palavra nunca aparece", e sim "ENVIRONMENT
        // nunca é atribuído a um valor que não seja 'test'".
        Assert.Contains("[\"ENVIRONMENT\"] = \"test\"", source);
        var environmentAssignments = System.Text.RegularExpressions.Regex.Matches(source, "\\[\"ENVIRONMENT\"\\]\\s*=\\s*\"([^\"]*)\"");
        Assert.NotEmpty(environmentAssignments);
        foreach (System.Text.RegularExpressions.Match m in environmentAssignments)
        {
            Assert.Equal("test", m.Groups[1].Value);
        }

        // Nenhuma senha/token literal -- API_SECRET_KEY é sempre gerado por
        // SecretGenerator.GenerateHex, nunca um literal fixo.
        var codeOnly = StripCommentOnlyLines(source);
        Assert.DoesNotContain("password", codeOnly, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("token =", codeOnly, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ProgramCs_ExibePermanentementeOBannerDeAmbienteDeTeste()
    {
        var source = ReadProgramSource();
        Assert.Contains("AMBIENTE DE PESQUISA", source);
        Assert.Contains("NÃO UTILIZAR DADOS CLÍNICOS REAIS", source);
        // O banner é impresso tanto no início quanto antes do loop de espera principal --
        // "mostrar permanentemente" é interpretado como "sempre visível durante a operação",
        // não apenas um flash inicial que desaparece quando os logs rolam.
        var occurrences = System.Text.RegularExpressions.Regex.Matches(source, "PrintBanner\\(\\)");
        Assert.True(occurrences.Count >= 2, "O banner deve ser impresso mais de uma vez (início + antes do loop de espera).");
    }

    [Fact]
    public void ProgramCs_NaoExecutaSeedAutomaticamenteSemMencionarAoUsuario()
    {
        var source = ReadProgramSource();
        // O launcher não deve chamar nenhum script de seed automaticamente dentro do fluxo
        // principal de inicialização.
        Assert.DoesNotContain("seed_e2e", source, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("run_seed", source, StringComparison.OrdinalIgnoreCase);
    }
}
