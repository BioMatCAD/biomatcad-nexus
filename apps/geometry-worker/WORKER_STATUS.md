# WORKER_STATUS — apps/geometry-worker (Incremento 2.1)

Evidência bruta do estado real do worker C#/.NET 9 + PicoGK 2.2.0 nesta sessão. Ver ADR-0007
para a decisão e o raciocínio; este arquivo é o registro de evidência que a sustenta.

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

## 6. O que É testável nesta sessão (9/9 xunit passando)

`tests/BioMatCadGeometryWorker.Tests` compila e executa apenas os arquivos independentes de
PicoGK (`JobEnvelope.cs`, `SimpleMesh.cs`, `GeometryMetricsCalculator.cs`, `StlExporter.cs`):

```text
$ dotnet test
Passed!  - Failed: 0, Passed: 9, Skipped: 0, Total: 9
```

Cobrindo: volume/área/watertight de um cubo unitário conhecido, bounding box, estimativa de
porosidade (incluindo clamping), volume de domínio block/cilindro, detecção de malha não
fechada, formato binário STL, (de)serialização JSON do contrato de job.

## 7. O que NÃO é testável neste ambiente

- Geração real de um scaffold Gyroid via `Voxels`/`Mesh` do PicoGK.
- Determinismo geométrico real (mesma seed + mesma receita -> mesmo STL) -- só o contrato
  (mesmo JSON de entrada) é testável, não a geometria de saída em si.
- Geração de thumbnail (depende de execução real).
- Exportação VDB (depende de execução real E de suporte oficial confirmado do PicoGK a VDB).
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
# esperado: 9/9 passando (não depende do runtime nativo)
```
