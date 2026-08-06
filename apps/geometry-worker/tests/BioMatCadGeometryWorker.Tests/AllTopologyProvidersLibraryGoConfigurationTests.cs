// Teste de "guarda de configuração" GENÉRICO para TODA chamada real a PicoGK.Library.Go em
// apps/geometry-worker -- não apenas a do Gyroid (ver LibraryGoConfigurationTests.cs, que cobre
// só GyroidScaffoldBuilder.cs). Adicionado na rodada Voronoi 20260806-133141, item 8, depois de
// uma auditoria por reflexão + decompilação real contra o PicoGK.dll 2.2.0 instalado
// (System.Reflection + ilspycmd, ver WORKER_STATUS.md) mostrar que Library.Go SÓ garante o
// encerramento do processo quando (a) bEndAppWithTask é true E (b) a thread da tarefa (fnTask)
// realmente termina -- se um FUTURO provider de topologia (ex.: uma extensão do
// "anatomy_guided", hoje só um ponto de extensão reservado) adicionar uma nova chamada a
// Library.Go sem esse parâmetro, o processo do worker ficaria sujeito ao mesmo risco de nunca
// encerrar sozinho que motivou toda esta auditoria.
//
// Este teste NÃO pode ser um teste de comportamento em runtime (mesma limitação documentada em
// LibraryGoConfigurationTests.cs: este projeto de testes deliberadamente não referencia o
// pacote PicoGK, para permanecer executável neste sandbox Linux sem o runtime nativo). O que
// ele garante, de forma real e executável: TODO arquivo-fonte real do worker (qualquer
// *ScaffoldBuilder.cs presente ou futuro, ou qualquer outro arquivo em apps/geometry-worker)
// que contenha uma chamada a `Library.Go(` -- passa `bEndAppWithTask: true` literalmente nessa
// chamada. Ao contrário de LibraryGoConfigurationTests.cs (que hardcoda o nome do arquivo
// Gyroid), este teste ENUMERA o diretório real de apps/geometry-worker em tempo de execução --
// cobre automaticamente qualquer provider futuro, sem exigir que alguém lembre de atualizar
// este teste quando um novo *ScaffoldBuilder.cs for adicionado.
using System.Text.RegularExpressions;
using Xunit;

namespace BioMatCadGeometryWorker.Tests;

public class AllTopologyProvidersLibraryGoConfigurationTests
{
    /// <summary>Raiz real de apps/geometry-worker (onde vivem VoronoiScaffoldBuilder.cs,
    /// GyroidScaffoldBuilder.cs, Program.cs etc.) -- calculada a partir do diretório de saída do
    /// teste (bin/Debug/net9.0/...), igual à técnica já usada em
    /// LibraryGoConfigurationTests.cs.</summary>
    private static string GeometryWorkerRootDir()
    {
        string path = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..");
        path = Path.GetFullPath(path);
        Assert.True(Directory.Exists(path), $"Diretório raiz de apps/geometry-worker não encontrado no caminho esperado: {path}");
        // Confirma que é de fato a raiz certa (contém Program.cs) -- evita silenciosamente
        // escanear o diretório errado se a estrutura de pastas mudar no futuro.
        Assert.True(File.Exists(Path.Combine(path, "Program.cs")), $"Program.cs não encontrado em {path} -- GeometryWorkerRootDir() pode estar apontando para o diretório errado.");
        return path;
    }

    /// <summary>Enumera SOMENTE os arquivos *.cs diretamente em apps/geometry-worker (não
    /// recursivo) -- exclui naturalmente tests/, bin/ e obj/ (que vivem em subpastas), sem
    /// precisar de nenhuma lista de exclusão manual.</summary>
    private static IReadOnlyList<string> RealWorkerSourceFiles()
    {
        string root = GeometryWorkerRootDir();
        var files = Directory.GetFiles(root, "*.cs", SearchOption.TopDirectoryOnly);
        Assert.NotEmpty(files);
        return files;
    }

    [Fact]
    public void EveryRealSourceFile_WithLibraryGoCall_PassesBEndAppWithTaskTrue()
    {
        var files = RealWorkerSourceFiles();
        var violations = new List<string>();
        int totalLibraryGoCallsFound = 0;

        foreach (string file in files)
        {
            string source = File.ReadAllText(file);
            var matches = Regex.Matches(source, @"Library\.Go\(");
            if (matches.Count == 0)
            {
                continue;
            }

            totalLibraryGoCallsFound += matches.Count;

            foreach (Match match in matches)
            {
                // A chamada é multi-linha (lambda como segundo argumento) -- procura o
                // argumento nomeado em todo o RESTANTE do arquivo a partir do início desta
                // chamada específica, até o próximo "Library.Go(" (ou o fim do arquivo) --
                // seguro mesmo se um arquivo um dia tiver mais de uma chamada.
                int start = match.Index;
                int nextCallIndex = source.IndexOf("Library.Go(", start + 1, StringComparison.Ordinal);
                string callRegion = nextCallIndex >= 0
                    ? source.Substring(start, nextCallIndex - start)
                    : source.Substring(start);

                if (!callRegion.Contains("bEndAppWithTask: true"))
                {
                    violations.Add(
                        $"{Path.GetFileName(file)} (offset {start}): chamada a Library.Go(...) " +
                        "sem 'bEndAppWithTask: true' literal -- risco de o processo do worker " +
                        "nunca encerrar sozinho (ver auditoria da rodada Voronoi 20260806-133141 " +
                        "em WORKER_STATUS.md).");
                }
            }
        }

        // Guarda contra um teste "neutralizado" silenciosamente (ex.: por um refactor que move
        // as chamadas para fora de apps/geometry-worker, ou renomeia o método) -- se NENHUMA
        // chamada a Library.Go for encontrada em lugar nenhum, isso também é uma falha: hoje
        // sabemos que existem pelo menos duas (Gyroid e Voronoi).
        Assert.True(
            totalLibraryGoCallsFound >= 2,
            $"Esperado encontrar pelo menos 2 chamadas reais a Library.Go( (Gyroid + Voronoi) " +
            $"nos arquivos-fonte de apps/geometry-worker, mas encontrou {totalLibraryGoCallsFound} -- " +
            "este teste pode estar escaneando o diretório errado.");

        Assert.True(violations.Count == 0, "Violações encontradas:\n" + string.Join("\n", violations));
    }
}
