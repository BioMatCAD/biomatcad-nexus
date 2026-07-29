# apps/geometry-worker — Motor geométrico (C#/.NET 9 + PicoGK 2.2.0)

**Status: implementado e compilado; execução real BLOQUEADA neste ambiente, com evidência —
ver `WORKER_STATUS.md` (Incremento 2.1, Fase 2).**

## Propósito

Worker C#/.NET separado da API, responsável por gerar o scaffold Gyroid (superfície mínima
periódica) dentro de um domínio `block` ou `cylinder`, a partir de uma receita BioMatCEM
validada (`schemas/biomatcem/geometry-recipe-v1.schema.json`). Usa o PicoGK (LEAP 71,
Apache-2.0) como geometry kernel — não reimplementa nem alega afiliação com o Noyron
(software proprietário distinto da mesma empresa). Ver `NOTICE` para atribuição completa.

## Estrutura

- `JobEnvelope.cs` — contrato JSON de entrada/saída (independente de PicoGK, testável).
- `SimpleMesh.cs`, `GeometryMetricsCalculator.cs`, `StlExporter.cs` — matemática de malha,
  métricas geométricas e exportação STL, também independentes de PicoGK (testados: ver
  `tests/BioMatCadGeometryWorker.Tests`, 9/9 testes passando).
- `GyroidScaffoldBuilder.cs` — geração real via PicoGK (`Voxels`, `Mesh`, `IImplicit`). Compila
  com sucesso; execução bloqueada neste ambiente (ver `WORKER_STATUS.md`).
- `Program.cs` — ponto de entrada (`dotnet BioMatCadGeometryWorker.dll <job.json>`), chamado
  pelo backend Python via `biomatcad_api.services.worker_client.DotnetPicoGkWorkerClient`.

## Por que está bloqueado

O pacote NuGet oficial `PicoGK` 2.2.0 só distribui o runtime nativo compilado para `win-x64` e
`osx-arm64` — não há binário para `linux-x64`, a plataforma deste sandbox. Isso foi confirmado
tanto por inspeção do pacote quanto por tentativa real de execução (`DllNotFoundException`
reproduzida e documentada). Ver `WORKER_STATUS.md` para a evidência completa.

## Fonte no Prompt Mestre

Seção 6.3

## Próximo passo

Ver `REQUIREMENTS_MATRIX.md` e `WORKER_STATUS.md` para o caminho de desbloqueio (execução em
Windows/macOS, ou build nativo do PicoGK para linux-x64 — nenhum realizado nesta sessão).
