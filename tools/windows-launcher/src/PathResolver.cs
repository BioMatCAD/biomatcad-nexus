namespace BioMatCAD.Launcher;

/// <summary>
/// Resolução de comandos via PATH implementada manualmente (em vez de depender da resolução
/// implícita do Win32 CreateProcess, que é inconsistente para arquivos .cmd/.bat no Windows --
/// ver comentário em <see cref="ResolveNpmCandidateNames"/>). Isso permite (a) sempre passar um
/// caminho absoluto e explícito para <c>ProcessStartInfo.FileName</c>, nunca dependendo de
/// UseShellExecute nem de um shell intermediário (defesa central contra command injection --
/// ver README.md, seção "Segurança"), e (b) testar a lógica de resolução inteira com
/// diretórios/arquivos reais em pastas temporárias, sem tocar o PATH real da máquina.
/// </summary>
public static class PathResolver
{
    /// <summary>
    /// Procura <paramref name="commandName"/> (sem extensão) em cada diretório de
    /// <paramref name="pathEnvValue"/> (separados por <see cref="Path.PathSeparator"/>),
    /// tentando, em ordem, cada extensão de <paramref name="pathExtValue"/> quando
    /// <paramref name="isWindows"/> é verdadeiro (imitando a resolução real do PATHEXT do
    /// Windows), ou o nome exato (sem extensão) quando não é Windows. Retorna o caminho
    /// absoluto completo do primeiro arquivo encontrado, ou null se nenhum existir.
    /// </summary>
    public static string? WhichCommand(
        string commandName,
        string? pathEnvValue,
        string? pathExtValue,
        bool isWindows)
    {
        if (string.IsNullOrWhiteSpace(pathEnvValue))
        {
            return null;
        }

        var directories = pathEnvValue.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries);

        // Se o nome candidato JÁ tem uma extensão explícita (ex.: "npm.cmd"), procura o nome
        // exato, sem tentar acrescentar sufixos do PATHEXT em cima dele (o que produziria
        // absurdos como "npm.cmd.EXE"). Só aplica a expansão do PATHEXT quando o nome é "nu"
        // (sem extensão) E estamos em Windows -- em outras plataformas, sempre nome exato.
        var hasExplicitExtension = Path.HasExtension(commandName);
        var candidateSuffixes = (isWindows && !hasExplicitExtension)
            ? ParsePathExt(pathExtValue)
            : [string.Empty];

        foreach (var dir in directories)
        {
            foreach (var suffix in candidateSuffixes)
            {
                string candidatePath;
                try
                {
                    candidatePath = Path.Combine(dir, commandName + suffix);
                }
                catch (ArgumentException)
                {
                    // Diretório malformado no PATH (caracteres inválidos) -- ignora e segue
                    // para o próximo, nunca lança para fora daqui.
                    continue;
                }

                if (File.Exists(candidatePath))
                {
                    return Path.GetFullPath(candidatePath);
                }

                // PATHEXT costuma listar sufixos em MAIÚSCULAS (".EXE", ".CMD", ...) por
                // convenção, mas os arquivos instalados de verdade normalmente têm extensão em
                // minúsculas ("npm.cmd", "python.exe"). No NTFS isso nunca importa (sistema de
                // arquivos insensível a caixa), mas para que esta lógica de resolução seja
                // corretamente testável (e correta) também em sistemas de arquivos sensíveis a
                // caixa, tentamos explicitamente a variante em minúsculas do sufixo antes de
                // desistir deste diretório.
                if (suffix.Length > 0)
                {
                    var lowerSuffix = suffix.ToLowerInvariant();
                    if (lowerSuffix != suffix)
                    {
                        var lowerCandidatePath = Path.Combine(dir, commandName + lowerSuffix);
                        if (File.Exists(lowerCandidatePath))
                        {
                            return Path.GetFullPath(lowerCandidatePath);
                        }
                    }
                }
            }
        }

        return null;
    }

    private static string[] ParsePathExt(string? pathExtValue)
    {
        if (string.IsNullOrWhiteSpace(pathExtValue))
        {
            // PATHEXT padrão de um Windows limpo, caso a variável não esteja definida.
            return [".COM", ".EXE", ".BAT", ".CMD"];
        }
        return pathExtValue.Split(';', StringSplitOptions.RemoveEmptyEntries);
    }

    /// <summary>
    /// Nomes candidatos, em ordem de preferência, para o executável do npm. No Windows, o
    /// instalador do Node.js coloca <c>npm.cmd</c> (um script de lote) no PATH -- NÃO um
    /// <c>npm.exe</c> nativo. O Win32 CreateProcess (usado por
    /// <c>Process.Start</c> com <c>UseShellExecute=false</c>) não aplica a mesma resolução de
    /// PATHEXT que o <c>cmd.exe</c> aplica interativamente -- invocar "npm" diretamente nessa
    /// configuração falha de verdade no Windows com "arquivo não encontrado", um problema
    /// conhecido e documentado do .NET. <see cref="WhichCommand"/> já resolve a extensão
    /// correta via PATHEXT sozinho, então aqui basta pedir "npm" e deixar o PATHEXT (tentado em
    /// ordem: .COM, .EXE, .BAT, .CMD) encontrar "npm.cmd" primeiro que teria menor prioridade
    /// nessa ordem -- por isso listamos "npm.cmd" TAMBÉM como candidato explícito de maior
    /// prioridade, para garantir que ele seja encontrado antes de qualquer outra coisa
    /// (inclusive antes de um eventual "npm.ps1").
    /// </summary>
    public static string[] ResolveNpmCandidateNames(bool isWindows) => isWindows ? ["npm.cmd", "npm"] : ["npm"];

    public static string[] ResolvePythonCandidateNames(bool isWindows) => isWindows ? ["python", "py"] : ["python3", "python"];

    public static string ResolveNodeCandidateName(bool isWindows) => "node";

    public static string ResolveDotnetCandidateName(bool isWindows) => "dotnet";
}
