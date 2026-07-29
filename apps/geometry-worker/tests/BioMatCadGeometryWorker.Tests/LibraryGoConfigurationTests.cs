// Teste de "guarda de configuração" para a chamada a PicoGK.Library.Go em
// GyroidScaffoldBuilder.cs. Não pode ser um teste de comportamento em runtime: este projeto de
// testes deliberadamente NÃO referencia o pacote PicoGK (ver comentário no .csproj) para
// permanecer executável neste sandbox Linux sem o runtime nativo do PicoGK. Como consequência,
// não é possível instanciar de verdade Library.Go() aqui e observar se o viewer realmente fecha
// sozinho -- isso só pode ser confirmado numa execução real (Windows x64, ver
// docs/examples/WINDOWS_EXECUTION_KIT.md).
//
// O que ESTE teste garante, de forma real e executável: que o código-fonte de
// GyroidScaffoldBuilder.cs efetivamente passa `bEndAppWithTask: true` na chamada a Library.Go
// -- o parâmetro oficial e documentado (confirmado nesta sessão por reflexão contra o
// PicoGK.dll 2.2.0 realmente instalado, não por suposição) para o viewer encerrar sozinho ao
// término da tarefa. Existe para impedir que uma futura edição remova silenciosamente esse
// argumento e reintroduza o bug real relatado pelo usuário (janela do PicoGK exigindo
// fechamento manual, inflando duration_seconds com tempo de espera humana).
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class LibraryGoConfigurationTests
{
    private static string ReadGyroidScaffoldBuilderSource()
    {
        // Caminho relativo ao diretório de saída do teste (bin/Debug/net9.0/...) até o
        // código-fonte real do worker -- o mesmo arquivo que é de fato compilado no projeto
        // principal (não uma cópia).
        string path = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "GyroidScaffoldBuilder.cs");
        path = Path.GetFullPath(path);
        Assert.True(File.Exists(path), $"GyroidScaffoldBuilder.cs não encontrado no caminho esperado: {path}");
        return File.ReadAllText(path);
    }

    [Fact]
    public void LibraryGoCall_PassesBEndAppWithTaskTrue()
    {
        string source = ReadGyroidScaffoldBuilderSource();

        Assert.Contains("Library.Go(", source);

        // A chamada real deve conter o argumento nomeado bEndAppWithTask: true associado à
        // invocação de Library.Go -- não apenas em algum comentário isolado.
        int callIndex = source.IndexOf("Library.Go(", StringComparison.Ordinal);
        Assert.True(callIndex >= 0);

        // A chamada é multi-linha (lambda como segundo argumento, agora com o laço de
        // calibração fechada contra a malha real -- correção pós-execução real). Em vez de uma
        // janela de tamanho fixo (frágil a crescimento do corpo do lambda), procura o argumento
        // nomeado em todo o restante do arquivo a partir do início da chamada -- seguro porque
        // há apenas UMA chamada a Library.Go neste arquivo (confirmado logo acima).
        string callRegion = source.Substring(callIndex);
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(source, @"Library\.Go\("));
        Assert.Contains("bEndAppWithTask: true", callRegion);
    }

    [Fact]
    public void LibraryGoCall_HasExplanatoryCommentAboutRealReflectionFinding()
    {
        // Guarda adicional e mais fraca: garante que a justificativa (não uma suposição, mas
        // uma verificação real por reflexão) permanece documentada perto da chamada, para que
        // uma futura remoção do parâmetro não passe despercebida numa revisão de código.
        string source = ReadGyroidScaffoldBuilderSource();
        Assert.Contains("bEndAppWithTask", source);
        Assert.Contains("reflexão", source, StringComparison.OrdinalIgnoreCase);
    }
}
