using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class MigrationRunnerTests
{
    private static string PythonExecutable => OperatingSystem.IsWindows() ? "python" : "python3";

    private static string CreateFakeApiDirWithAlembicStub(string moduleBody)
    {
        // Cria uma pasta que faz "python -m alembic upgrade head" executar nosso próprio
        // código: um pacote local chamado "alembic" no mesmo diretório (Python prioriza um
        // pacote local sobre um instalado, quando executado com esse diretório como cwd e "."
        // implicitamente no sys.path) -- assim testamos MigrationRunner.Run() de ponta a ponta
        // (subprocess real) sem precisar de um Postgres real nem do Alembic real instalado.
        var tmpDir = Directory.CreateTempSubdirectory("biomatcad-migration-fake-api-");
        var alembicPkgDir = Directory.CreateDirectory(Path.Combine(tmpDir.FullName, "alembic"));
        File.WriteAllText(Path.Combine(alembicPkgDir.FullName, "__init__.py"), "");
        File.WriteAllText(Path.Combine(alembicPkgDir.FullName, "__main__.py"), moduleBody);
        return tmpDir.FullName;
    }

    [Fact]
    public void Run_ExitCodeZero_EhConsideradoSucessoMesmoComSaidaEmStderr()
    {
        // Regressão direta do bug que motivou a correção do Run-FinalGate.ps1 no Incremento
        // 2.1.1: linhas INFO do Alembic em stderr, com exit code 0, NUNCA devem ser tratadas
        // como falha. Em C# isso é trivial (StandardError.ReadToEnd() é só uma string), mas
        // este teste documenta e trava o comportamento esperado explicitamente.
        var apiDir = CreateFakeApiDirWithAlembicStub(
            "import sys\n" +
            "print('INFO [alembic.runtime.migration] Running upgrade -> head', file=sys.stderr)\n" +
            "sys.exit(0)\n");
        try
        {
            var result = MigrationRunner.Run(PythonExecutable, apiDir);
            Assert.True(result.Ok);
            Assert.Equal(0, result.ExitCode);
        }
        finally { Directory.Delete(apiDir, recursive: true); }
    }

    [Fact]
    public void Run_ExitCodeDiferenteDeZero_EhConsideradoFalha()
    {
        var apiDir = CreateFakeApiDirWithAlembicStub(
            "import sys\n" +
            "print('ERROR: could not connect to server', file=sys.stderr)\n" +
            "sys.exit(1)\n");
        try
        {
            var result = MigrationRunner.Run(PythonExecutable, apiDir);
            Assert.False(result.Ok);
            Assert.Equal(1, result.ExitCode);
        }
        finally { Directory.Delete(apiDir, recursive: true); }
    }

    [Fact]
    public void Run_SanitizaDatabaseUrlSeEcoadaNaSaida()
    {
        var apiDir = CreateFakeApiDirWithAlembicStub(
            "import sys\n" +
            "print('conectando em postgresql://user:senha987@host:5432/db', file=sys.stderr)\n" +
            "sys.exit(1)\n");
        try
        {
            var result = MigrationRunner.Run(PythonExecutable, apiDir);
            Assert.DoesNotContain("senha987", result.SanitizedOutput);
        }
        finally { Directory.Delete(apiDir, recursive: true); }
    }
}
