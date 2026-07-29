# Kit de execução real no Windows x64 — Incremento 2.1.1

Este documento é o guia operacional para executar o worker `BioMatCadGeometryWorker` de
verdade, com o PicoGK 2.2.0 nativo, no Windows x64 do usuário. Existe porque o ambiente de
desenvolvimento assistido (sandbox Linux) **não consegue** executar o runtime nativo do PicoGK
(ver `apps/geometry-worker/WORKER_STATUS.md` e `docs/adr/0007-worker-picogk-bloqueado-linux-com-evidencia.md`
para a evidência completa e reproduzível dessa limitação — `picogk.26.2.so` não existe para
`linux-x64` no pacote NuGet 2.2.0, apenas para `win-x64` e `osx-arm64`).

Por decisão explícita do responsável pelo projeto (Adler), o caminho escolhido para o
Incremento 2.1.1 é: o agente corrige e prepara todo o código; **o próprio Adler executa no seu
Windows** e devolve os artefatos reais (STL, logs, JSON de saída, manifesto) para auditoria e
fechamento formal dos itens de aceite que dependem de execução real do PicoGK.

Nada neste kit deve ser interpretado como "já provado" — os 17 itens de aceite do Incremento
2.1.1 que dependem de execução real (ver `IMPLEMENTATION_STATUS.md` / `TEST_EVIDENCE.md`)
só serão marcados como concluídos depois que os resultados deste kit forem devolvidos e
conferidos.

---

## 0. Pré-requisitos

- Windows 10 ou 11, **x64** (não ARM — o PicoGK 2.2.0 só publica runtime nativo `win-x64`).
- PowerShell 5.1 (já vem com o Windows) ou PowerShell 7+ (`winget install Microsoft.PowerShell`).
- .NET 9 SDK (não apenas o runtime — precisamos compilar):
  ```powershell
  winget install Microsoft.DotNet.SDK.9
  ```
  Confirme depois de instalar (feche e reabra o PowerShell antes):
  ```powershell
  dotnet --info
  ```
  Deve mostrar `.NET SDK` versão `9.x` e RID `win-x64`.
- (Opcional, apenas para rodar a suíte completa API+fila+E2E) Python 3.11+, PostgreSQL 14+,
  Node.js 20+. Se você só quer validar o worker isoladamente (passos 1 a 4 abaixo), não precisa
  de nada disso.

---

## 1. Obter o código

Use o pacote de entrega `biomatcad-nexus-v2.2.1.zip` (ou `.bundle`, se preferir restaurar via
git) fornecido junto com este kit. Extraia em um caminho **sem espaços e sem acentos**, por
exemplo `C:\biomatcad-nexus`.

Se usar o bundle:
```powershell
cd C:\
git clone C:\caminho\para\biomatcad-nexus-v2.2.1.bundle biomatcad-nexus
cd biomatcad-nexus
git log --oneline | Measure-Object -Line   # confirme a contagem de commits esperada
git tag -l
```

---

## 2. Compilar o worker

```powershell
cd C:\biomatcad-nexus\apps\geometry-worker
dotnet restore
dotnet build -c Release
```

Confira que o pacote `PicoGK` 2.2.0 foi restaurado com o runtime nativo `win-x64`:
```powershell
Get-ChildItem "$env:USERPROFILE\.nuget\packages\picogk\2.2.0\runtimes" -Directory
```
Deve listar `win-x64` (e possivelmente `osx-arm64`) — **isso já é evidência de que o ambiente
tem, em tese, o que falta no Linux**. A prova real só vem da execução no passo 4.

---

## 3. Rodar os testes automatizados do worker (xUnit)

Estes testes **não dependem do runtime nativo do PicoGK** (são a parte pura de matemática/STL/
métricas extraída para `GyroidMath.cs`, `SimpleMesh.cs`, `StlExporter.cs` — ver
`apps/geometry-worker/tests/`). Devem passar igual ao que já passou no Linux (44 testes):

```powershell
cd C:\biomatcad-nexus\apps\geometry-worker\tests\BioMatCadGeometryWorker.Tests
dotnet test | Tee-Object -FilePath C:\biomatcad-runs\dotnet-test-output.txt
```

Guarde `dotnet-test-output.txt` — é um dos artefatos a devolver.

---

## 4. Rodar as três golden recipes de verdade

Crie uma pasta para os resultados:
```powershell
New-Item -ItemType Directory -Path C:\biomatcad-runs -Force | Out-Null
```

Para cada uma das três receitas em `schemas\biomatcem\golden-recipes\` (`block-gyroid-v1.json`,
`cylinder-gyroid-v1.json`, `preview-gyroid-low-res-v1.json`), monte o job.json e rode o worker.
Um script auxiliar (`apps\geometry-worker\tools\New-JobFromRecipe.ps1`) faz o envelope por você
— ele só monta `{job_id, recipe, output_dir}`, não simula nem inventa nada da execução em si.

```powershell
cd C:\biomatcad-nexus\apps\geometry-worker

foreach ($recipeName in @("block-gyroid-v1", "cylinder-gyroid-v1", "preview-gyroid-low-res-v1")) {
    $recipePath = "..\..\schemas\biomatcem\golden-recipes\$recipeName.json"
    $outDir = "C:\biomatcad-runs\$recipeName"

    $jobJsonPath = .\tools\New-JobFromRecipe.ps1 -RecipePath $recipePath -OutputDir $outDir

    Write-Host "`n=== Executando worker para $recipeName ===`n"
    dotnet run -c Release --project . -- $jobJsonPath `
        1> "$outDir\stdout.json" `
        2> "$outDir\stderr.json"

    Write-Host "Exit code: $LASTEXITCODE"
    "$LASTEXITCODE" | Set-Content "$outDir\exit_code.txt"
}
```

Depois de rodar, cada pasta `C:\biomatcad-runs\<receita>\` deve conter:
- `job.json` — o envelope de entrada.
- `stdout.json` — se sucesso (`exit_code.txt` = 0), o `WorkerResultOutput` estruturado
  (métricas, parâmetros efetivos, `stl_sha256`, versões, plataforma).
- `stderr.json` — se falha (`exit_code.txt` != 0), o `StructuredWorkerError` estruturado.
- `exit_code.txt` — o código de saída do processo.
- O(s) arquivo(s) `.stl` gerado(s), se a execução chegou a esse ponto.

**Não edite nenhum desses arquivos.** Se algo falhar, o `stderr.json` com o erro real é
exatamente o que precisamos para diagnosticar — inclusive se a falha for outra (ex.: DLL nativa
faltando por outro motivo, incompatibilidade de versão do Visual C++ Redistributable, etc.).

---

## 5. Auditoria independente STL vs. saída do worker (item 11 da correção)

O objetivo aqui é ter uma **segunda implementação**, totalmente separada do código C# do
worker, recalculando as métricas geométricas diretamente do STL gravado, para provar que STL e
JSON de saída batem (a auditoria anterior tinha encontrado 336 triângulos / 224 vértices únicos
no STL contra 168 vértices no manifesto — exatamente o tipo de inconsistência que este passo
detectaria, caso ainda existisse).

Requer apenas Python 3 (sem dependências externas — usa só a biblioteca padrão):
```powershell
foreach ($recipeName in @("block-gyroid-v1", "cylinder-gyroid-v1", "preview-gyroid-low-res-v1")) {
    $outDir = "C:\biomatcad-runs\$recipeName"
    $stl = Get-ChildItem "$outDir\*.stl" | Select-Object -First 1
    if ($stl) {
        python C:\biomatcad-nexus\scripts\audit_stl_vs_worker_output.py $stl.FullName `
            --worker-json "$outDir\stdout.json" `
            | Tee-Object -FilePath "$outDir\independent_audit.txt"
    } else {
        Write-Warning "Nenhum STL encontrado em $outDir -- ver stderr.json"
    }
}
```

Se aparecer "DIVERGÊNCIAS ENCONTRADAS", **não corrija manualmente os números** — devolva o
`independent_audit.txt` junto com os outros artefatos; é exatamente esse tipo de divergência
real que precisa ser investigada e corrigida no código, nunca maquiada.

---

## 6. (Opcional, recomendado) Suíte completa: API + fila Postgres + dispatcher + worker

Isso prova a integração real de ponta a ponta (item 12 da correção), não só o worker isolado.
Requer PostgreSQL rodando localmente e Python 3.11+.

```powershell
cd C:\biomatcad-nexus\apps\api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# Ajuste a connection string conforme seu Postgres local:
$env:DATABASE_URL = "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad"

python -m alembic upgrade head
python -m pytest -v | Tee-Object -FilePath C:\biomatcad-runs\pytest-windows-output.txt
```

Um teste em particular (relacionado ao worker real) hoje está marcado `skip` no Linux porque o
`dotnet`/PicoGK não está disponível ali. No Windows, com o worker compilado, esse teste deve
rodar de verdade. **Se esse teste passar com sucesso real (job chega a `SUCCEEDED` via PicoGK
de verdade), isso é a prova mais forte de todo o Incremento 2.1.1** — devolva o trecho relevante
de `pytest-windows-output.txt` destacado. Se ele falhar ou continuar sendo pulado, devolva
também — não há problema em reportar isso, é exatamente o que o processo pede.

Para rodar o dispatcher e submeter um job via API real (fluxo completo), veja
`apps/api/scripts/geometry_dispatcher.py` e os testes em
`apps/api/tests/test_geometry_job_orchestration.py` como referência de uso.

---

## 7. (Opcional) E2E com Playwright

O ambiente Linux não conseguiu instalar as dependências de sistema do Chromium (bloqueio de
`sudo`, ver `apps/web/e2e/README.md` para o erro exato reproduzido). No Windows isso
normalmente funciona sem problema:

```powershell
cd C:\biomatcad-nexus\apps\web
npm install
npx playwright install --with-deps chromium
npm run test:e2e | Tee-Object -FilePath C:\biomatcad-runs\playwright-windows-output.txt
```

---

## 8. O que devolver

Compacte a pasta `C:\biomatcad-runs\` inteira (todas as subpastas das 3 receitas, mais os logs
opcionais dos passos 6 e 7) e devolva. Idealmente:

```powershell
Compress-Archive -Path C:\biomatcad-runs\* -DestinationPath C:\biomatcad-runs-resultado.zip
```

Com isso será possível:
- Conferir STL vs. manifesto vs. JSON do worker de forma independente (fechando o item 11).
- Confirmar aplicação real de `wall_thickness_mm`, `isovalue`, `target_porosity_pct`, `seed`,
  `preview` vs `final` (itens do checklist de aceite 2, 3, 4, 5).
- Confirmar determinismo (rodar a mesma receita+seed duas vezes deve produzir SHA-256 de STL
  idêntico — se quiser ajudar ainda mais, rode `block-gyroid-v1` duas vezes em pastas
  diferentes e compare os dois `stl_sha256`).
- Fechar (ou honestamente não fechar, com evidência do motivo) os 17 itens do checklist de
  aceite do Incremento 2.1.1.

**Se a execução falhar no Windows também**: não simule, não edite números, não invente uma
saída de sucesso. Devolva exatamente o `stderr.json`/erro real, e o Incremento será fechado
declarando precisamente esse bloqueio remanescente — como o Adler pediu explicitamente na
especificação corretiva.
