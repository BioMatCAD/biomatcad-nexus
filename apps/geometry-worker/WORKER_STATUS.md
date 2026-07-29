# WORKER_STATUS — apps/geometry-worker (Incremento 2.1, corrigido no 2.1.1)

Evidência bruta do estado real do worker C#/.NET 9 + PicoGK 2.2.0. Ver ADR-0007 para a decisão
e o raciocínio do bloqueio, e ADR-0008 para a semântica espessura/isovalor corrigida no
Incremento 2.1.1; este arquivo é o registro de evidência que os sustenta.

**Nota (Incremento 2.1.1)**: o bloqueio de execução real descrito abaixo (seções 1 a 5) é
idêntico ao do Incremento 2.1 — nada mudou neste ponto, e nenhuma tentativa de contorná-lo foi
feita. O que mudou é o CÓDIGO por trás do bloqueio: `GyroidScaffoldBuilder.cs` e o novo
`GyroidMath.cs` corrigem o recorte de domínio (SDF real do cilindro, não bounding box), a
semântica espessura/isovalor/porosidade, o determinismo por seed, a diferença preview/final, e a
solda de vértices antes de medir/exportar — tudo descrito em detalhe na seção 6 abaixo (agora
44 testes, não mais 9) e em `apps/geometry-worker/README.md`. Nenhuma dessas correções foi
provada contra uma execução real do PicoGK nesta sessão — ver
`docs/examples/WINDOWS_EXECUTION_KIT.md` para o caminho de fechamento dessa lacuna.

## 1. Ambiente .NET

```text
$ dotnet --info
.NET SDK:
 Version:           9.0.316
 Runtime Environment:
 OS Name:     ubuntu
 OS Version:  22.04
 RID:         linux-x64
.NET runtimes installed:
  Microsoft.AspNetCore.App 9.0.18
  Microsoft.NETCore.App 9.0.18
```

Instalado em espaço de usuário via `dotnet-install.sh --channel 9.0 --install-dir /tmp/dotnet
--no-path` -- sem root, sem binários adicionados ao Git.

## 2. Origem e licença do PicoGK

- Pacote: `PicoGK` 2.2.0 (NuGet).
- Autor: LEAP 71.
- Licença: Apache License 2.0.
- Origem: https://github.com/leap71/PicoGK
- Este componente **não** usa nem faz referência ao "Noyron" (software proprietário distinto,
  também da LEAP 71) -- apenas ao PicoGK, explicitamente open source.

## 3. Build

```text
$ dotnet build
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

O projeto `BioMatCadGeometryWorker.csproj` (net9.0) compila sem erros contra o pacote PicoGK
2.2.0.

## 4. Inspeção do pacote NuGet -- runtime nativo ausente para linux-x64

```text
$ find ~/.nuget/packages/picogk/2.2.0/runtimes -maxdepth 2
runtimes/win-x64
runtimes/win-x64/native
runtimes/osx-arm64
runtimes/osx-arm64/native
```

**Não existe `runtimes/linux-x64/native/`** no pacote 2.2.0 -- confirmado por listagem direta
do diretório de pacotes NuGet restaurado, não por suposição.

## 5. Execução real -- falha reproduzida com evidência completa

```text
$ dotnet bin/Debug/net9.0/BioMatCadGeometryWorker.dll job.json
EXIT=1
```

Saída de erro estruturada (stderr, ver `EVIDENCE_execution_attempt_stderr.log`):

```json
{"error_code":"PICOGK_RUNTIME_UNAVAILABLE","message":"System.Exception: Failed to load PicoGK library\n   at PicoGK.Library.GlobalInstance..ctor(...)\n   at PicoGK.Library.Go(...)\n   at BioMatCadGeometryWorker.GyroidScaffoldBuilder.BuildAndExport(...)\n   at Program.<Main>$(String[] args)"}
```

Log interno do PicoGK (stdout, ver `EVIDENCE_execution_attempt_stdout.log`), com o
`DllNotFoundException` completo:

```text
System.DllNotFoundException: Unable to load shared library 'picogk.26.2' or one of its
dependencies. ...
/tmp/dotnet/shared/Microsoft.NETCore.App/9.0.18/picogk.26.2.so: cannot open shared object
file: No such file or directory
... (mesma falha testada em 6 caminhos de busca diferentes) ...
   at PicoGK.Library._hCreateInstance(Single fVoxelSizeMM)
   at PicoGK.Library..ctor(Single fVoxelSizeMM)
   at PicoGK.Library.GlobalInstance..ctor(...)
```

PicoGK internamente captura a `DllNotFoundException` e relança uma `System.Exception` genérica
("Failed to load PicoGK library") -- o worker detecta esse caso (por tipo de exceção, por
`InnerException`, e por conteúdo textual da mensagem/stack trace) e classifica corretamente
como `PICOGK_RUNTIME_UNAVAILABLE`, nunca como sucesso.

## 6. O que É testável nesta sessão (44/44 xunit passando, Incremento 2.1.1)

`tests/BioMatCadGeometryWorker.Tests` compila e executa apenas os arquivos independentes de
PicoGK (`GyroidMath.cs`, `JobEnvelope.cs`, `SimpleMesh.cs`, `GeometryMetricsCalculator.cs`,
`StlExporter.cs`):

```text
$ dotnet test
Passed!  - Failed: 0, Passed: 44, Skipped: 0, Total: 44
```

Cobrindo (Incremento 2.1, 9 testes originais + Incremento 2.1.1, 35 testes novos/ampliados):
volume/área/watertight de um cubo unitário conhecido, bounding box, estimativa de porosidade
(incluindo clamping), volume de domínio block/cilindro, detecção de malha não fechada, formato
binário STL, (de)serialização JSON do contrato de job (Incremento 2.1); e, novo no Incremento
2.1.1 — `GyroidMathTests.cs` (27 testes): avaliação do campo gyroid de Schoen, SDF exata de
bloco/cilindro, interseção booleana implícita via `max()`, conversão determinística
`wall_thickness_mm` ↔ meia-largura de banda, mapeamento seed→deslocamento de fase, estimativa de
fração sólida por amostragem em grade, calibração de porosidade por bisseção (casos convergentes
e de borda), piso de voxel size em modo preview, estimativas prévias de voxel/memória —
`SimpleMeshWeldTests.cs` (5 testes): solda de vértices duplicados, preservação de topologia,
idempotência sobre malha já soldada.

## 7. O que NÃO é testável neste ambiente

- Geração real de um scaffold Gyroid via `Voxels`/`Mesh` do PicoGK -- incluindo se o domínio
  cilíndrico corrigido (Incremento 2.1.1, SDF real em vez de bounding box) de fato recorta a
  malha voxelizada como esperado.
- Se a conversão `wall_thickness_mm` -> meia-largura de banda (`GyroidMath.
  WallThicknessMmToHalfBandWidth`, Incremento 2.1.1) produz, numa malha voxelizada real, uma
  espessura de parede visualmente/dimensionalmente condizente com o valor solicitado.
- Se a calibração de porosidade por bisseção (`CalibratePorosityByBisection`, Incremento 2.1.1)
  produz, numa malha real, uma porosidade medida (`GeometryMetricsCalculator`) próxima do alvo
  solicitado -- só a estimativa analítica interna foi testada, não a porosidade medida na malha
  final.
- Determinismo geométrico real (mesma seed + mesma receita -> mesmo STL) -- só o contrato
  (mesmo JSON de entrada, e o mapeamento determinístico seed->fase testado isoladamente) é
  testável, não a geometria de saída em si.
- Geração de thumbnail (depende de execução real).
- Exportação VDB (depende de execução real E de suporte oficial confirmado do PicoGK a VDB) --
  Incremento 2.1.1 adicionou rejeição estruturada `OUTPUT_FORMAT_UNSUPPORTED` para não
  silenciosamente ignorar `vdb` quando não suportado, mas o caminho de sucesso de exportação VDB
  em si permanece não verificável neste ambiente.
- Se a solda de vértices (`SimpleMesh.Weld()`, Incremento 2.1.1) produz, numa malha real do
  PicoGK, uma contagem de vértices coerente entre o STL exportado e o manifesto -- testado até
  agora apenas contra malhas sintéticas de teste (`SimpleMeshWeldTests.cs`).
- Qualquer verificação end-to-end da API chamando o worker real com sucesso -- o teste
  `test_dispatch_job_real_worker_fails_in_blocked_environment` (Python) prova o caminho de
  falha real, não um caminho de sucesso.

## 8. Caminhos de desbloqueio não tentados nesta sessão

- Executar em Windows/macOS (onde o pacote 2.2.0 traz runtime nativo oficial).
- Compilar o runtime nativo do PicoGK a partir do código-fonte C++ para linux-x64.

## 9. Reprodução

```bash
cd apps/geometry-worker
dotnet build
mkdir -p ~/Documents   # PicoGK grava um log aqui; sem este diretório o erro é mascarado
dotnet bin/Debug/net9.0/BioMatCadGeometryWorker.dll <caminho-para-job.json>
# esperado: exit code 1, stderr com error_code=PICOGK_RUNTIME_UNAVAILABLE (em linux-x64)

cd tests/BioMatCadGeometryWorker.Tests
dotnet test
# esperado: 48/48 passando (não depende do runtime nativo)
```

## 9.1 Bug real encontrado e corrigido nesta sessão (reexecução real do build+worker)

Ao reexecutar de verdade o build e uma tentativa de execução do worker contra a golden recipe
`block-gyroid-v1.json` nesta sessão (não apenas reler evidência anterior), a limpeza de
artefatos parciais (`CleanupPartialOutputs`, chamada em qualquer falha, incluindo a
`PICOGK_RUNTIME_UNAVAILABLE` esperada neste sandbox) apagava **todos** os arquivos de
`output_dir` -- incluindo o próprio `job.json` de entrada, porque `worker_client.py` grava
`output_dir / "job.json"` (o envelope de entrada vive dentro do mesmo diretório que a limpeza
varre). Reproduzido de forma determinística: rodar o worker contra um `job.json` dentro do seu
próprio `output_dir` e confirmar que ele desaparece após a falha.

Efeito prático: depois de uma falha, o diretório de evidência da execução perdia a receita de
entrada que efetivamente rodou -- prejudica auditoria pós-morte de falhas em produção (não é um
problema de segurança, mas é um problema real de rastreabilidade, relevante para os itens 3 e 11
do checklist de aceite).

Corrigido: lógica extraída para `OutputCleanup.cs` (testável isoladamente, sem depender do
PicoGK), preservando explicitamente `job.json` da limpeza. 4 novos testes xUnit
(`OutputCleanupTests.cs`) cobrem: preserva `job.json` mas remove outros arquivos; diretório só
com `job.json` não remove nada; diretório inexistente não lança exceção; diretório vazio não
remove nada. Total agora: 48/48 testes xUnit passando. Reexecutado o cenário real depois da
correção -- `job.json` agora sobrevive à falha esperada (`PICOGK_RUNTIME_UNAVAILABLE`,
reproduzida de forma idêntica à evidência anterior, confirmando que o bloqueio em si não mudou,
apenas o efeito colateral indevido da limpeza foi corrigido).

## 10. Caminho de fechamento (Incremento 2.1.1)

Para provar de verdade as correções listadas na seção 6 contra uma execução real do PicoGK,
siga `docs/examples/WINDOWS_EXECUTION_KIT.md` num Windows x64 real. Esse guia usa
`apps/geometry-worker/tools/New-JobFromRecipe.ps1` para montar um `job.json` a partir de uma
golden recipe, e `scripts/audit_stl_vs_worker_output.py` para recomputar de forma independente
(Python) as métricas do STL resultante, para conferência cruzada contra o manifesto.
