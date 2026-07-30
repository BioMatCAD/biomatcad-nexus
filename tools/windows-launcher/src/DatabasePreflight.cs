using System.Text.Json;
using System.Text.RegularExpressions;

namespace BioMatCAD.Launcher;

public sealed record PreflightStepDetail(string Step, bool Ok, string Detail);

public sealed record PreflightOutcome(
    bool Ok,
    string? FailureReason,
    IReadOnlyList<PreflightStepDetail> Steps,
    string? GuidanceMessage);

/// <summary>
/// Wrapper fino sobre apps/api/scripts/gate_preflight_check.py -- Incremento 2.2, seção 2 ("1.
/// Banco": verificar driver, verificar porta, autenticar sem mostrar senha, SELECT 1, recusar
/// SQLite). Deliberadamente NÃO reimplementa essa lógica em C#: o script Python já é a mesma
/// peça usada e validada de verdade no gate final do Incremento 2.1.1 (ver TEST_EVIDENCE.md
/// §16) -- reusar garante que o launcher e o gate final concordam byte a byte sobre o que
/// "banco pronto" significa, e evita duas implementações divergentes do mesmo contrato.
///
/// Este módulo NUNCA cria, altera ou reseta um usuário/senha do PostgreSQL -- só lê
/// DATABASE_URL e tenta conectar. Se a conexão falhar, o retorno é sempre uma falha relatada
/// ao usuário, nunca uma tentativa silenciosa de "corrigir" o banco.
/// </summary>
public static class DatabasePreflight
{
    // Mascara qualquer "usuario:senha@" dentro de uma URL do tipo scheme://user:pass@host...
    // -- defesa em profundidade para exibição: mesmo que uma mensagem de erro do driver acabe
    // ecoando a DATABASE_URL crua (não deveria, mas drivers de terceiros variam), nunca
    // deixamos a senha visível no console do launcher.
    private static readonly Regex CredentialsInUrlPattern = new(
        @"(?<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?<user>[^:/@\s]+):(?<password>[^@/\s]+)@",
        RegexOptions.Compiled);

    public static string SanitizeForDisplay(string text) =>
        CredentialsInUrlPattern.Replace(text, "${scheme}${user}:***@");

    /// <summary>
    /// Lê DATABASE_URL de (em ordem de precedência): variável de ambiente do processo atual;
    /// apps/api/.env; .env na raiz do repositório. Nunca grava, nunca modifica nenhum desses
    /// arquivos -- apenas leitura.
    /// </summary>
    public static string? ReadDatabaseUrl(string apiDir, string repoRoot)
    {
        var fromEnv = Environment.GetEnvironmentVariable("DATABASE_URL");
        if (!string.IsNullOrWhiteSpace(fromEnv))
        {
            return fromEnv;
        }

        foreach (var envFile in new[] { Path.Combine(apiDir, ".env"), Path.Combine(repoRoot, ".env") })
        {
            var fromFile = ReadKeyFromDotEnvFile(envFile, "DATABASE_URL");
            if (!string.IsNullOrWhiteSpace(fromFile))
            {
                return fromFile;
            }
        }

        return null;
    }

    /// <summary>
    /// Parser minimalista de arquivo .env (KEY=VALUE por linha, "#" inicia comentário, aspas
    /// simples/duplas ao redor do valor são removidas) -- suficiente para o único propósito
    /// aqui (ler DATABASE_URL), sem trazer uma dependência externa de parsing de dotenv.
    /// </summary>
    public static string? ReadKeyFromDotEnvFile(string path, string key)
    {
        if (!File.Exists(path))
        {
            return null;
        }
        foreach (var rawLine in File.ReadAllLines(path))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith('#'))
            {
                continue;
            }
            var eq = line.IndexOf('=');
            if (eq <= 0)
            {
                continue;
            }
            var lineKey = line[..eq].Trim();
            if (!string.Equals(lineKey, key, StringComparison.Ordinal))
            {
                continue;
            }
            var value = line[(eq + 1)..].Trim();
            if (value.Length >= 2 && ((value[0] == '"' && value[^1] == '"') || (value[0] == '\'' && value[^1] == '\'')))
            {
                value = value[1..^1];
            }
            return value;
        }
        return null;
    }

    public static PreflightOutcome MissingConfiguration(string apiDir, string repoRoot) => new(
        Ok: false,
        FailureReason: "DATABASE_URL não configurada.",
        Steps: [],
        GuidanceMessage:
            "Nenhuma DATABASE_URL foi encontrada (nem na variável de ambiente do processo, nem " +
            $"em {Path.Combine(apiDir, ".env")}, nem em {Path.Combine(repoRoot, ".env")}). " +
            "Este launcher NUNCA cria ou configura um banco PostgreSQL por você -- crie um " +
            $"arquivo .env em {apiDir} com uma linha DATABASE_URL=postgresql+psycopg://" +
            "usuario:senha@host:5432/nome_do_banco apontando para um PostgreSQL real já em " +
            "execução. Veja docs/examples/WINDOWS_EXECUTION_KIT.md para o passo a passo.");

    /// <summary>
    /// Executa o preflight real (subprocess Python, sem shell, ArgumentList) e traduz o
    /// relatório JSON dele para um <see cref="PreflightOutcome"/>. Nunca lança para "banco
    /// indisponível" -- isso é um resultado (Ok=false) esperado e tratado, não uma exceção.
    /// </summary>
    public static PreflightOutcome Run(string venvPythonPath, string apiDir, string databaseUrl)
    {
        var (exitCode, output) = ProcessSupervisor.RunToCompletion(
            venvPythonPath,
            ["scripts/gate_preflight_check.py", "--database-url", databaseUrl],
            apiDir,
            timeout: TimeSpan.FromSeconds(30));

        var sanitizedOutput = SanitizeForDisplay(output);

        JsonDocument doc;
        try
        {
            // O script imprime exatamente um objeto JSON em stdout (mais possivelmente ruído
            // de stderr misturado por RunToCompletion) -- localizamos o primeiro '{' até o
            // último '}' para tolerar esse ruído sem depender de stdout/stderr separados aqui.
            var start = sanitizedOutput.IndexOf('{');
            var end = sanitizedOutput.LastIndexOf('}');
            if (start < 0 || end < start)
            {
                throw new JsonException("Nenhum objeto JSON encontrado na saída do preflight.");
            }
            doc = JsonDocument.Parse(sanitizedOutput[start..(end + 1)]);
        }
        catch (JsonException)
        {
            return new PreflightOutcome(
                Ok: false,
                FailureReason: "Não foi possível interpretar a saída do preflight.",
                Steps: [],
                GuidanceMessage: $"Saída bruta (sanitizada) do preflight: {Truncate(sanitizedOutput)}");
        }

        var root = doc.RootElement;
        var steps = new List<PreflightStepDetail>();
        if (root.TryGetProperty("steps", out var stepsElement) && stepsElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var stepEl in stepsElement.EnumerateArray())
            {
                var name = stepEl.TryGetProperty("step", out var n) ? n.GetString() ?? "" : "";
                var ok = stepEl.TryGetProperty("ok", out var o) && o.ValueKind == JsonValueKind.True;
                var detail = stepEl.TryGetProperty("detail", out var d) ? d.GetString() ?? "" : "";
                steps.Add(new PreflightStepDetail(name, ok, SanitizeForDisplay(detail)));
            }
        }

        var overallOk = exitCode == 0
            && root.TryGetProperty("overall_ok", out var okEl)
            && okEl.ValueKind == JsonValueKind.True;

        string? failureReason = null;
        if (!overallOk && root.TryGetProperty("failure_reason", out var frEl) && frEl.ValueKind == JsonValueKind.String)
        {
            failureReason = SanitizeForDisplay(frEl.GetString() ?? "");
        }

        return new PreflightOutcome(overallOk, failureReason, steps, GuidanceMessage: null);
    }

    private static string Truncate(string s, int max = 1500) => s.Length <= max ? s : s[..max] + "... [truncado]";
}
