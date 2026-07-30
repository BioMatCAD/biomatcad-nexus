namespace BioMatCAD.Launcher;

public sealed record MigrationResult(bool Ok, int ExitCode, string SanitizedOutput);

/// <summary>
/// Executa "alembic upgrade head" a partir do venv da API -- Incremento 2.2, seção 2 ("2.
/// Migrações"). Ao contrário do Run-FinalGate.ps1 (PowerShell), aqui NÃO existe o bug de
/// "INFO em stderr virar NativeCommandError": Process.StandardError.ReadToEnd() em C# é só uma
/// string, nunca um objeto de erro que aborta o processo por causa de $ErrorActionPreference.
/// O único critério de sucesso/falha é o código de saída do próprio Alembic -- exatamente o
/// que a seção 2 pede ("tratar INFO em stderr corretamente; abortar em exit code diferente de
/// zero"). UTF-8 já é garantido pelo ProcessSupervisor (StandardOutputEncoding/
/// StandardErrorEncoding + PYTHONUTF8/PYTHONIOENCODING).
/// </summary>
public static class MigrationRunner
{
    public static MigrationResult Run(string venvPythonPath, string apiDir, TimeSpan? timeout = null)
    {
        var (exitCode, output) = ProcessSupervisor.RunToCompletion(
            venvPythonPath,
            ["-m", "alembic", "upgrade", "head"],
            apiDir,
            timeout: timeout ?? TimeSpan.FromMinutes(5));

        return new MigrationResult(exitCode == 0, exitCode, DatabasePreflight.SanitizeForDisplay(output));
    }
}
