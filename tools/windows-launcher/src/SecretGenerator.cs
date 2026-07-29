using System.Security.Cryptography;

namespace BioMatCAD.Launcher;

/// <summary>
/// Gera um API_SECRET_KEY efêmero e criptograficamente seguro para a sessão do launcher.
/// O segredo NUNCA é gravado em disco, NUNCA é logado e NUNCA é impresso no console -- é passado
/// diretamente como variável de ambiente do processo filho da API (ver ProcessSupervisor), e
/// existe apenas na memória do processo do launcher e do processo filho enquanto ambos vivem.
/// </summary>
public static class SecretGenerator
{
    /// <summary>
    /// Gera <paramref name="byteLength"/> bytes aleatórios via RandomNumberGenerator (CSPRNG do
    /// SO, não System.Random) e retorna como string hexadecimal (não Base64, para evitar
    /// caracteres que exijam escaping em variáveis de ambiente/linha de comando no Windows).
    /// </summary>
    public static string GenerateHex(int byteLength = 32)
    {
        if (byteLength < 16)
        {
            throw new ArgumentOutOfRangeException(nameof(byteLength), "Segredo precisa ter pelo menos 16 bytes (128 bits) de entropia.");
        }
        var bytes = RandomNumberGenerator.GetBytes(byteLength);
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
