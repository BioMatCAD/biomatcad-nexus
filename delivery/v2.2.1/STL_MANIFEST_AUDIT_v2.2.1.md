# STL_MANIFEST_AUDIT_v2.2.1 — auditoria STL vs. manifesto (item 11 do Incremento 2.1.1)

## O que a auditoria do Incremento 2.1 encontrou

O STL de exemplo entregue (`example-scaffold-v2.2.stl`, explicitamente rotulado no seu próprio
cabeçalho binário como `"BioMatCAD Nexus DEMO - exemplo SINTETICO pre-calculado (nao gerado
pelo PicoGK)"`) tinha, quando reprocessado de forma independente: 336 triângulos, **224**
vértices únicos (após solda por posição), ~457.57 mm² de área, ~130.36 mm³ de volume. O
manifesto correspondente (`example-manifest-v2.2.json`) declarava: 336 triângulos, **168**
vértices, 950.5 mm², 400 mm³. Divergência real, não de arredondamento.

## Causa raiz identificada e corrigida nesta sessão

O worker C# nunca deduplicava vértices — cada triângulo era escrito com 3 vértices "soltos"
(limitação inerente do próprio formato STL binário, que não suporta índices compartilhados), e
as métricas eram calculadas sobre essa contagem bruta (3 × número de triângulos), nunca sobre
uma representação soldada/única. Corrigido via `SimpleMesh.Weld(epsilonMm: 1e-5)`
(`apps/geometry-worker/SimpleMesh.cs`), aplicado ANTES tanto do cálculo de métricas
(`GeometryMetricsCalculator`) quanto da exportação STL (`StlExporter`) — garantindo que a
contagem de vértices únicos reportada no manifesto seja a mesma que qualquer ferramenta externa
obteria ao reabrir o STL e soldar por posição.

## Por que este relatório não contém números "corrigidos" de exemplo

A especificação corretiva do Incremento 2.1.1 (Seção 11) é explícita: **"Não altere os números
manualmente"** — a correção precisa vir de uma execução real do PicoGK gerando um novo STL, com
métricas calculadas sobre essa malha real, não de editar à mão o STL/manifesto sintéticos
existentes para "parecerem" consistentes. Como a execução real do PicoGK continua bloqueada
neste sandbox Linux (ver ADR-0007, `WORKER_STATUS.md`), este relatório **não pode**, com
honestidade, apresentar um novo par STL-real/manifesto-real consistente ainda.

## O que está pronto para fechar este item

1. **A correção de código** (`SimpleMesh.Weld()`, item acima) — testada contra malhas sintéticas
   de teste conhecidas (`SimpleMeshWeldTests.cs`, `GeometryMetricsCalculatorTests.cs`,
   `StlExporterTests.cs` — 44 testes xUnit no total, todos passando).
2. **Uma ferramenta de auditoria independente** — `scripts/audit_stl_vs_worker_output.py`. É uma
   segunda implementação, em Python puro (biblioteca padrão, sem dependências externas),
   TOTALMENTE separada do código C# do worker: reparsa o STL binário gravado, solda vértices por
   posição, recalcula bounding box/volume/área/vértices-únicos/watertightness, e compara
   contra o JSON de saída do worker e/ou o `manifest.json`, com tolerância numérica de 0.1% e
   `exit code 1` em caso de divergência real. Autoteste incluído nesta sessão contra um
   tetraedro sintético conhecido (volume analítico 1/6 mm³, 4 vértices únicos, watertight),
   confirmando tanto o caso de sucesso quanto a detecção correta de uma divergência proposital.
3. **Instruções exatas** de como rodar essa ferramenta contra a saída real do worker —
   `docs/examples/WINDOWS_EXECUTION_KIT.md`, Seção 5.

## Como este item será fechado

Depois que o usuário rodar as três golden recipes no seu Windows x64 (ver
`docs/examples/WINDOWS_EXECUTION_KIT.md`) e devolver os STLs + JSON de saída do worker + (se
gerado via o fluxo completo API→dispatcher) o `manifest.json` correspondente, rodar:

```powershell
python scripts\audit_stl_vs_worker_output.py <arquivo.stl> --worker-json <stdout.json> --manifest-json <manifest.json>
```

Se não houver divergências, este relatório será atualizado com os números reais e o item 10/11
do checklist de aceite (`ACCEPTANCE_CHECKLIST_v2.2.1.md`) poderá ser marcado como provado em
(b). Se houver divergências, elas serão investigadas e corrigidas no código — nunca maquiadas.

**Status deste item nesta entrega: código corrigido e ferramenta de verificação pronta; prova
final pendente da execução real do usuário no Windows.**
