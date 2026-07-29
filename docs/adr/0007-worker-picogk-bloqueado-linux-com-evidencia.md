# ADR-0007: Worker C#/PicoGK implementado e testável, mas bloqueado em execução real neste sandbox

- Status: Aceita (bloqueio declarado, não contornado)
- Data: 2026-07-29 (Incremento 2.1)
- Decisor: Adler Lima Botelho de Azevedo (usuário) — instrução explícita: "Se o PicoGK não puder
  ser executado no sandbox, declare o incremento parcialmente bloqueado. Não substitua
  silenciosamente o worker por geometria falsa."

## Contexto

O núcleo geométrico do Incremento 2.1 depende do pacote NuGet oficial `PicoGK` 2.2.0 (LEAP 71,
Apache-2.0) para gerar o scaffold Gyroid via voxelização (`Voxels`, `Mesh`, `IImplicit`). O
ambiente de execução desta sessão é um sandbox Linux x86_64 sem Docker e sem privilégio de root.

## Investigação (evidência, não suposição)

1. `.NET SDK` 9.0.316 foi instalado em espaço de usuário
   (`dotnet-install.sh --install-dir /tmp/dotnet --no-path`, sem root) — PicoGK 2.2.0 exige
   `net9.0`.
2. O pacote `PicoGK` 2.2.0 resolve e o projeto `apps/geometry-worker` compila com
   `dotnet build` sem erros (0 Warning(s), 0 Error(s)).
3. Inspeção do conteúdo do pacote NuGet restaurado mostrou runtime nativo (`picogk.26.2`)
   presente **apenas** em `runtimes/win-x64/native/` e `runtimes/osx-arm64/native/` — **nenhuma
   pasta** `runtimes/linux-x64/native/` existe no pacote 2.2.0.
4. Execução real do binário compilado (`dotnet BioMatCadGeometryWorker.dll <job.json>`) produziu
   `System.DllNotFoundException: Unable to load shared library 'picogk.26.2' ... cannot open
   shared object file` — confirmando em tempo de execução, não apenas por inspeção estática, que
   o runtime nativo não está disponível para linux-x64.

Evidência completa (comandos, saída integral, stack trace) em
`apps/geometry-worker/WORKER_STATUS.md` e nos logs brutos
`apps/geometry-worker/EVIDENCE_execution_attempt_std{out,err}.log`.

## Decisão

1. **Não fabricar sucesso**: o worker nunca retorna uma malha ou métricas fabricadas quando o
   runtime nativo está ausente — `Program.cs` captura a exceção (mesmo quando o PicoGK a
   reembrulha como `System.Exception` genérica, em vez de propagar a `DllNotFoundException`
   diretamente) e emite um `StructuredWorkerError` com `error_code=PICOGK_RUNTIME_UNAVAILABLE`
   em stderr, com exit code 1. `DotnetPicoGkWorkerClient` (Python) traduz isso em
   `WorkerExecutionError(code=WORKER_RUNTIME_UNAVAILABLE)`, propagado pela orquestração
   (`geometry_job_service.dispatch_job`) como `GeometryJob.status=failed`, nunca como sucesso.
2. **Separar código dependente de PicoGK do código independente**: `GyroidScaffoldBuilder.cs` e
   `Program.cs` (dependentes) ficam isolados de `JobEnvelope.cs`, `SimpleMesh.cs`,
   `GeometryMetricsCalculator.cs`, `StlExporter.cs` (independentes) — um projeto de teste xunit
   separado (`tests/BioMatCadGeometryWorker.Tests`) compila e executa genuinamente 9 testes
   sobre os arquivos independentes, sem exigir o runtime nativo bloqueado.
3. **Teste dedicado do caminho de falha real**: `test_dispatch_job_real_worker_fails_in_blocked_
   environment` (Python, `skipif` na ausência de `dotnet`) invoca o `DotnetPicoGkWorkerClient`
   de verdade contra o binário compilado de verdade, e afirma que o `error_code` retornado é um
   dos códigos de bloqueio esperados — prova automatizada e repetível do bloqueio, não apenas um
   registro textual em markdown.
4. **Declarar o incremento parcialmente bloqueado**: a geração real de um scaffold Gyroid via
   PicoGK, a verificação de determinismo geométrico, a geração de thumbnail e a exportação VDB
   permanecem não verificadas nesta sessão — item explícito em `IMPLEMENTATION_STATUS.md` e no
   relatório final ao usuário, nunca apresentado como concluído.
5. **Não usar Noyron**: nem o código nem a documentação fazem referência a Noyron (software
   proprietário da LEAP 71, distinto do PicoGK). O único componente de terceiros referenciado é
   o PicoGK, oficialmente open source sob Apache-2.0 (ver `apps/geometry-worker/NOTICE`).

## Caminhos de desbloqueio não tentados nesta sessão

- Executar o worker compilado em Windows ou macOS (onde o pacote 2.2.0 traz runtime nativo
  oficial) — não disponível neste sandbox.
- Compilar o runtime nativo do PicoGK a partir do código-fonte C++ para linux-x64 — não
  tentado; exigiria toolchain de build C++ e teria que ser avaliado quanto à licença/suporte
  oficial antes de ser adotado como caminho suportado.

## Consequências

- A vertical geométrica está **implementada e testável em suas partes não bloqueadas** (schema,
  modelos, orquestração de job com fila Postgres, API, frontend com STL sintético rotulado,
  métricas geométricas sobre malhas de teste), mas **não é uma vertical geométrica real e
  ponta-a-ponta executável neste ambiente** — condição explícita do Prompt Mestre para avançar à
  Fase 3 ("não avance para a Fase 3 até a vertical geométrica estar realmente executável")
  permanece não satisfeita.
- Qualquer ambiente Windows/macOS com o SDK .NET 9 deve conseguir executar
  `apps/geometry-worker` de fato — o contrato (JSON de entrada/saída, CLI) já está pronto para
  isso, sem mudança de código, apenas trocando o sistema operacional de execução.

---

## Atualização (Incremento 2.1.1)

A decisão original acima permanece integralmente válida — nada foi contornado, nenhum resultado
foi fabricado. O que mudou neste incremento corretivo:

1. **Todo o código em volta do bloqueio foi corrigido e re-testado matematicamente.** A auditoria
   do Incremento 2.1 encontrou defeitos reais na lógica que, uma vez desbloqueada, geraria a
   geometria: domínio cilíndrico recortado pela bounding box (não pelo cilindro real), ausência
   de solda de vértices (causa raiz de uma divergência real de contagem STL-vs-manifesto),
   espessura/isovalor com papéis ambíguos, seed sem efeito determinístico real, preview e final
   indistinguíveis na prática. Essas correções foram implementadas em `GyroidMath.cs` (núcleo
   matemático, novo, totalmente independente do PicoGK) e em `GyroidScaffoldBuilder.cs`
   (`GyroidDomainImplicit`, dependente do PicoGK), e testadas com 48 testes xUnit — todos contra
   o código independente, nenhum contra o PicoGK real, pelo mesmo motivo que originou esta ADR.
2. **Caminho de desbloqueio escolhido**: em vez de investigar um build nativo do PicoGK para
   linux-x64 (caminho mais lento, levantado como opção não tentada na decisão original), o
   responsável pelo projeto (Adler) decidiu executar o worker **no seu próprio Windows x64**, a
   plataforma com runtime nativo oficial do pacote 2.2.0, e devolver os artefatos reais (STL,
   logs, manifesto) para conferência. O guia operacional completo está em
   `docs/examples/WINDOWS_EXECUTION_KIT.md`, incluindo o helper
   `apps/geometry-worker/tools/New-JobFromRecipe.ps1` (monta um `job.json` a partir de uma golden
   recipe) e `scripts/audit_stl_vs_worker_output.py` (recomputação independente, em Python, das
   métricas do STL gerado, para conferência cruzada contra o manifesto).
3. **Nada aqui altera o status do bloqueio em si**: `apps/geometry-worker` continua sem poder
   executar de verdade neste sandbox Linux. Os 17 itens de aceite do Incremento 2.1.1 que
   dependem de execução real do PicoGK (geração real de scaffold, determinismo geométrico,
   métricas/manifesto coerentes com um STL real, thumbnail, VDB) permanecem **pendentes** até que
   os resultados do Windows do usuário sejam devolvidos e conferidos — ver
   `IMPLEMENTATION_STATUS.md` para o checklist item a item.
