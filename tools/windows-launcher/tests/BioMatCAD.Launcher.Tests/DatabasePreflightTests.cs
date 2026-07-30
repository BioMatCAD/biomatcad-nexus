using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class DatabasePreflightTests
{
    [Theory]
    [InlineData(
        "postgresql+psycopg://biomatcad:supersegredo@localhost:5432/biomatcad",
        "postgresql+psycopg://biomatcad:***@localhost:5432/biomatcad")]
    [InlineData(
        "postgresql://user:senha-simples@host:5432/db",
        "postgresql://user:***@host:5432/db")]
    [InlineData("postgresql://localhost:5432/db", "postgresql://localhost:5432/db")] // sem credenciais, nada a mascarar
    public void SanitizeForDisplay_MascaraSenhaEmUrlDeConexao(string input, string expected)
    {
        Assert.Equal(expected, DatabasePreflight.SanitizeForDisplay(input));
    }

    [Fact]
    public void SanitizeForDisplay_LimitacaoConhecida_SenhaComArrobaLiteralNaoEhTotalmenteMascarada()
    {
        // Documenta uma limitação conhecida e aceitável: uma URL com "@" literal (não
        // percent-encoded) DENTRO da senha -- o que já é inválido pela RFC 3986 -- confunde a
        // regex sobre onde a senha termina, mascarando só até o primeiro "@". Não é o caso real
        // esperado (senhas geradas/documentadas neste projeto nunca contêm "@" sem
        // percent-encoding), mas o teste existe para que este comportamento nunca seja
        // "corrigido" silenciosamente sem entender a troca envolvida.
        var input = "postgresql://user:p@ss-with-literal-at@host:5432/db";
        var sanitized = DatabasePreflight.SanitizeForDisplay(input);
        Assert.Contains("user:***@", sanitized);
        Assert.Contains("ss-with-literal-at@host", sanitized); // parte da senha "vaza" após o primeiro @, limitação conhecida
    }

    [Fact]
    public void SanitizeForDisplay_MascaraMesmoQuandoUrlApareceEmbutidaNumaMensagemMaior()
    {
        var message = "Falha ao conectar em postgresql+psycopg://admin:senha123@db.internal:5432/prod: timeout";
        var sanitized = DatabasePreflight.SanitizeForDisplay(message);

        Assert.DoesNotContain("senha123", sanitized);
        Assert.Contains("admin:***@db.internal:5432/prod", sanitized);
    }

    [Fact]
    public void SanitizeForDisplay_NuncaExibeApiSecretKeyOuJwtSeAparecerAcidentalmenteEmTexto()
    {
        // Não são o alvo principal desta função (isso é regex de URL), mas o teste documenta o
        // comportamento esperado: texto que não bate o padrão "scheme://user:pass@" é devolvido
        // intacto -- ou seja, quem loga API_SECRET_KEY/JWT deve fazer isso de outro jeito
        // (nunca passando por aqui como se fosse seguro). Este teste é uma guarda de regressão
        // para não presumirmos cobertura que esta função não oferece.
        var jwtLike = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig";
        Assert.Equal(jwtLike, DatabasePreflight.SanitizeForDisplay(jwtLike));
    }

    [Fact]
    public void ReadKeyFromDotEnvFile_LeValorSimples()
    {
        var tmp = Path.GetTempFileName();
        try
        {
            File.WriteAllText(tmp, "DATABASE_URL=postgresql://a:b@localhost:5432/x\nOUTRA=coisa\n");
            var value = DatabasePreflight.ReadKeyFromDotEnvFile(tmp, "DATABASE_URL");
            Assert.Equal("postgresql://a:b@localhost:5432/x", value);
        }
        finally { File.Delete(tmp); }
    }

    [Fact]
    public void ReadKeyFromDotEnvFile_IgnoraComentariosELinhasEmBranco()
    {
        var tmp = Path.GetTempFileName();
        try
        {
            File.WriteAllText(tmp, "# comentário\n\n   \nDATABASE_URL=postgresql://x\n");
            Assert.Equal("postgresql://x", DatabasePreflight.ReadKeyFromDotEnvFile(tmp, "DATABASE_URL"));
        }
        finally { File.Delete(tmp); }
    }

    [Fact]
    public void ReadKeyFromDotEnvFile_RemoveAspasAoRedorDoValor()
    {
        var tmp = Path.GetTempFileName();
        try
        {
            File.WriteAllText(tmp, "DATABASE_URL=\"postgresql://x\"\n");
            Assert.Equal("postgresql://x", DatabasePreflight.ReadKeyFromDotEnvFile(tmp, "DATABASE_URL"));
        }
        finally { File.Delete(tmp); }
    }

    [Fact]
    public void ReadKeyFromDotEnvFile_RetornaNullSeArquivoNaoExiste()
    {
        Assert.Null(DatabasePreflight.ReadKeyFromDotEnvFile("/caminho/que/nao/existe/.env", "DATABASE_URL"));
    }

    [Fact]
    public void ReadKeyFromDotEnvFile_RetornaNullSeChaveNaoEstaNoArquivo()
    {
        var tmp = Path.GetTempFileName();
        try
        {
            File.WriteAllText(tmp, "OUTRA_CHAVE=valor\n");
            Assert.Null(DatabasePreflight.ReadKeyFromDotEnvFile(tmp, "DATABASE_URL"));
        }
        finally { File.Delete(tmp); }
    }

    [Fact]
    public void ReadDatabaseUrl_PriorizaVariavelDeAmbienteSobreArquivos()
    {
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-preflight-test-");
        try
        {
            var apiDir = Directory.CreateDirectory(Path.Combine(tmpDir.FullName, "apps", "api")).FullName;
            File.WriteAllText(Path.Combine(apiDir, ".env"), "DATABASE_URL=postgresql://do-arquivo\n");

            Environment.SetEnvironmentVariable("DATABASE_URL", "postgresql://da-variavel-de-ambiente");
            try
            {
                var url = DatabasePreflight.ReadDatabaseUrl(apiDir, tmpDir.FullName);
                Assert.Equal("postgresql://da-variavel-de-ambiente", url);
            }
            finally
            {
                Environment.SetEnvironmentVariable("DATABASE_URL", null);
            }
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void ReadDatabaseUrl_UsaArquivoApiEnvQuandoVariavelDeAmbienteAusente()
    {
        Environment.SetEnvironmentVariable("DATABASE_URL", null);
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-preflight-test-");
        try
        {
            var apiDir = Directory.CreateDirectory(Path.Combine(tmpDir.FullName, "apps", "api")).FullName;
            File.WriteAllText(Path.Combine(apiDir, ".env"), "DATABASE_URL=postgresql://do-arquivo-api\n");

            var url = DatabasePreflight.ReadDatabaseUrl(apiDir, tmpDir.FullName);
            Assert.Equal("postgresql://do-arquivo-api", url);
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void ReadDatabaseUrl_RetornaNullQuandoNaoConfiguradoEmNenhumLugar()
    {
        Environment.SetEnvironmentVariable("DATABASE_URL", null);
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-preflight-test-");
        try
        {
            var apiDir = Directory.CreateDirectory(Path.Combine(tmpDir.FullName, "apps", "api")).FullName;
            Assert.Null(DatabasePreflight.ReadDatabaseUrl(apiDir, tmpDir.FullName));
        }
        finally { tmpDir.Delete(recursive: true); }
    }

    [Fact]
    public void MissingConfiguration_NuncaLancaEExplicaClaramenteOQueFazer()
    {
        var outcome = DatabasePreflight.MissingConfiguration("/repo/apps/api", "/repo");
        Assert.False(outcome.Ok);
        Assert.NotNull(outcome.GuidanceMessage);
        Assert.Contains("DATABASE_URL", outcome.GuidanceMessage);
        Assert.Contains("NUNCA cria ou configura", outcome.GuidanceMessage);
    }

    private static string PythonExecutable => OperatingSystem.IsWindows() ? "python" : "python3";

    /// <summary>
    /// Cria uma pasta temporária com scripts/gate_preflight_check.py FALSO (mesma interface e
    /// mesmo formato de saída do real: um objeto JSON em stdout, exit code 0 se aprovado, 1 se
    /// falhou) -- exercita DatabasePreflight.Run() de ponta a ponta (subprocess real, parsing
    /// real do JSON real produzido por ele), sem depender de um PostgreSQL de verdade.
    /// </summary>
    private static string CreateFakeApiDirWithPreflightScript(string pythonBody)
    {
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-preflight-fake-api-");
        var scriptsDir = Directory.CreateDirectory(Path.Combine(tmpDir.FullName, "scripts"));
        File.WriteAllText(Path.Combine(scriptsDir.FullName, "gate_preflight_check.py"), pythonBody);
        return tmpDir.FullName;
    }

    [Fact]
    public void Run_RelatorioAprovadoRealEhParseadoCorretamente()
    {
        var apiDir = CreateFakeApiDirWithPreflightScript(
            "import json, sys\n" +
            "print(json.dumps({'steps':[{'step':'database_url_nao_e_sqlite','ok':True,'detail':'ok'}]," +
            "'result':'APPROVED','failure_reason':None,'overall_ok':True}))\n" +
            "sys.exit(0)\n");
        try
        {
            var outcome = DatabasePreflight.Run(PythonExecutable, apiDir, "postgresql://fake:fake@localhost:5432/fake");
            Assert.True(outcome.Ok);
            Assert.Single(outcome.Steps);
            Assert.True(outcome.Steps[0].Ok);
            Assert.Null(outcome.FailureReason);
        }
        finally { Directory.Delete(apiDir, recursive: true); }
    }

    [Fact]
    public void Run_RelatorioComFalhaRealEhParseadoComFailureReasonSanitizado()
    {
        var apiDir = CreateFakeApiDirWithPreflightScript(
            "import json, sys\n" +
            "detail = 'Falha ao conectar em postgresql://user:segredo123@host:5432/db'\n" +
            "print(json.dumps({'steps':[{'step':'conexao_e_autenticacao_reais','ok':False,'detail':detail}]," +
            "'result':'FAILED','failure_reason':'conexao_e_autenticacao_reais: ' + detail,'overall_ok':False}))\n" +
            "sys.exit(1)\n");
        try
        {
            var outcome = DatabasePreflight.Run(PythonExecutable, apiDir, "postgresql://user:segredo123@host:5432/db");
            Assert.False(outcome.Ok);
            Assert.NotNull(outcome.FailureReason);
            Assert.DoesNotContain("segredo123", outcome.FailureReason);
            Assert.Contains("***", outcome.FailureReason);
            Assert.False(outcome.Steps[0].Ok);
            Assert.DoesNotContain("segredo123", outcome.Steps[0].Detail);
        }
        finally { Directory.Delete(apiDir, recursive: true); }
    }

    [Fact]
    public void Run_SaidaNaoJsonResultaEmFalhaTratadaSemLancar()
    {
        var apiDir = CreateFakeApiDirWithPreflightScript("print('isto nao e json')\n");
        try
        {
            var outcome = DatabasePreflight.Run(PythonExecutable, apiDir, "postgresql://fake");
            Assert.False(outcome.Ok);
            Assert.NotNull(outcome.GuidanceMessage);
        }
        finally { Directory.Delete(apiDir, recursive: true); }
    }
}
