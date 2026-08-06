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

## 10. EXECUÇÃO REAL BEM-SUCEDIDA -- `block-gyroid-v1` no Windows x64 (marco desta sessão; **evidência ANTERIOR à correção de calibração de porosidade da seção 10.2 -- ver rótulo abaixo**)

Pela primeira vez neste projeto, o worker rodou de verdade contra o PicoGK real e produziu uma
malha real, reportado pelo usuário a partir de sua própria máquina Windows x64:

```text
ExitCode:              0
PicoGK Core:            26.2.0 (pacote NuGet 2.2.0)
STL:                    10.428.084 bytes
STL SHA-256:            cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d
Triângulos:             208.560
Vértices únicos:        102.338
Watertight:             sim
Validação de recarga do STL: aprovada
Porosidade alvo:        60%
Porosidade medida:      58,669879%
Calibração:             convergiu
Erro residual:          -1,330121 p.p.
```

**O que isto prova de verdade**: a fórmula de Schoen, a interseção booleana implícita
(domínio bloco), a aplicação de `wall_thickness_mm`, a calibração de porosidade por bisseção, e
a solda de vértices (sem o padrão antigo de vértices = 3×triângulos) funcionam de fato contra o
PicoGK real -- não apenas nos 50 testes xUnit matemáticos isolados.

**O que isto NÃO provou ainda nesta rodada específica**: `cylinder-gyroid-v1` e
`preview-gyroid-low-res-v1` foram executados numa rodada SEGUINTE (ver seção 10.2 abaixo), que
revelou um problema real na calibração de porosidade -- corrigido na seção 10.3. Determinismo
binário (mesma receita+seed rodada duas vezes, comparando SHA-256) **foi** confirmado pelo
usuário para `block-gyroid-v1` (ver seção 10.2). Nenhum `manifest.json` foi gerado em nenhuma
das rodadas (execuções diretas do worker via CLI, fora do fluxo API→dispatcher→manifesto).

**IMPORTANTE -- rótulo de evidência**: os números do bloco acima (STL SHA-256
`cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d`) foram produzidos ANTES da
correção de calibração de porosidade descrita nas seções 10.2/10.3. O bloco em si (geometria,
watertight, vértices, SHA-256, auditoria independente aprovada) permanece válido como evidência
de execução real -- só a calibração de porosidade daquele run específico usa o código ANTIGO
(analítico, sem conferência contra a malha real). Preservado aqui sem alteração, exatamente como
recebido -- nunca "corrigido" manualmente.

## 10.1 Bug operacional real encontrado nesta execução: viewer exigia fechamento manual

O usuário relatou que `scaffold.stl` ficou pronto por volta de 15:48:01, mas o processo só
encerrou às 15:50:07, depois de fechar manualmente a janela branca do visualizador do PicoGK --
os 127 segundos de `duration_seconds` reportados incluíam esse tempo de espera humana, não
apenas geração geométrica.

Antes de alterar qualquer coisa, a assinatura real de `PicoGK.Library.Go` no pacote 2.2.0
efetivamente instalado foi inspecionada nesta sessão por **reflexão contra o `PicoGK.dll` real**
(não por suposição nem documentação histórica genérica):

```text
Go(Single fVoxelSizeMM, ThreadStart fnTask, String strLogFilePath = "",
   Boolean bEndAppWithTask = false, String strWindowTitle = "PicoGK", String strLightsFile = "")
```

O XML doc do próprio pacote (`PicoGK.xml`, embutido no NuGet) confirma:
`bEndAppWithTask`: "If true, the viewer exits when your task is done." É o único mecanismo
oficial e documentado para o viewer encerrar sozinho -- não existe, nesta versão, nenhuma opção
de execução verdadeiramente headless/sem janela (conferido: nenhuma menção a "headless" em todo
o XML doc do pacote).

O worker (`GyroidScaffoldBuilder.cs`) chamava `Library.Go(...)` usando apenas os dois primeiros
parâmetros posicionais, deixando `bEndAppWithTask` no valor padrão `false` -- daí o
comportamento relatado. Corrigido: `bEndAppWithTask: true` passado explicitamente como argumento
nomeado. Como `stopwatch.Stop()` (`Program.cs`) só roda depois que `BuildAndExport` retorna, e
`BuildAndExport` só retorna depois que `Library.Go` retorna, isso também corrige `duration_seconds`
para medir só a execução útil, sem esperar fechamento manual.

Esta correção **não pôde ser validada em runtime neste sandbox** (a exceção
`PICOGK_RUNTIME_UNAVAILABLE` acontece antes do corpo de `Library.Go` executar, então o
comportamento do viewer nunca chega a ser exercitado aqui) -- validado apenas por: (a) reflexão
real confirmando que o parâmetro existe, tem esse nome e esse comportamento documentado; (b)
`dotnet build` sem erros; (c) 2 novos testes de guarda de configuração
(`LibraryGoConfigurationTests.cs`) que leem o código-fonte real de `GyroidScaffoldBuilder.cs` e
falham se `bEndAppWithTask: true` for removido (sanidade confirmada nesta sessão: revertendo a
correção manualmente, o teste falha como esperado; restaurando, volta a passar). A confirmação
final de que o viewer realmente fecha sozinho e `duration_seconds` reflete só o tempo útil
depende de uma nova execução real do usuário no Windows.

## 10.2 EXECUÇÃO REAL das três golden recipes -- `cylinder-gyroid-v1` e `preview-gyroid-low-res-v1`
(evidência ANTERIOR à correção de calibração da seção 10.3)

Numa rodada seguinte, o usuário executou de verdade as três golden recipes no Windows x64.
Reportado tal como recebido, sem qualquer alteração manual dos números:

```text
BLOCK (block-gyroid-v1) -- repete o run da seção 10, agora com determinismo confirmado:
  Alvo:                60%
  Medido:              58,669879%
  Erro:                -1,330121 p.p.
  Watertight:           sim
  Auditoria independente: aprovada
  Determinismo binário: CONFIRMADO em duas execuções (mesmo SHA-256 nas duas)
  STL SHA-256:          cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d

CYLINDER (cylinder-gyroid-v1):
  Alvo:                55%
  Medido:              52,756863%
  Erro:                -2,243137 p.p.
  Watertight:           sim
  Auditoria independente: aprovada
  Contenção cilíndrica: verificada em 1.486.788 vértices, ZERO violações radiais e em Z
  STL SHA-256:          6004d7c1f1075e504ff6a25abd86b3118f54bf15dfb7364c5d8b34cdb5f61810

PREVIEW (preview-gyroid-low-res-v1):
  Alvo:                60%
  Estimativa analítica: 59,402332%
  Medido no STL:        78,804521%
  Erro REAL:           +18,804521 p.p.
  "porosity_calibration_converged=true" declarado pelo worker -- ENGANOSO, refere-se apenas à
    estimativa analítica, não à malha real
  Watertight:           sim
  Auditoria STL vs. métricas: aprovada (métricas internamente consistentes com o STL, mesmo
    estando erradas em relação ao alvo de porosidade)
  STL SHA-256:          14a46df73731e09c6fb9712702945fcc4c211ad11f0e8d3a8af8d6ded832455d
```

**Avaliação honesta por receita**:

- **Bloco**: **APROVADO**. Geometria real, watertight, auditoria independente aprovada,
  determinismo binário confirmado, porosidade dentro de uma margem pequena (-1,33 p.p.).
- **Cilindro**: **geometria APROVADA** (recorte cilíndrico real -- SDF, não bounding box --
  contenção verificada em quase 1,5 milhão de vértices com zero violação, watertight, auditoria
  independente aprovada). **Porosidade precisa de refinamento**: -2,24 p.p. de erro é maior que a
  tolerância de modo final agora definida (2,0 p.p., ver seção 10.3) -- marginalmente fora.
- **Preview**: **REPROVADO quanto à porosidade**. Erro real de +18,80 pontos percentuais é
  inaceitável sob qualquer tolerância razoável (a tolerância de preview definida na seção 10.3 é
  5,0 p.p.) -- este é o caso que expôs a causa raiz: a calibração antiga só conferia contra a
  estimativa analítica contínua, nunca contra a malha real discretizada, e por isso declarava
  convergência de forma cientificamente falsa.

Nenhum destes três SHA-256/STLs foi ou será substituído -- permanecem como evidência real do
comportamento ANTERIOR à correção de calibração, exatamente para que a comparação com as
próximas execuções (pós-correção) seja honesta e verificável.

## 10.3 Causa raiz e correção: calibração de porosidade agora é fechada contra a malha real

**Causa raiz**: `GyroidMath.CalibratePorosityByBisection` (calibração analítica) usa
`EstimateSolidFractionForBand` -- uma estimativa CONTÍNUA por amostragem em grade sobre o campo
gyroid puro, sem qualquer voxelização real -- como único oráculo de medição. O worker declarava
`porosity_calibration_converged=true` baseado SOMENTE nessa estimativa contínua convergir,
mesmo sem nunca conferir o resultado contra a malha efetivamente gerada pelo PicoGK. Em modo
`final` (voxel size mais fino), a estimativa contínua aproxima razoavelmente a malha discretizada
resultante (erros de -1,33 e -2,24 p.p. nos casos reais). Em modo `preview` (voxel size com piso
de 0.3mm, deliberadamente mais grosseiro -- `GyroidMath.PreviewMinVoxelSizeMm`), a discretização
grosseira faz a malha real divergir MUITO da estimativa contínua (erro real de +18,80 p.p.) --
mas o worker nunca detectava isso, porque nunca comparava a estimativa contra a malha real.

**Correção** (`GyroidMath.cs`, `GyroidScaffoldBuilder.cs`, `JobEnvelope.cs`, `Program.cs`,
`PorosityCalibrationExceptions.cs` -- ver commit desta correção):

1. Novo método genérico `GyroidMath.CalibrateByMonotonicBisection` -- bisseção monotônica sobre
   um oráculo de MEDIÇÃO injetado (testável com oráculos sintéticos sem PicoGK; em produção, o
   oráculo real gera Voxels+Mesh de verdade a cada candidato de espessura e mede o volume real).
2. `GyroidScaffoldBuilder.BuildAndExport` agora, quando `target_porosity_pct` é solicitado: usa a
   calibração analítica só como palpite inicial (Passo 1), depois roda a calibração FECHADA
   (Passo 2) -- cada iteração gera Voxels+Mesh reais (descartados via `using`/`Dispose()` entre
   iterações, para não acumular memória nativa), mede a porosidade real, e ajusta
   `wall_thickness_effective_mm` por bisseção até convergir dentro da tolerância MEDIDA ou atingir
   o máximo de iterações (`GyroidMath.DefaultMeshCalibrationMaxIterations = 12`).
3. Tolerâncias explícitas por modo: `final` = 2,0 pontos percentuais,
   `preview` = 5,0 pontos percentuais (`GyroidMath.DefaultPorosityToleranceFinalPctPoints` /
   `DefaultPorosityTolerancePreviewPctPoints`).
4. Se a calibração fechada NÃO converge dentro da tolerância medida, o worker lança
   `PorosityTargetNotReachedException` ANTES de soldar/exportar qualquer STL -- Program.cs
   mapeia isso para o erro estruturado `POROSITY_TARGET_NOT_REACHED` (com `measured_porosity_pct`,
   `porosity_tolerance_pct_points`, `measured_porosity_error_pct_points` e
   `mesh_calibration_iterations` nos detalhes). Nunca finge sucesso científico.
5. Saída JSON agora distingue explicitamente: `analytical_porosity_estimate_pct` /
   `analytical_calibration_converged` (Passo 1, só um palpite) vs. `measured_porosity_pct` /
   `porosity_tolerance_pct_points` / `measured_porosity_error_pct_points` /
   `measured_porosity_within_tolerance` / `mesh_calibration_iterations` (Passo 2, valor de
   referência definitivo, calculado sobre a MESMA malha soldada gravada no STL).

**Testes**: 12 novos testes xUnit (`MonotonicPorosityCalibrationTests.cs`) cobrindo os cenários
pedidos -- divergência analítico-vs-medido (didático, inspirado no caso real de preview),
convergência dentro de ±2pp (cenários tipo bloco e tipo cilindro), convergência dentro de ±5pp
(tipo preview, incluindo um teste que prova a diferença prática entre as duas tolerâncias com o
mesmo oráculo), falha quando o alvo é inatingível, invariante "nunca `Converged=true` fora da
tolerância medida" (testada contra 5 cenários distintos), determinismo do algoritmo, e validação
de limites inválidos. Total: 62/62 testes xUnit passando (antes desta correção: 50/50).

**O que esta correção NÃO prova ainda**: o código foi corrigido e testado com oráculos
SINTÉTICOS (sem PicoGK, exatamente como toda a matemática de `GyroidMath.cs`). A calibração
FECHADA rodando de verdade contra Voxels/Mesh reais do PicoGK -- e confirmando que as três
receitas agora convergem dentro da tolerância medida -- depende de uma NOVA execução real do
usuário no Windows com o código corrigido. Os SHA-256 das seções 10 e 10.2 são anteriores a esta
correção e não devem ser reutilizados como prova do código novo.

## 10.4 EXECUÇÃO REAL PÓS-CORREÇÃO -- as 3 golden recipes APROVADAS (commit `da75219`)

Depois da correção de calibração de porosidade descrita na seção 10.3, o usuário reexecutou de
verdade as três golden recipes no Windows x64, contra o worker compilado no commit `da75219`.
Resultados transcritos literalmente, tal como recebidos, sem qualquer alteração:

### Build e testes

```text
Build Release: aprovado
xUnit:         62/62 aprovados, 0 falhas
```

### Calibração de porosidade fechada contra a malha real -- por receita

```text
BLOCK (block-gyroid-v1):
  Alvo:                    60%
  Medido:                  58,6698791858207%
  Erro:                    -1,3301208141793026 pp
  Tolerância (modo final): 2 pp
  Iterações de calibração por malha: 1
  SHA-256 do STL:          cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d

CYLINDER (cylinder-gyroid-v1):
  Alvo:                    55%
  Medido:                  55,75526607688106%
  Erro:                    +0,7552660768810568 pp
  Tolerância (modo final): 2 pp
  Iterações de calibração por malha: 5
  SHA-256 do STL:          2cb8cbdf9acbff579c838d8bf3cc2e2a688bcd33a3c475945174272cb278445e

PREVIEW (preview-gyroid-low-res-v1):
  Alvo:                    60%
  Medido:                  56,733228138231375%
  Erro:                    -3,2667718617686248 pp
  Tolerância (modo preview): 5 pp
  Iterações de calibração por malha: 4
  SHA-256 do STL:          7660dae3ee263445835bbf9d26c16fa4ef8f8ee2fd2c320000b0546c1eaaba78
```

Todas as três dentro da tolerância MEDIDA (não apenas da estimativa analítica) -- exatamente o
comportamento que a correção da seção 10.3 pretendia garantir. `porosity_calibration_converged`/
`measured_porosity_within_tolerance` agora refletem a realidade da malha, não uma estimativa
contínua otimista.

**Observação de consistência (conferida nesta sessão, não apenas transcrita)**: o SHA-256 do
bloco é **idêntico** ao SHA-256 obtido na execução PRÉ-correção (seção 10.2). Isso é consistente
e esperado, não uma coincidência suspeita: o bloco convergiu em **1 iteração** de calibração por
malha, ou seja, o palpite inicial (a mesma calibração analítica de sempre, usada como Passo 1 em
ambas as versões do código) já estava dentro da tolerância medida -- então `wall_thickness_effective_mm`
não mudou, e a malha resultante é bit-a-bit a mesma. Cilindro (5 iterações) e preview (4
iterações) precisaram de fato refinar o palpite inicial, e por isso têm SHA-256 diferentes das
execuções pré-correção (`6004d7c1...` e `14a46df7...`, respectivamente) -- exatamente o
comportamento esperado de uma calibração que agora itera de verdade contra a malha real.

### Auditoria independente (`scripts/audit_stl_vs_worker_output.py`)

```text
Três STLs recalculados diretamente pela ferramenta independente (Python, sem PicoGK).
Nenhuma divergência encontrada contra a saída do worker, nas três receitas.
AuditExitCode = 0 nas três (bloco, cilindro, preview).
Watertight = verdadeiro nas três.
```

Fecha definitivamente o item 10 do checklist de aceite (métricas coerentes com o STL) para as
três receitas -- a mesma ferramenta corrigida nesta sessão para lidar com UTF-8/UTF-16 e logs
misturados (ver seção 10.3) foi usada de verdade contra os artefatos reais e não encontrou
divergência.

### Determinismo pós-correção

```text
Segunda execução real das três receitas (mesma receita+seed+worker+plataforma).
Hashes Run1 e Run2: idênticos, nas três receitas.
DeterminismoGlobal = True.
```

Fecha o item 12 do checklist de aceite (determinismo geométrico) para o código corrigido -- não
apenas para o bloco pré-correção como antes, mas para as três receitas com a calibração fechada.

### Contenção cilíndrica pós-correção

```text
Triângulos:        493.664
Vértices examinados: 1.480.992
Raio máximo:       4,999950394 mm (domínio: raio 5mm -- consistente com a superfície ficando
                    ligeiramente dentro do limite por discretização de voxel, não fora dele)
Intervalo Z:       [-6, +6] mm (domínio: altura 12mm, centrada -- consistente com a convenção
                    de bbox documentada em GyroidScaffoldBuilder.cs)
Violações radiais: 0
Violações em Z:    0
ContainmentExitCode = 0
```

**Nota de honestidade sobre a ferramenta usada**: esta verificação específica de contenção
radial/em-Z NÃO foi gerada por `scripts/audit_stl_vs_worker_output.py` deste repositório -- essa
ferramenta (descrita nas seções acima) verifica volume/área/vértices/triângulos/watertight/
SHA-256, mas não inclui uma checagem geométrica dedicada de "todo vértice está dentro do raio e
da faixa Z do domínio". Os números acima foram relatados pelo usuário a partir de uma verificação
adicional própria (fora do escopo dos scripts entregues nesta sessão) e são registrados aqui tal
como recebidos, sem inventar qual ferramenta os produziu. Ainda assim, os valores são
plausíveis e consistentes com a geometria esperada (raio máximo ligeiramente abaixo de 5mm,
faixa Z simétrica em torno de zero para altura 12mm) -- não há motivo para desconfiar deles, mas
também não devem ser atribuídos a uma ferramenta específica deste repositório sem essa ressalva.

### Veredito final por receita (pós-correção)

- **Bloco**: **APROVADO** (geometria, calibração, auditoria, determinismo).
- **Cilindro**: **APROVADO** (geometria, calibração de porosidade agora dentro da tolerância,
  contenção radial/Z com zero violações, auditoria, determinismo).
- **Preview**: **APROVADO** (geometria, calibração de porosidade agora dentro da tolerância de
  modo preview, auditoria, determinismo).

Todas as pendências de geometria/calibração/auditoria/determinismo/contenção identificadas nas
seções 10/10.2 estão fechadas para as três golden recipes. As correções de código (calibração
fechada, `bEndAppWithTask: true`, `OutputCleanup.cs`) estão agora provadas de verdade contra o
PicoGK real, não apenas testadas matematicamente.

## 11. Caminho de fechamento (Incremento 2.1.1)

A seção 10.4 fechou, com prova real contra o PicoGK: calibração de porosidade fechada (bloco,
cilindro, preview), auditoria independente (3/3), determinismo pós-correção (3/3), e contenção
cilíndrica (zero violações).

**Atualização final (2026-07-29)**: os critérios que faltavam nesta seção foram todos fechados
com execução real no Windows do usuário, na mesma sessão:

- **Validação da interface integrada + E2E Playwright real**: aprovado (`2 passed`,
  `PlaywrightExitCode=0`, commit `f7a9614` -- ver `apps/web/e2e/README.md` e
  `TEST_EVIDENCE.md` §11). O bloqueio permanece verdadeiro apenas neste sandbox Linux
  (bibliotecas nativas do Chromium ausentes, `sudo` desabilitado).
- **Consistência STL-vs-manifesto via fluxo completo API→dispatcher→worker PicoGK
  real→Artifact→Manifest→download**: aprovado. Gate final
  (`apps/api/scripts/verify_full_pipeline_sha256.py`, automatizado por
  `scripts/Run-FinalGate.ps1`) executado com um job NOVO via HTTP real (nunca invocação direta
  do worker via CLI, nunca pré-semeado, nenhuma simulação): transição real
  `queued→running→succeeded`, SHA-256
  `cd97e3c2be2029fe54bb4743217254a7ecb769ba24b81bf737d76e73bbc1565d` idêntico em 5 fontes
  (STL físico, Artifact via API, Artifact via DB, Manifest, download via API), métricas
  (`porosity_pct_measured=58.6698791858207`, `vertex_count_unique=102338`, `is_watertight=true`)
  e auditoria (`geometry_job_created`, `geometry_job_succeeded`) confirmadas -- ver
  `TEST_EVIDENCE.md` §16 para a transcrição literal completa.
- **Empacotamento final v2.2.1**: único item ainda pendente no momento em que esta seção foi
  escrita, gerado nesta mesma rodada de trabalho (ver `TEST_EVIDENCE.md`/`IMPLEMENTATION_STATUS.md`
  para o estado mais atual).

**Com geometria real, interface real (E2E) e fluxo de produção completo real (gate final)
todos provados independentemente, a vertical completa do Incremento 2.1.1 está aprovada.**

## 12. Rodada Voronoi 20260806-133141 — auditoria real do WORKER_TIMEOUT (bEndAppWithTask REFUTADO como causa; hang aponta para dentro do próprio Library.Go)

Contexto: a validação Windows real desta rodada (evidência em
`C:\biomatcad-runs\voronoi-validation-staged-20260806-133141\pilot`) reproduziu o WORKER_TIMEOUT
de `block-voronoi-preview-v1` em 2/2 execuções (66.7s e 65.5s), enquanto `preview-gyroid-low-res-v1`,
executado imediatamente depois, passou 2/2 com determinismo confirmado (SHA-256 idêntico). A
correção de processos órfãos da rodada anterior (20260806-112714) funcionou corretamente: nenhuma
árvore `dotnet.exe` órfã antes/depois de nenhuma execução, e o Gyroid de controle não sofreu
cascata.

**Nova hipótese do usuário**: o stdout capturado no momento do timeout já continha um JSON de
resultado quase completo (`mesh_calibration_iterations: 3`, `measured_porosity_within_tolerance:
true`, `estimated_voxel_count: 15625` etc.) -- sugerindo que o cálculo terminou, mas o processo
não encerrou. Hipótese prioritária levantada: `VoronoiScaffoldBuilder.cs` poderia estar deixando
`bEndAppWithTask` no valor padrão `false` (ao contrário do Gyroid, corrigido na seção 10.1).

**Auditoria real realizada nesta rodada** (não suposição -- comparação literal do código-fonte
vivo + reflexão + decompilação real contra o PicoGK.dll 2.2.0 instalado via NuGet):

1. `VoronoiScaffoldBuilder.cs` linha ~268: `Library.Go((float)voxelSizeEffectiveMm, () => { ... },
   bEndAppWithTask: true);` -- **já passa `bEndAppWithTask: true` explicitamente**, de forma
   estruturalmente IDÊNTICA à chamada em `GyroidScaffoldBuilder.cs`. A hipótese de "parâmetro
   deixado no padrão `false`" está **REFUTADA** por leitura direta do arquivo-fonte atual (não
   uma versão em cache/desatualizada).
2. Dispose de `Voxels`/`Mesh`: ambos os arquivos usam `using var candidateVoxels = new
   Voxels(...)` e `using var candidateMeshObj = new Mesh(...)` de forma idêntica -- confirmado
   por reflexão contra `PicoGK.dll` que ambos os tipos implementam `IDisposable` com um único
   método público `Dispose()`. Nenhuma diferença de padrão de descarte entre os dois arquivos.
3. Nenhum dos dois arquivos referencia `Library.oViewer`/`Viewer.Add(...)` em nenhum lugar --
   nenhuma malha/voxel é adicionada explicitamente ao viewer para exibição em nenhum dos dois
   casos, então "quantidade de geometria renderizada" não é uma diferença de código entre eles.
4. **Decompilação real do corpo de `PicoGK.Library.Go`** (via `ilspycmd` contra o
   `PicoGK.dll` 2.2.0 realmente instalado -- não documentação, não suposição) revelou o mecanismo
   exato:

   ```csharp
   public static void Go(float fVoxelSizeMM, ThreadStart fnTask, string strLogFilePath = "",
       bool bEndAppWithTask = false, string strWindowTitle = "PicoGK", string strLightsFile = "")
   {
       ...
       using GlobalInstance globalInstance = new GlobalInstance(fVoxelSizeMM, strLogFilePath, strWindowTitle, strLightsFile);
       Thread thread = new Thread(fnTask);
       thread.Start();
       while (globalInstance.oViewer.bPoll())
       {
           Thread.Sleep(5);
           if (bEndAppWithTask && !thread.IsAlive && globalInstance.oViewer.bIsIdle())
           {
               break;
           }
       }
       EndTask();
       while (thread.IsAlive)
       {
           globalInstance.oViewer.bPoll();
           Thread.Sleep(5);
           ...
       }
       m_bAppExit = true;
   }
   ```

   Ou seja: mesmo com `bEndAppWithTask: true`, `Go()` só retorna quando (a) a thread da tarefa
   (`fnTask`) realmente termina (`!thread.IsAlive`) **E** (b) o viewer nativo reporta-se `bIsIdle()`
   dentro do primeiro laço -- e, adicionalmente, o SEGUNDO laço (`while (thread.IsAlive)`, que
   roda incondicionalmente, independente de `bEndAppWithTask`) só sai quando a thread de fato
   termina. `bEndAppWithTask: true` é necessário mas não suficiente por si só -- ele não
   controla nada além de UMA das condições de saída do primeiro laço; o encerramento real do
   processo continua dependendo do estado interno do viewer nativo (`bPoll()`/`bIsIdle()`),
   que é código nativo (`picogk.26.2.dll`) fora do alcance de qualquer parâmetro C# que
   possamos passar.

**Evidência adicional que restringe onde o hang acontece**: o JSON parcial capturado no stdout
do WORKER_TIMEOUT real inclui campos (`estimated_voxel_count`, `estimated_memory_mb_upper_bound`)
que só são serializados em `Program.cs` DEPOIS que `topologyProvider.BuildAndExport(...)` (e,
portanto, `Library.Go(...)`) já retornou -- ou seja, a evidência real sugere que TODO o cálculo,
incluindo o retorno de `Library.Go`, a validação do STL, o hash SHA-256 e a serialização do JSON
final já haviam ocorrido, e o processo .NET simplesmente não encerrou sozinho depois disso
(`Main()` retornaria `0`, mas o processo do SO continua vivo até o watchdog externo confirmar
o encerramento da árvore).

**Conclusão honesta desta rodada**: a hipótese específica de "bEndAppWithTask deixado em `false`"
está refutada -- ambos os arquivos já o configuram corretamente e de forma idêntica. A causa mais
provável, dada a decompilação real acima, é um comportamento do PRÓPRIO PicoGK.Library.Go (ou do
viewer nativo `picogk.26.2.dll` que ele encapsula) que não está sob controle de nenhum parâmetro
que o código de aplicação possa ajustar -- possivelmente correlacionado com a maior
complexidade/fragmentação da malha de voxels gerada pelo Voronoi (muitos primitivos pequenos
unidos por smooth-min, sem estrutura de aceleração espacial, já documentado como limitação
conhecida no cabeçalho de `VoronoiScaffoldBuilder.cs`) versus a superfície TPMS contínua e única
do Gyroid. Isso NÃO foi provado de forma definitiva (não é possível instrumentar/depurar o
processo nativo a partir deste sandbox Linux, que nem sequer consegue executar o PicoGK real) --
permanece como a explicação mais bem fundamentada disponível, não uma conclusão fechada. Não é
recomendado aumentar o timeout como "solução": se a causa for um hang genuíno (não apenas lento),
nenhum timeout maior resolveria -- apenas adiaria a detecção.

**O que FOI corrigido nesta rodada, independente da causa do hang**:

- O stdout/stderr completo do worker (nunca truncado) agora é preservado em um arquivo próprio
  (`_worker_diagnostics/<job_id>.json`, irmão de `output_dir`, sobrevive à limpeza de artefatos
  parciais) -- ver `worker_client.py::_write_full_diagnostics_file` e
  `test_worker_timeout_recovery.py` (2 novos testes).
- Regressão permanente: `AllTopologyProvidersLibraryGoConfigurationTests.cs` escaneia TODOS os
  arquivos-fonte reais de `apps/geometry-worker` (não apenas o Gyroid) e falha se qualquer
  chamada real a `Library.Go(` for encontrada sem `bEndAppWithTask: true` -- protege contra
  regressão em qualquer provider futuro.

**Próximo passo recomendado (fora do alcance deste sandbox)**: investigar o hang diretamente no
Windows com um profiler/depurador nativo anexado ao processo `dotnet.exe` no momento do timeout
(ex.: Process Explorer para inspecionar threads vivas, ou um dump de memória), para confirmar se
o thread travado é o loop de `bPoll()` do viewer nativo ou algum outro mecanismo interno do
PicoGK -- não realizável a partir deste ambiente Linux, que não executa o runtime nativo do
PicoGK (ver seção 4).

## 13. Rodada de prova direta (pós-commit `d13c691`) -- roteiro `Run-VoronoiDirectWorkerProbe.ps1`

O usuário instruiu explicitamente que a hipótese "está fora do alcance da aplicação" (seção 12)
não deve ser aceita como conclusão final: mesmo que a thread persistente seja interna ao
PicoGK, o `geometry-worker` é um processo CLI de job único e deve garantir término
determinístico. Antes de qualquer correção de código (que só faz sentido se a causa for
confirmada por prova direta, não apenas pela evidência indireta já disponível), esta rodada
prepara uma **prova direta e isolada**, sem API, sem dispatcher e sem o mecanismo de
`WORKER_TIMEOUT` externo:

- `apps/api/scripts/build_worker_job_json.py` (novo): constrói um `job.json` real usando a
  MESMA canonicalização (`validate_and_canonicalize`) que a API de produção usa -- nenhuma
  golden recipe é alterada, apenas processada como sempre foi.
- `scripts/Run-VoronoiDirectWorkerProbe.ps1` (novo): invoca `dotnet BioMatCadGeometryWorker.dll
  job.json` diretamente, redireciona stdout/stderr completos (UTF-8, nunca truncados) para
  arquivos, e monitora em paralelo: aparecimento do marcador `[DIAG_MARKER]
  library_go_returned_at_utc=...` (novo, ver `Program.cs`, emitido em stderr imediatamente após
  `topologyProvider.BuildAndExport(...)` retornar -- isola o tempo gasto dentro de
  `Library.Go`/PicoGK do tempo gasto depois), aparecimento de um JSON final válido em stdout,
  existência e tamanho do `scaffold.stl`, e uma tentativa real de reabrir esse STL para leitura
  (prova de que o arquivo está de fato fechado/legível, não apenas "existe"). Quando um
  resultado completo (JSON + STL) é detectado, aguarda mais 15s (parametrizável) SEM matar nada,
  e só então -- se o processo ainda estiver vivo -- captura uma amostra de threads do SO
  (melhor esforço) e encerra APENAS a árvore de processos que ele mesmo iniciou (nunca um
  `taskkill` global, nunca processos não rastreados). Grava um relatório JSON estruturado com
  todos os tempos/estados medidos.

**Validação da lógica de detecção/temporização feita nesta sessão** (sem PicoGK real, que não
roda neste sandbox Linux): a lógica central de polling (regex de detecção do marcador em
stderr, parsing da última linha de stdout como JSON, detecção de resultado completo, espera
extra, e encerramento controlado com confirmação) foi extraída e testada contra um processo
fictício controlável (Python, mesmo contrato de stdout/stderr do worker real) em dois cenários:
(1) processo que produz o resultado completo e sai sozinho logo depois -- detectado
corretamente, sem encerramento forçado; (2) processo que produz o resultado completo e
permanece vivo indefinidamente -- detectado corretamente após a espera extra, e encerrado de
forma controlada e confirmada, sem deixar processos órfãos. Isso prova que a MECÂNICA do
roteiro funciona; a EXECUÇÃO real contra o worker/PicoGK genuíno só pode acontecer no Windows do
usuário (ver seção 4) -- ainda não foi executada.

**Próximo passo**: o usuário deve rodar `Run-VoronoiDirectWorkerProbe.ps1` no Windows contra
`block-voronoi-preview-v1`. Se o relatório resultante confirmar `still_alive_after_extra_wait:
true` (resultado completo + processo vivo por tempo adicional sem nenhum watchdog externo), a
FASE B (implementação de um `WorkerProcessExitCoordinator` explícito no limite externo do
processo) será iniciada com essa prova direta em mãos -- não antes, por instrução explícita do
usuário.
