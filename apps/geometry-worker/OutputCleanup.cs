// Limpeza de artefatos parciais em caso de falha (Incremento 2.1.1, item 3: "cleanup de
// arquivos parciais"). Extraído de Program.cs para ser testável isoladamente (sem depender do
// runtime nativo do PicoGK) depois que uma execução real nesta sessão revelou um bug real:
// a implementação original (Directory.GetFiles + delete de TUDO no output_dir) apagava também
// o próprio job.json de entrada, porque o chamador em produção (worker_client.py,
// `job_json_path = output_dir / "job.json"`) grava o envelope de entrada DENTRO do mesmo
// output_dir usado para os artefatos de saída. O efeito prático: depois de uma falha, o
// diretório de evidência da execução perdia a receita de entrada que efetivamente rodou,
// prejudicando a auditoria pós-morte de falhas -- exatamente o tipo de defeito que este
// incremento corretivo existe para encontrar e corrigir, não simular.
namespace BioMatCadGeometryWorker;

public static class OutputCleanup
{
    // Nomes de arquivo que NUNCA devem ser removidos pela limpeza de artefatos parciais, por
    // serem entrada (não saída) da execução. Comparação por nome de arquivo (case-sensitive,
    // como o restante do projeto -- Linux/Windows tratam isso de formas diferentes, mas o nome
    // "job.json" é sempre gravado em minúsculas pelo chamador).
    public static readonly IReadOnlySet<string> PreservedFileNames = new HashSet<string> { "job.json" };

    /// <summary>
    /// Remove, com melhor esforço, todos os arquivos de <paramref name="outputDir"/> EXCETO os
    /// listados em <see cref="PreservedFileNames"/>. Nunca lança exceção (falha de limpeza não
    /// deve mascarar o erro original que motivou a limpeza) e nunca falha se o diretório não
    /// existir.
    /// </summary>
    /// <returns>Os caminhos efetivamente removidos (para fins de teste/log; melhor esforço).</returns>
    public static List<string> CleanupPartialOutputs(string outputDir)
    {
        var removed = new List<string>();
        try
        {
            if (!Directory.Exists(outputDir))
                return removed;

            foreach (var file in Directory.GetFiles(outputDir))
            {
                string fileName = Path.GetFileName(file);
                if (PreservedFileNames.Contains(fileName))
                    continue;

                try
                {
                    File.Delete(file);
                    removed.Add(file);
                }
                catch
                {
                    // melhor esforço -- não mascarar o erro original que motivou a limpeza.
                }
            }
        }
        catch
        {
            // melhor esforço.
        }
        return removed;
    }
}
