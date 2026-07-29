using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class RepositoryLocatorTests
{
    private static void CreateMarkers(string root)
    {
        Directory.CreateDirectory(Path.Combine(root, "apps", "api"));
        Directory.CreateDirectory(Path.Combine(root, "apps", "web"));
        Directory.CreateDirectory(Path.Combine(root, "apps", "geometry-worker"));
        File.WriteAllText(Path.Combine(root, "apps", "api", "pyproject.toml"), "[project]\nname=\"x\"\n");
        File.WriteAllText(Path.Combine(root, "apps", "web", "package.json"), "{}");
        File.WriteAllText(Path.Combine(root, "apps", "geometry-worker", "BioMatCadGeometryWorker.csproj"), "<Project />");
    }

    [Fact]
    public void FindRepoRoot_QuandoIniciaExatamenteNaRaiz_RetornaAPropriaRaiz()
    {
        var root = Directory.CreateTempSubdirectory("biomatcad-repo-").FullName;
        try
        {
            CreateMarkers(root);
            var found = RepositoryLocator.FindRepoRoot(root);
            Assert.Equal(Path.GetFullPath(root), found);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void FindRepoRoot_QuandoIniciaEmSubdiretorioProfundo_SobeAteEncontrarARaiz()
    {
        var root = Directory.CreateTempSubdirectory("biomatcad-repo-").FullName;
        try
        {
            CreateMarkers(root);
            var deepStart = Path.Combine(root, "dist", "windows-launcher");
            Directory.CreateDirectory(deepStart);

            var found = RepositoryLocator.FindRepoRoot(deepStart);
            Assert.Equal(Path.GetFullPath(root), found);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public void FindRepoRoot_ComEspacosNoCaminho_FuncionaNormalmente()
    {
        // Item explicitamente pedido: "caminhos com espaços". Ex.: em máquinas Windows reais,
        // é comum o repositório estar sob "C:\Users\Fulano de Tal\Documents\biomatcad-nexus".
        var parent = Directory.CreateTempSubdirectory("biomatcad launcher tests ").FullName;
        var root = Path.Combine(parent, "Meu Repositorio BioMatCAD Nexus");
        Directory.CreateDirectory(root);
        try
        {
            CreateMarkers(root);
            var deepStart = Path.Combine(root, "dist", "windows launcher build");
            Directory.CreateDirectory(deepStart);

            var found = RepositoryLocator.FindRepoRoot(deepStart);
            Assert.Equal(Path.GetFullPath(root), found);
            Assert.Contains(" ", found);
        }
        finally
        {
            Directory.Delete(parent, recursive: true);
        }
    }

    [Fact]
    public void FindRepoRoot_QuandoNenhumAncestralTemOsMarcadores_RetornaNull()
    {
        var isolated = Directory.CreateTempSubdirectory("biomatcad-not-a-repo-").FullName;
        try
        {
            // Diretório temporário isolado (ex.: /tmp/xxxx) não tem nenhum ancestral com os
            // marcadores do repositório -- deve retornar null, nunca lançar exceção nem
            // "adivinhar" uma raiz errada.
            var found = RepositoryLocator.FindRepoRoot(isolated);
            Assert.Null(found);
        }
        finally
        {
            Directory.Delete(isolated, recursive: true);
        }
    }

    [Fact]
    public void FindRepoRoot_NaRaizRealDoRepositorioClonado_Encontra()
    {
        // Teste de integração real: a partir deste próprio arquivo de teste, subindo os
        // diretórios reais do repositório clonado, RepositoryLocator deve encontrar a raiz real
        // (não um diretório sintético) -- prova que os marcadores escolhidos batem com a
        // estrutura real do projeto, não apenas com fixtures artificiais.
        var thisFileDir = AppContext.BaseDirectory;
        var found = RepositoryLocator.FindRepoRoot(thisFileDir);
        Assert.NotNull(found);
        Assert.True(File.Exists(Path.Combine(found!, "apps", "api", "pyproject.toml")));
        Assert.True(File.Exists(Path.Combine(found!, "apps", "web", "package.json")));
    }
}
