# apps/geometry-worker — Motor geométrico (C#/.NET 9 + PicoGK 2.2.0)

**Status: implementado, compilado e corrigido (Incremento 2.1.1); execução real continua
BLOQUEADA neste ambiente, com evidência — ver `WORKER_STATUS.md` (Incremento 2.1, Fase 2, e
correções do Incremento 2.1.1).**

## Propósito

Worker C#/.NET separado da API, responsável por gerar o scaffold Gyroid (superfície mínima
periódica) dentro de um domínio `block` ou `cylinder`, a partir de uma receita BioMatCEM
validada (`schemas/biomatcem/geometry-recipe-v1.schema.json`). Usa o PicoGK (LEAP 71,
Apache-2.0) como geometry kernel — não reimplementa nem alega afiliação com o Noyron
(software proprietário distinto da mesma empresa). Ver `NOTICE` para atribuição completa.

## Estrutura

- `GyroidMath.cs` — **novo no Incremento 2.1.1**: núcleo matemático do scaffold Gyroid,
  TOTALMENTE independente do PicoGK (nenhuma referência a `PicoGK.*`). Avaliação do campo gyroid
  de Schoen (1970), SDF exata de bloco/cilindro, interseção booleana implícita (`max()`,
  CSG padrão), conversão `wall_thickness_mm` ↔ meia-largura de banda, mapeamento determinístico
  seed→deslocamento de fase, estimativa de fração sólida por amostragem em grade, calibração de
  porosidade por bisseção, piso de voxel size do modo preview, e estimativas prévias
  (limite superior) de contagem de voxels/memória. É por isso que essa parte É testável de
  verdade mesmo com o PicoGK bloqueado (27 dos 48 testes xUnit).
- `JobEnvelope.cs` — contrato JSON de entrada/saída (independente de PicoGK, testável).
- `SimpleMesh.cs`, `GeometryMetricsCalculator.cs`, `StlExporter.cs` — matemática de malha,
  métricas geométricas e exportação STL, também independentes de PicoGK. Desde o Incremento
  2.1.1, `SimpleMesh` tem um método `Weld()` (solda de vértices duplicados) aplicado antes de
  medir/exportar — corrige a divergência de contagem de vértices encontrada na auditoria
  (STL com vértices duplicados por triângulo vs. manifesto reportando vértices únicos). Testado
  em `tests/BioMatCadGeometryWorker.Tests` (48/48 testes passando).
- `GyroidScaffoldBuilder.cs` — geração real via PicoGK (`Voxels`, `Mesh`, `IImplicit`). Contém a
  classe `GyroidDomainImplicit` (substitui o antigo arquivo `GyroidImplicit.cs` do Incremento
  2.1, que não existe mais separadamente), que combina a banda gyroid com o SDF do domínio real
  (bloco ou cilindro, via `GyroidMath`) — o cilindro deixa de ser recortado pela bounding box.
  Compila com sucesso; execução continua bloqueada neste ambiente (ver `WORKER_STATUS.md`).
- `Program.cs` — ponto de entrada (`dotnet BioMatCadGeometryWorker.dll <job.json>`), chamado
  pelo backend Python via `biomatcad_api.services.worker_client.DotnetPicoGkWorkerClient`. Desde
  o Incremento 2.1.1, também aplica limites computacionais pré-execução (estimativa de
  voxel/memória, rejeitando receitas antes de alocar), timeout com kill de árvore de processos, e
  validação pós-gravação do STL exportado.
- `tools/New-JobFromRecipe.ps1` — **novo no Incremento 2.1.1**: helper PowerShell para montar um
  `job.json` a partir de uma golden recipe, usado no kit de execução Windows (ver
  `docs/examples/WINDOWS_EXECUTION_KIT.md`).

## Por que está bloqueado

O pacote NuGet oficial `PicoGK` 2.2.0 só distribui o runtime nativo compilado para `win-x64` e
`osx-arm64` — não há binário para `linux-x64`, a plataforma deste sandbox. Isso foi confirmado
tanto por inspeção do pacote quanto por tentativa real de execução (`DllNotFoundException`
reproduzida e documentada). Ver `WORKER_STATUS.md` para a evidência completa.

## Fonte no Prompt Mestre

Seção 6.3

## Próximo passo

Ver `REQUIREMENTS_MATRIX.md` e `WORKER_STATUS.md` para o caminho de desbloqueio. Para o
Incremento 2.1.1, o caminho escolhido é a execução real no Windows x64 do usuário — guia
completo em `docs/examples/WINDOWS_EXECUTION_KIT.md` (nenhum realizado neste sandbox; build
nativo do PicoGK para linux-x64 continua como alternativa não tentada).
