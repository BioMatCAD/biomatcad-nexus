# BioMatCAD Nexus — Launcher Windows (Incremento 2.1.1)

Iniciador executável de duplo clique que substitui a necessidade de abrir três PowerShells
manuais para preparar e rodar o ambiente de desenvolvimento/teste do BioMatCAD Nexus (API +
frontend). **É exclusivamente um utilitário de desenvolvimento/teste** — ver seção "Segurança".

## O que ele faz (duplo clique único)

1. Localiza a raiz do repositório a partir do diretório do próprio executável (funciona mesmo
   se o `.exe` estiver em `dist/windows-launcher/`, ou tenha sido movido, ou o repositório
   esteja em um caminho com espaços).
2. Detecta Python, Node.js, npm e .NET no `PATH` real da máquina, resolvendo os caminhos
   absolutos manualmente (ver "Segurança" — isso é também uma defesa contra command injection).
3. Localiza ou cria `apps/api/.venv`.
4. Instala a API em modo editável (`pip install -e .`) somente se ainda não estiver instalada.
5. Verifica `node_modules`/`package-lock.json` do frontend e roda `npm ci`/`npm install`
   somente se necessário.
6. Gera um `API_SECRET_KEY` efêmero, criptograficamente seguro (256 bits, via
   `RandomNumberGenerator` do .NET — nunca `System.Random`).
7. Define `ENVIRONMENT=test` para o processo da API.
8. Inicia a API em `http://localhost:8000`.
9. Inicia o frontend em `http://localhost:5173`.
10. Aguarda ambos os serviços ficarem disponíveis (poll de socket TCP real, com timeout).
11. Abre `http://localhost:5173/login` no navegador padrão.
12. Mostra status, PIDs e mantém os logs (stdout/stderr) dos processos filhos visíveis.
13. Ao fechar a janela ou pressionar Ctrl+C, encerra **somente** os processos filhos que ele
    mesmo iniciou (nunca um `taskkill` genérico por nome ou por porta).
14. Detecta portas já ocupadas: se 8000 ou 5173 já estiverem em uso, **reaproveita** o serviço
    existente em vez de tentar iniciar uma segunda instância.
15. **Nunca** grava ou exibe o segredo gerado (nem no console, nem em disco, nem em log).
16. Exibe permanentemente o banner: **"AMBIENTE DE TESTE — NÃO UTILIZAR DADOS CLÍNICOS REAIS"**.

O launcher **não** roda seed de dados sintéticos automaticamente. (A opção explícita
"Preparar dados sintéticos de demonstração" faz parte do roadmap deste mesmo incremento — ver
`IMPLEMENTATION_STATUS.md` para o estado exato desse item específico nesta entrega.)

## Como usar (Windows)

```powershell
# 1. Compilar (uma vez, ou sempre que o código do launcher mudar):
pwsh -File .\scripts\Build-WindowsLauncher.ps1

# 2. Rodar (duplo clique no Explorer, ou via linha de comando):
.\Start-BioMatCAD.cmd
```

Para encerrar: feche a janela do console ou pressione `Ctrl+C`. Isso mata a API e o frontend
(e toda a árvore de processos de cada um), mas nunca afeta outros programas na máquina.

## Arquitetura do código

```
tools/windows-launcher/
  BioMatCAD.Launcher.csproj      projeto .NET 9 (net9.0), OutputType=Exe
  Program.cs                     orquestração dos 16 comportamentos (ponto de entrada)
  src/
    RepositoryLocator.cs         localiza a raiz do repo (sobe diretórios até achar marcadores)
    PathResolver.cs              resolução manual de PATH/PATHEXT (defesa central contra
                                  command injection — ver abaixo)
    DependencyDetector.cs        detecta Python/Node/npm/.NET via "--version" real
    PortChecker.cs                verifica/aguarda portas via sockets TCP reais
    SecretGenerator.cs           gera API_SECRET_KEY efêmero via CSPRNG
    StartupPlanner.cs            lógica PURA de decisão (reaproveitar serviço existente,
                                  bloquear por dependência faltando) — sem I/O, 100% testável
    ProcessSupervisor.cs         inicia/rastreia/mata processos filhos reais
    EnvironmentSetup.cs          venv, pip install -e ., npm ci/install
  tests/BioMatCAD.Launcher.Tests/
    ... suíte xUnit real (ver "Testes" abaixo)
```

## Segurança

- **Command injection**: toda invocação de processo usa
  `ProcessStartInfo.ArgumentList` (cada argumento como elemento discreto de array), **nunca**
  a propriedade `Arguments` (string única concatenada, que pode ser reinterpretada por um
  shell em certas condições no Windows). Verificado por teste de guarda
  (`SecurityReviewGuardTests`) que falha se alguém reintroduzir `.Arguments =` no código.
- **`UseShellExecute=true`** é usado em **exatamente um lugar**: abrir o navegador em
  `http://localhost:5173/login`, uma URL **fixa e interna**, nunca construída a partir de
  input externo/do usuário — logo, não é um vetor de injeção.
- **Resolução de comandos**: `PathResolver.WhichCommand` resolve manualmente o caminho
  absoluto de `python`/`node`/`npm`/`dotnet` a partir do `PATH`/`PATHEXT` reais, e esse
  caminho absoluto é sempre o que vira `ProcessStartInfo.FileName` — nunca um nome de comando
  "nu" que dependeria da resolução implícita (às vezes inconsistente, ex.: `npm` vs
  `npm.cmd`) do `CreateProcess` do Windows.
- **Segredo (`API_SECRET_KEY`)**: gerado com `RandomNumberGenerator` (CSPRNG do SO, 256 bits),
  passado **somente** como variável de ambiente do processo filho da API. Nunca impresso no
  console, nunca gravado em arquivo, nunca incluído em nenhuma mensagem de log. Verificado por
  teste de guarda que varre `Program.cs` em busca de qualquer `Console.Write*` que referencie
  a variável.
- **Encerramento de processos**: `ProcessSupervisor` rastreia cada processo filho por
  **referência de objeto** (não por nome ou porta) e usa `Process.Kill(entireProcessTree:
  true)` apenas sobre os processos que ele mesmo criou. Nunca usa `taskkill` (verificado por
  teste de guarda).
- **Sem Docker, sudo, ou elevação de administrador**: o launcher nunca invoca `docker`,
  `sudo`, `runas`, nem solicita elevação de privilégios (verificado por teste de guarda).
- **Sem segredos fixos no código**: nenhuma senha ou token literal aparece no código-fonte —
  o único segredo (`API_SECRET_KEY`) é sempre gerado em tempo de execução.
- **Ambiente sempre de teste**: `ENVIRONMENT` é sempre definido como `"test"` para o processo
  da API — o launcher nunca define, sugere, nem oferece um valor diferente (verificado por
  teste de guarda que varre todas as atribuições a essa chave).

## Testes

`tools/windows-launcher/tests/BioMatCAD.Launcher.Tests/` — 101 testes xUnit, **todos reais**
(sem mocks/fakes de sistema operacional): usam diretórios temporários reais, sockets TCP
reais, subprocessos reais. Onde é preciso um "processo real de longa duração ou controlado"
para testes de supervisão (em vez de `node`/`npm`/`dotnet` genuinamente instalados, usados
para os cenários de detecção de dependências em si), os testes usam
`tests/TestHelperProcess` — um executável .NET puro, genuinamente multiplataforma, sem
nenhuma dependência de `sh`/`sleep`/`python3`/`cmd.exe timeout` do sistema operacional (ver
"Incremento 2.2, Seção 2 — commit 774b5ae" acima para o porquê desta mudança: a versão
anterior desses testes dependia de binários específicos do SO e falhou de verdade na
validação no Windows). Cobrem explicitamente os 10 cenários pedidos originalmente, mais os
casos de regressão adicionados desde então:

| # | Cenário pedido | Onde |
|---|---|---|
| 1 | Raiz do projeto | `RepositoryLocatorTests` |
| 2 | Caminhos com espaços | `RepositoryLocatorTests.FindRepoRoot_ComEspacosNoCaminho_...` |
| 3 | Detecção de dependências | `DependencyDetectorTests` (real, contra binários instalados) |
| 4 | Segredo não exposto | `SecretGeneratorTests` (entropia/unicidade + guarda textual) |
| 5 | Portas ocupadas | `PortCheckerTests` (sockets TCP reais) |
| 6 | Início parcial | `StartupPlannerTests` + `ProcessSupervisorTests.ShutdownAll_ComInicioParcial_...` |
| 7 | Encerramento dos filhos | `ProcessSupervisorTests.ShutdownAll_EncerraApenasOsProcessosRealmenteRastreados` |
| 8 | Composição de comandos Windows | `PathResolverWindowsCompositionTests` (PATH/PATHEXT sintéticos, modo Windows) |
| 9 | Python 3.14 | `DependencyDetectorTests.ParseVersion_Python314_...` (comparação numérica, não lexicográfica) |
| 10 | API/frontend já ativos | `StartupPlannerTests.PlanService_ComPortaJaOcupada_...` |

Rodar localmente:

```bash
dotnet test tools/windows-launcher/tests/BioMatCAD.Launcher.Tests/BioMatCAD.Launcher.Tests.csproj
```

**Resultado real obtido no sandbox de desenvolvimento (Linux) nesta rodada: 101/101 passaram.**
Isso NÃO substitui a validação real no Windows -- ver a seção "Status de validação" acima.
`Program.cs` em si (orquestração/`Main`) não é compilado no projeto de testes por usar
top-level statements — toda a lógica que ele orquestra vive nas classes acima, que são
testadas diretamente. `Program.cs` foi validado por execução manual real neste sandbox
(detecção de dependências reais, criação de venv real, início de `pip install`) — ver
`IMPLEMENTATION_STATUS.md` para o relato exato do que foi exercido de ponta a ponta versus o
que depende de validação no Windows real do usuário.

## Build / publish para Windows

```powershell
pwsh -File .\scripts\Build-WindowsLauncher.ps1
```

Equivalente a:

```powershell
dotnet publish tools/windows-launcher/BioMatCAD.Launcher.csproj `
  -c Release `
  -r win-x64 `
  --self-contained false `
  -p:PublishSingleFile=true `
  -o dist/windows-launcher
```

Gera `dist/windows-launcher/BioMatCAD-Nexus.exe` (framework-dependente: requer o .NET 9
Runtime instalado, já um pré-requisito documentado do worker PicoGK) e
`dist/windows-launcher/BioMatCAD-Nexus.exe.sha256` com o hash SHA-256 do binário.

**Este `.exe` não é versionado no Git** (decisão documentada — ver `.gitignore` e
`IMPLEMENTATION_STATUS.md`): é um artefato de build, reproduzível a qualquer momento a partir
do código-fonte versionado, e o usuário deve gerá-lo localmente (ou usar o binário entregue
fora do histórico Git, conforme instruções de entrega).

## Status de validação — duas etapas distintas

- **Cross-build (sandbox Linux)**: `dotnet publish -r win-x64` rodou de verdade neste ambiente
  de desenvolvimento e produziu um `.exe` PE32+ Windows genuíno (confirmado via `file`), com
  SHA-256 `b6ae108ca7305b256d778403211cddb14d31d958cabb3f63b1132d99210070f6`. Isso prova que o
  código **compila** para Windows — não prova que ele **funciona** quando executado (o sandbox
  Linux não roda binários win-x64).
- **Execução real (Windows do usuário)**: o usuário baixou este `.exe`, conferiu o SHA-256
  acima antes de executar, e rodou de verdade. Resultado relatado: o executável abriu
  corretamente, a API e o frontend foram iniciados pelo launcher, o navegador abriu a
  interface, a tela de login ficou disponível, e o encerramento (fechar/Ctrl+C) funcionou
  corretamente — nenhum problema observado. Ver `TEST_EVIDENCE.md` §14 para a transcrição
  literal desta validação e o que fica explicitamente fora do relato (alguns dos 16
  comportamentos, como criação vs. reaproveitamento de `.venv`/`node_modules` ou o cenário de
  porta já ocupada, não foram confirmados individualmente porque o relato não entrou nesse
  nível de detalhe — isso não invalida a aprovação do caminho principal, apenas não é afirmado
  aqui como confirmado).

### Incremento 2.2, Seção 2 — commit 774b5ae: FALHOU no Windows real (14 testes)

Registro honesto, como manda a regra deste projeto de nunca declarar sucesso sem prova real:
o commit `774b5ae` (integração do launcher com banco/API/dispatcher/frontend) foi validado
apenas no sandbox Linux (`dotnet build` aprovado, 97 testes C# passando) antes de ser entregue
ao usuário. Quando o usuário rodou `dotnet build` + `dotnet test` de verdade no Windows,
**14 dos 97 testes falharam**. Nenhum problema de geometria, API ou frontend foi encontrado —
todas as falhas eram de portabilidade Windows do próprio launcher e da sua suíte de testes:

1. `DependencyDetector`/`PathResolver`: quatro testes de detecção de dependências tinham
   `isWindows: false` **hardcoded**, mas liam o `PATH` real da máquina que roda os testes. No
   Windows real isso fazia a resolução de `npm` encontrar o script POSIX sem extensão (que o
   instalador do Node também deixa ao lado de `npm.cmd`) em vez de `npm.cmd`, e tentar executá-lo
   diretamente — falha real com "not a valid Win32 application".
2. `DispatcherManagerTests`: dois testes invocavam `"python3"` diretamente como nome de
   processo — inexistente no Windows (que usa `python.exe`/`py.exe`).
3. `PathResolverWindowsCompositionTests`: três testes comparavam caminhos resolvidos com
   `Assert.Equal`/`Assert.EndsWith` sensíveis a maiúsculas/minúsculas; em Windows real
   (filesystem case-insensitive), o sufixo do `PATHEXT` (`.EXE`, maiúsculo) é preservado na
   resolução e não bate literalmente com a extensão em minúsculas do teste (`.exe`) — a
   resolução em si estava correta, a asserção do teste é que era frágil.
4. `ProcessSupervisorTests`: seis testes usavam `cmd.exe /c timeout /t N` (falha real e
   intermitente no Windows quando executado sem console interativo real) e uma composição de
   string via `cmd.exe`/`sh` para propagação de variável de ambiente (frágil por depender da
   sintaxe exata de expansão/redirecionamento de cada shell).
5. `StartTracked_ComLogFilePath...`: o `StreamWriter` do arquivo de log não era fechado antes
   de o teste tentar apagar seu diretório temporário — no Windows (ao contrário do Linux), um
   arquivo com handle aberto não pode ser apagado, causando falha real de limpeza.

**Correção aplicada nesta rodada** (commit seguinte a `774b5ae`, ver `git log`): as quatro
detecções agora usam `OperatingSystem.IsWindows()` de verdade; foi criado um processo auxiliar
de testes genuinamente multiplataforma (`tests/TestHelperProcess`, um executável .NET puro,
sem shell/sh/sleep/python3/cmd.exe) usado por todos os testes que antes dependiam de binários
específicos do SO; as asserções de caminho passaram a comparar com
`StringComparison.OrdinalIgnoreCase`; `ProcessSupervisor.Dispose()` foi reforçado para esperar
a saída do processo e fechar (`Flush`+`Dispose`) o `LogWriter` antes de retornar. Quatro novos
testes de regressão foram adicionados (prioridade de `npm.cmd`, case-insensitividade de
PATH/PATHEXT, dispose do arquivo de log, isolamento entre instâncias de `ProcessSupervisor`).
`dotnet test` no sandbox Linux agora passa 101/101 — **mas, como o próprio bug desta seção
prova, sucesso no sandbox Linux não é prova suficiente de sucesso no Windows real**. A
aprovação final desta seção continua condicionada à nova execução real do usuário no Windows,
relatando 0 falhas.

### Incremento 2.2, Seção 2 — commit 882d9fe: 100/101 no Windows real (1 falha restante corrigida nesta rodada)

Registro honesto de uma segunda rodada de validação real: o usuário rodou `dotnet build` +
`dotnet test` de verdade no Windows contra o commit `882d9fe` (a correção das 14 falhas acima).
Resultado: **melhora de 83/97 para 100/101 — mas com 1 falha real remanescente**, não
cosmética:

```
ProcessSupervisorNamedControlTests.StartTracked_ComLogFilePath_DrenaStdoutEStderrSanitizadosParaOArquivo
System.IO.IOException: child.log está sendo usado por outro processo.
```

**Causa raiz real** (não flakiness, não timing do teste): a regra de compartilhamento de
arquivos do Windows é bidirecional. Quando o `LogWriter` do processo filho abre `child.log`
para escrita com `FileShare.Read`, um leitor separado (como `File.ReadAllText`, que abre com
`FileShare.Read` por padrão) só consegue abrir o mesmo arquivo se o handle **já aberto**
também permitir a nova operação — e a checagem correspondente exige que o handle já aberto
tenha `FileShare` compatível com o ACESSO do novo handle, e vice-versa. Como o escritor só
oferece `FileShare.Read` (nunca `Write`), e o leitor pede compartilhamento padrão (`Read`), a
checagem "o ACESSO do handle já existente (Write) é permitido pelo SHARE do novo handle" falha
— por isso o `IOException`. Isso nunca aparece no Linux (sem imposição de sharing mandatório
no nível do SO), o que explica por que o sandbox deste projeto sempre passou 101/101 mesmo com
esse bug real presente.

**Correção aplicada nesta rodada** (commit seguinte a `882d9fe`, ver `git log`):

1. Novo `ProcessSupervisor.ReadLogFile(path)` estático, que abre o arquivo com
   `FileShare.ReadWrite` do lado do LEITOR — não se alterou o lado do escritor (que continua
   com `FileShare.Read`, nunca `Write`, preservando a garantia de que nenhum processo externo
   pode escrever concorrentemente no log). É o padrão recomendado para observabilidade: ler um
   arquivo que ainda está sendo escrito por outro handle no mesmo processo.
2. Ciclo de vida do log tornado explícito e convergente: `StdoutDrained`/`StderrDrained`
   (`ManualResetEventSlim`, sinalizados pelos próprios handlers `OutputDataReceived`/
   `ErrorDataReceived` quando entregam `e.Data == null`, ou seja, EOF real de cada stream, não
   um timing estimado) mais uma rotina privada única `FinalizeChild` que espera (bounded, 5s
   por stream) a drenagem terminar antes de `Flush`+`Dispose` do `LogWriter`.
3. `FinalizeChild` é idempotente e thread-safe (`Interlocked.CompareExchange` via
   `TrackedChild.TryBeginFinalize()`) e é agora o ÚNICO lugar que fecha o log — chamado a
   partir dos quatro caminhos de término (`Process.Exited` natural, `TryKillNamed`,
   `ShutdownAll`, `Dispose`), garantindo que todos convirjam para o mesmo comportamento em vez
   de cada um ter sua própria lógica de fechamento.
4. Novo `ProcessSupervisor.WaitUntilLogDrained(name, timeout)` público, para quem precisar
   esperar a drenagem terminar antes de ler (condição real, não sleep fixo).

Cinco testes novos/reescritos cobrem exatamente os cenários pedidos: leitura do log com o
processo ainda rodando (`ReadLogFile_ConsegueLerOLogComOProcessoAindaRodando`); leitura
imediatamente após término natural, sem chamar `Dispose()` antes e sem sleep arbitrário
(`ReadLogFile_LeOLogImediatamenteAposTerminoNatural_SemDisposeESemSleepArbitrario` — a
regressão direta do bug relatado); fechamento e exclusão após `Dispose()`
(`Dispose_FechaOArquivoDeLogPermitindoApagarODiretorioLogoEmSeguida`); finalização idempotente
acionada por dois caminhos diferentes (término natural + `Dispose()`, sem exceção)
(`FinalizacaoDoLog_EhIdempotente_MesmoAcionadaPorCaminhosDiferentes`); e stdout/stderr
completos e sanitizados via `WaitUntilLogDrained` + `ReadLogFile`
(`StartTracked_ComLogFilePath_DrenaStdoutEStderrSanitizadosParaOArquivo`, reescrito para não
usar mais `File.ReadAllText`).

**Mutation test real desta correção**: removida deliberadamente (e depois restaurada, com
`diff` confirmando o arquivo idêntico ao original) a espera de drenagem
(`StdoutDrained?.Wait`/`StderrDrained?.Wait`) dentro de `FinalizeChild`. Resultado: falha real
e reproduzível (2 de 3 execuções) exatamente nos dois testes que essa espera deveria proteger
(`ReadLogFile_LeOLogImediatamenteAposTerminoNatural...` e
`FinalizacaoDoLog_EhIdempotente...`), com a mensagem exata esperada
(`Assert.Contains() Failure: ... Not found: "linha stdout"` — prova de que o `LogWriter` foi
fechado antes de todo o stdout assíncrono ter sido entregue). Note que a mutação equivalente no
lado do **leitor** (voltar `ReadLogFile` para `FileShare.Read`) não é detectável por nenhum
teste neste sandbox Linux, pelo mesmo motivo estrutural do bug original: o Linux não impõe essa
regra de compartilhamento, então o teste não pode reproduzi-la aqui — a única prova real
possível para essa parte específica da correção é a nova execução do usuário no Windows.

`dotnet build` limpo (0 avisos, 0 erros) e `dotnet test` **104/104** no sandbox Linux (101
anteriores + 3 novos testes). Como sempre: sucesso no sandbox Linux não é prova suficiente de
sucesso no Windows real. A aprovação final desta seção continua condicionada à nova execução
real do usuário no Windows, relatando 0 falhas.
