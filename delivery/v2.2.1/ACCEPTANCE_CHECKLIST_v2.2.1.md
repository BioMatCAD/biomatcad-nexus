# ACCEPTANCE_CHECKLIST_v2.2.1 — checklist de aceite (17 itens) do Incremento 2.1.1

Extraído de `IMPLEMENTATION_STATUS.md` para acompanhar a entrega v2.2.1 como documento
autocontido. Ver aquele arquivo para o contexto completo e o restante do histórico do projeto.

**Declaração explícita, conforme instrução do usuário**: o Incremento 2.1 (e seu corretivo
2.1.1) só pode ser declarado CONCLUÍDO quando os 17 itens abaixo estiverem PROVADOS. Nesta
entrega, 4 itens estão totalmente provados (7, 8, 9, 16), 8 itens têm código corrigido e testado
mas não provados contra PicoGK real (2, 3, 4, 5, 6, 10, 11, 15), e os 5 itens restantes
simplesmente não foram feitos ainda (1, 12, 14, 17-para-v2.2.1, e o item 13 é neutro/inalterado).
**Portanto, esta entrega NÃO declara o Incremento 2.1 concluído.** Ela entrega o código
corrigido, testado no que é testável sem PicoGK, documentado com honestidade, e um kit de
execução para o usuário fechar os itens restantes no seu próprio Windows x64.

## Checklist de aceite do Incremento 2.1.1 (17 itens)

| # | Item | Status | Evidência / observação |
|---|---|---|---|
| 1 | Worker PicoGK realmente executado em Windows x64 | **NÃO FEITO** (pendente) | Depende da execução do usuário no seu Windows — ver `docs/examples/WINDOWS_EXECUTION_KIT.md`. Nada foi executado contra PicoGK real nesta sessão, em nenhuma plataforma. |
| 2 | Geração real de bloco Gyroid | Código corrigido e testado (a); NÃO provado (b) | `GyroidMath.cs` (fórmula de Schoen, 44 testes xUnit incluindo `GyroidMathTests.cs`) e `GyroidDomainImplicit` em `GyroidScaffoldBuilder.cs` aplicam a fórmula corretamente em teoria; nenhuma malha real do PicoGK foi gerada nesta sessão. |
| 3 | Cilindro realmente recortado (não bounding box) | Código corrigido via interseção de SDF (a); NÃO provado (b) | `GyroidMath.CappedCylinderSignedDistanceMm` + `IntersectSignedDistance` (max de duas SDF, CSG padrão) substituem o corte por bounding box do Incremento 2.1 — testado matematicamente (`GyroidMathTests.cs`), não contra voxelização real. |
| 4 | Diferença real preview vs. final | Código corrigido (piso de voxel 0.3mm) (a); NÃO provado (b) | `GyroidMath.EffectiveVoxelSizeMm`/`PreviewMinVoxelSizeMm`, testado unitariamente; a diferença real de tempo/resolução entre os dois modos só é observável numa execução real. |
| 5 | Parâmetros efetivamente aplicados (espessura/isovalor/porosidade/seed) | Código corrigido e testado na camada matemática (a); NÃO provado (b) | `WallThicknessMmToHalfBandWidth`, `SeedToPhaseShiftRad`, `CalibratePorosityByBisection` — todos testados isoladamente (matemática pura); a aplicação real numa malha voxelizada depende da execução real. |
| 6 | Limites computacionais efetivamente controlados | Código corrigido, parcialmente verificado nesta sessão | Estimativa prévia de voxel/memória (`EstimateVoxelCount`/`EstimateMemoryMbUpperBound`) testada unitariamente; o mecanismo de timeout + kill de árvore de processos (`psutil`) é cross-platform e **foi verificado neste sandbox** (funciona independentemente do PicoGK, pois mata o processo do worker seja qual for o motivo da demora). |
| 7 | Fila concorrente seguro | **PROVADO de verdade** | `SELECT ... FOR UPDATE SKIP LOCKED` contra Postgres real, duas conexões/threads reais e independentes, zero jobs reivindicados em duplicidade em 24 jobs (`test_geometry_job_concurrency.py`). |
| 8 | Cancelamento real | **PROVADO de verdade** | Teste de corrida contra o fluxo real de `dispatch_job`, kill de árvore de processos via `psutil` (cross-platform), idempotência de recancelamento (`test_geometry_job_cancellation.py`). |
| 9 | Isolamento organizacional | **PROVADO de verdade** | Testes de ataque dedicados (projeto/receita/material de outra organização, receita não pertencente ao projeto, receita não validada) — todos recusados e auditados (`test_geometry_job_security.py`). |
| 10 | Métricas coerentes com o STL | Código corrigido (solda antes de medir) (a); NÃO provado (b) contra STL real do PicoGK | `SimpleMesh.Weld()` aplicado antes de `GeometryMetricsCalculator` e `StlExporter`, testado contra malhas sintéticas de teste (cubo unitário conhecido, etc. — `SimpleMeshWeldTests.cs`, `GeometryMetricsCalculatorTests.cs`); nunca contra um STL real gerado pelo PicoGK. |
| 11 | Manifesto coerente com os artefatos | Código corrigido (a); NÃO provado (b) em execução ponta-a-ponta real | Manifesto reestruturado (commit, versões, plataforma, seed/fase, parâmetros efetivos, SHA-256 por artefato, checksum do próprio manifesto fora do JSON) — verificado por testes de unidade/integração do backend, nunca contra uma execução real completa API→worker→artefato. |
| 12 | Determinismo geométrico provado | **NÃO FEITO** (pendente) | Requer duas execuções reais no Windows com a mesma receita/seed, comparando SHA-256 do STL resultante — não pôde ser feito neste sandbox. |
| 13 | Visualização e download | Inalterado do Incremento 2.1, fora do núcleo de correções deste incremento | `StlViewer.tsx` (Three.js, orbit/pan/zoom/wireframe/corte/screenshot) e `JobDetailPage.tsx` continuam como estavam — nenhum defeito relacionado foi relatado na auditoria que motivou o 2.1.1, então nenhuma mudança foi feita aqui. |
| 14 | E2E real | Escrito, **nunca executado em nenhum ambiente** | `apps/web/e2e/` (Playwright) — bloqueado neste sandbox Linux (`libXdamage.so.1` ausente, `sudo` desabilitado — ver `apps/web/e2e/README.md`); pendente de execução real no Windows do usuário. |
| 15 | Todos os testes/builds aprovados | **SIM, para o que é testável sem PicoGK real** | Backend: 83 testes pytest (2 skips esperados sem `dotnet`/Windows), ruff e mypy limpos. Worker C#: 44/44 xUnit passando (só código independente de PicoGK), `dotnet build` sem erros. Frontend: 27/27 Vitest, `tsc --noEmit` e `eslint` limpos, `npm run build` e `npm run build:pages` executados com sucesso. Isso **não** equivale a prova E2E/PicoGK real (itens 1, 12, 14). |
| 16 | Histórico preservado | **SIM, verificado** | Base (tag/commit do v2.2) intacta; apenas novos commits acrescentados nesta sessão (nenhum `git commit --amend`, `rebase` ou `push --force` usado); `git log` mostra a sequência completa desde o Incremento 1. |
| 17 | Checksums verificados na extração/restauração | **SIM para o bundle base v2.2** (início da sessão); **AINDA NÃO** para o pacote final v2.2.1 | O pacote v2.2.1 (zip/bundle/SHA256SUMS) ainda não foi gerado — é uma tarefa de empacotamento separada, posterior a esta documentação. |

### Resumo honesto

**Totalmente fechados e provados nesta sessão**: itens 7, 8, 9, 16 (segurança/concorrência/
cancelamento/preservação de histórico — nenhum depende de PicoGK real, todos exercitados contra
infraestrutura real: Postgres real, processos reais, git real).

**Código corrigido e testado no que é testável sem PicoGK, mas não provado ponta-a-ponta**:
itens 2, 3, 4, 5, 6, 10, 11, 15 — este é o grosso das correções deste incremento. A correção é
real e o teste unitário/de integração que a acompanha também é real; o que falta é a prova final
contra uma execução genuína do PicoGK.

**Simplesmente não feitos ainda, dependem do usuário**: itens 1, 12, 14 (execução real,
determinismo, E2E) e 17 para o pacote final v2.2.1 especificamente (o v2.2 base já foi
verificado).

**Sem mudança de escopo neste incremento**: item 13 (visualização/download), que segue como
estava no Incremento 2.1.

