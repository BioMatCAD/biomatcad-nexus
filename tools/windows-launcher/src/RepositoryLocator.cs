namespace BioMatCAD.Launcher;

/// <summary>
/// Localiza a raiz do repositório BioMatCAD Nexus a partir de um diretório de partida
/// (normalmente o diretório do próprio executável do launcher, que pode estar em
/// dist/windows-launcher/ ou em qualquer outro lugar dentro -- ou fora -- da árvore do
/// repositório). Sobe diretório por diretório até encontrar todos os marcadores esperados, ou
/// retorna null se nenhum ancestral (nem o próprio diretório de partida) contiver a estrutura
/// esperada.
///
/// Puramente baseado em System.IO real (nenhuma abstração de sistema de arquivos falsa) --
/// os testes criam árvores de diretórios reais em pastas temporárias, incluindo casos com
/// espaços no caminho (item explicitamente pedido nos testes).
/// </summary>
public static class RepositoryLocator
{
    /// <summary>
    /// Marcadores mínimos e suficientes para identificar a raiz real do repositório: as duas
    /// aplicações principais (apps/api com pyproject.toml, apps/web com package.json). Não
    /// exige .git (o repositório pode ter sido extraído de um bundle/zip sem histórico Git,
    /// como já aconteceu nesta sessão com os pacotes de entrega v2.2/v2.2.1).
    /// </summary>
    private static readonly string[] RequiredRelativeFiles =
    [
        Path.Combine("apps", "api", "pyproject.toml"),
        Path.Combine("apps", "web", "package.json"),
        Path.Combine("apps", "geometry-worker", "BioMatCadGeometryWorker.csproj"),
    ];

    public static bool LooksLikeRepoRoot(string candidateDirectory)
    {
        if (!Directory.Exists(candidateDirectory))
        {
            return false;
        }

        foreach (var relative in RequiredRelativeFiles)
        {
            if (!File.Exists(Path.Combine(candidateDirectory, relative)))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Sobe a árvore de diretórios a partir de <paramref name="startDirectory"/> (inclusive)
    /// até a raiz do sistema de arquivos, retornando o primeiro ancestral que satisfaça
    /// <see cref="LooksLikeRepoRoot"/>, ou null se nenhum satisfizer.
    /// </summary>
    public static string? FindRepoRoot(string startDirectory)
    {
        var current = new DirectoryInfo(Path.GetFullPath(startDirectory));
        while (current is not null)
        {
            if (LooksLikeRepoRoot(current.FullName))
            {
                return current.FullName;
            }
            current = current.Parent;
        }
        return null;
    }
}
