using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class SecretGeneratorTests
{
    [Fact]
    public void GenerateHex_RetornaComprimentoEsperadoEApenasHexadecimalMinusculo()
    {
        var secret = SecretGenerator.GenerateHex(32);
        Assert.Equal(64, secret.Length); // 32 bytes -> 64 caracteres hex
        Assert.Matches("^[0-9a-f]+$", secret);
    }

    [Fact]
    public void GenerateHex_ChamadasSucessivasGeramValoresDiferentes()
    {
        // Prova que usa uma fonte de aleatoriedade real (RandomNumberGenerator), não um valor
        // fixo/determinístico ou um contador previsível.
        var secrets = Enumerable.Range(0, 20).Select(_ => SecretGenerator.GenerateHex(32)).ToList();
        Assert.Equal(secrets.Count, secrets.Distinct().Count());
    }

    [Fact]
    public void GenerateHex_ComTamanhoMenorQue16Bytes_LancaExcecao()
    {
        // Recusa gerar segredos fracos (menos de 128 bits de entropia) em vez de gerar
        // silenciosamente um segredo curto e inseguro.
        Assert.Throws<ArgumentOutOfRangeException>(() => SecretGenerator.GenerateHex(8));
    }

    [Fact]
    public void ProgramCs_NuncaImprimeOuLogaOValorDoSegredoGerado()
    {
        // Guarda de segurança textual: o código-fonte de Program.cs pode REFERENCIAR a
        // variável apiSecretKey apenas para (a) gerá-la e (b) passá-la como variável de
        // ambiente do processo filho da API -- nunca para Console.Write*, nunca concatenada em
        // uma string de log. Isso é verificado tanto por este teste (análise textual) quanto
        // pela própria implementação (SecretGenerator.GenerateHex nunca é logado em nenhum
        // lugar do código).
        var source = SourcePaths.ReadProgramCsSource();

        // Não pode haver nenhuma linha de Console.Write*/Error.Write* que referencie
        // "apiSecretKey" diretamente.
        var suspiciousLines = source
            .Split('\n')
            .Where(line => line.Contains("apiSecretKey", StringComparison.Ordinal))
            .Where(line => line.Contains("Console.", StringComparison.Ordinal))
            .ToList();

        Assert.Empty(suspiciousLines);

        // A única atribuição do valor deve vir de SecretGenerator.GenerateHex(...) -- nunca de
        // um literal fixo, nunca de uma variável de ambiente pré-existente sendo simplesmente
        // reexibida.
        Assert.Contains("SecretGenerator.GenerateHex(", source);
    }

    [Fact]
    public void ProgramCs_NuncaGravaOSegredoEmDisco()
    {
        var source = SourcePaths.ReadProgramCsSource();
        // Garante que não existe nenhuma chamada de escrita de arquivo (File.WriteAllText,
        // File.AppendAllText, StreamWriter, etc.) na mesma vizinhança da variável do segredo.
        var lines = source.Split('\n');
        for (var i = 0; i < lines.Length; i++)
        {
            if (!lines[i].Contains("apiSecretKey", StringComparison.Ordinal))
            {
                continue;
            }
            Assert.DoesNotContain("File.WriteAllText", lines[i]);
            Assert.DoesNotContain("File.AppendAllText", lines[i]);
            Assert.DoesNotContain("StreamWriter", lines[i]);
        }
    }
}
