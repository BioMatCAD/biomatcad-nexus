// Testes de regressão para o bug real encontrado nesta sessão: uma tentativa real de execução
// do worker (build + dotnet run contra uma golden recipe, no sandbox Linux, reproduzindo a
// falha esperada de runtime nativo do PicoGK ausente) revelou que a limpeza de artefatos
// parciais apagava também o job.json de entrada, porque worker_client.py grava
// `output_dir / "job.json"` -- ou seja, o job.json vive DENTRO do mesmo diretório que a
// limpeza-em-caso-de-falha varre e apaga por completo.
using BioMatCadGeometryWorker;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class OutputCleanupTests
{
    private static string CreateTempDirWithFiles(params string[] fileNames)
    {
        string dir = Path.Combine(Path.GetTempPath(), "biomatcad-cleanup-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        foreach (var name in fileNames)
        {
            File.WriteAllText(Path.Combine(dir, name), "conteudo de teste");
        }
        return dir;
    }

    [Fact]
    public void CleanupPartialOutputs_PreservesJobJson_ButRemovesOtherFiles()
    {
        // Regressão direta do bug encontrado: job.json (entrada) não pode ser apagado, mas
        // artefatos de saída parciais (ex.: um scaffold.stl truncado de uma tentativa que
        // falhou) devem ser removidos.
        string dir = CreateTempDirWithFiles("job.json", "scaffold.stl", "stdout.json");
        try
        {
            var removed = OutputCleanup.CleanupPartialOutputs(dir);

            Assert.True(File.Exists(Path.Combine(dir, "job.json")), "job.json (entrada) deveria ter sido preservado.");
            Assert.False(File.Exists(Path.Combine(dir, "scaffold.stl")), "scaffold.stl (saída parcial) deveria ter sido removido.");
            Assert.False(File.Exists(Path.Combine(dir, "stdout.json")), "stdout.json deveria ter sido removido.");
            Assert.Equal(2, removed.Count);
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void CleanupPartialOutputs_OnDirectoryWithOnlyJobJson_RemovesNothing()
    {
        string dir = CreateTempDirWithFiles("job.json");
        try
        {
            var removed = OutputCleanup.CleanupPartialOutputs(dir);
            Assert.Empty(removed);
            Assert.True(File.Exists(Path.Combine(dir, "job.json")));
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void CleanupPartialOutputs_OnNonExistentDirectory_DoesNotThrowAndReturnsEmpty()
    {
        string dir = Path.Combine(Path.GetTempPath(), "biomatcad-cleanup-test-nonexistent-" + Guid.NewGuid().ToString("N"));
        var removed = OutputCleanup.CleanupPartialOutputs(dir);
        Assert.Empty(removed);
    }

    [Fact]
    public void CleanupPartialOutputs_OnEmptyDirectory_RemovesNothing()
    {
        string dir = Path.Combine(Path.GetTempPath(), "biomatcad-cleanup-test-empty-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var removed = OutputCleanup.CleanupPartialOutputs(dir);
            Assert.Empty(removed);
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }
}
