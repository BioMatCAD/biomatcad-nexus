# TEST_EVIDENCE_v2.2.1 — Incremento 2.1.1 (corretivo)

Documento consolidado e autocontido de evidência de teste para a entrega v2.2.1. É um recorte
focado do `TEST_EVIDENCE.md` do repositório (que contém, além disto, o histórico completo desde
o Incremento 1.1) — pensado para acompanhar o pacote de entrega isoladamente.

Gerado em: 2026-07-29. Commit: ver `SHA256SUMS_v2.2.1.txt` / tag da entrega para o hash exato.

## Como ler isto

Nada aqui é declarado "provado contra PicoGK real" a menos que explicitamente dito. A distinção
central desta entrega:

- **(a) Testado nesta sessão, sem depender de execução real do PicoGK** — a esmagadora maioria
  do que segue.
- **(b) Provado ponta-a-ponta contra execução real do PicoGK em Windows x64** — **nada** nesta
  entrega está em (b) ainda. Depende da execução do usuário — ver
  `docs/examples/WINDOWS_EXECUTION_KIT.md`.

## 1. Backend (`apps/api`) — pytest, ruff, mypy

```text
$ pytest -v
83 passed, 2 skipped
```
2 skips esperados: dependem de `dotnet`/worker real no PATH (`DotnetPicoGkWorkerClient`).

```text
$ ruff check .
All checks passed!

$ mypy src
Success: no issues found
```

Cobertura nova desta sessão: isolamento entre organizações (5 ataques recusados+auditados),
concorrência real de fila (2 conexões/threads reais, Postgres real, 24 jobs, zero duplicidade),
cancelamento real com teste de corrida, 24 testes de schema (semântica espessura/isovalor).

## 2. Migração Alembic

```text
$ alembic upgrade head        # banco vazio
$ alembic upgrade head        # banco já na revisão do Incremento 2.1
```
Ambos os cenários verificados; nova revisão adiciona colunas de claim atômico
(`claimed_by_dispatcher_id`, `claimed_at`, `heartbeat_at`, `cancel_requested_at`, `worker_pid`)
e índice (`ix_geometry_jobs_status_created_at`).

## 3. Worker C#/.NET 9 (`apps/geometry-worker`) — build e xUnit

```text
$ dotnet build
Build succeeded. 0 Warning(s). 0 Error(s).

$ dotnet test
Passed! - Failed: 0, Passed: 44, Skipped: 0, Total: 44
```

Todos os 44 testes são sobre código **independente do runtime nativo do PicoGK**
(`GyroidMath.cs`, `SimpleMesh.Weld()`, `StlExporter`, `GeometryMetricsCalculator`,
`JobEnvelope`). Nenhum foi (nem poderia ser, neste sandbox Linux) validado contra uma execução
real de `PicoGK.Voxels`/`Mesh` — ver Seção 6 abaixo.

## 4. Frontend (`apps/web`) — Vitest, tsc, eslint, build

```text
$ npx tsc --noEmit          # sem erros
$ npm run lint              # sem erros
$ npx vitest run
Test Files  10 passed (10)
     Tests  27 passed (27)
$ npm run build             # sucesso
$ npm run build:pages       # sucesso
```

Validação de receita agora via Ajv (`ajv/dist/2020`) contra cópia sincronizada (testada
byte-a-byte) do schema real; bug real de canonicalização do fingerprint de demonstração
corrigido (recursão em todos os níveis de aninhamento, não só o nível de topo).

## 5. Auditoria de dependências

| Ecossistema | Ferramenta | Resultado |
|---|---|---|
| Python (23 deps diretas) | `pip-audit` | 0 vulnerabilidades |
| NuGet (2 projetos worker) | `dotnet list package --vulnerable --include-transitive` | 0 vulnerabilidades, 0 desatualizados |
| npm (raiz + apps/web) | `npm audit` | 18 encontradas — 1 corrigida sem breaking change (react-router 6.26.2→6.30.4); 17 deferidas (tooling de dev: eslint/vite/vitest, exigem major breaking, ver `ROADMAP.md`) |

Detalhamento item a item: `docs/security/DEPENDENCY_AUDIT_2.1.1.md`.

## 6. O que esta entrega explicitamente NÃO prova (pendências reais, não maquiadas)

1. **Execução real do worker PicoGK em Windows x64** — não ocorreu em nenhum momento desta
   sessão, em nenhuma plataforma. O pacote `PicoGK` 2.2.0 (NuGet) não publica runtime nativo
   para `linux-x64` (apenas `win-x64` e `osx-arm64`) — ver `apps/geometry-worker/WORKER_STATUS.md`
   e ADR-0007 para a evidência reproduzida (`DllNotFoundException` completo).
2. **Geometria real gerada pelo PicoGK** (bloco, cilindro recortado, espessura/isovalor/
   porosidade/seed efetivamente aplicados numa malha voxelizada real, diferença real
   preview/final) — o código está corrigido e testado matematicamente (item 3 acima), mas nunca
   executado contra o PicoGK real.
3. **Determinismo geométrico real** (mesma receita+seed+worker+plataforma ⇒ mesmo SHA-256 de
   STL) — requer duas execuções reais, que só podem acontecer no Windows do usuário.
4. **Consistência STL-vs-manifesto contra um STL real do PicoGK** — o mecanismo de solda de
   vértices (`SimpleMesh.Weld()`) está testado contra malhas sintéticas de teste conhecidas
   (cubo, tetraedro), mas nunca contra a saída real do PicoGK. Ver
   `delivery/v2.2.1/STL_MANIFEST_AUDIT_v2.2.1.md` para o relatório honesto desta pendência e a
   ferramenta pronta para fechá-la (`scripts/audit_stl_vs_worker_output.py`).
5. **E2E Playwright** — escrito (`apps/web/e2e/`), nunca executado em nenhum ambiente (bloqueio
   de bibliotecas nativas do Chromium neste sandbox Linux, `sudo` desabilitado — ver
   `apps/web/e2e/README.md`).

Os itens 1–5 acima só podem ser fechados depois que o usuário rodar
`apps/geometry-worker` de verdade em seu Windows x64 e devolver os resultados — ver
`docs/examples/WINDOWS_EXECUTION_KIT.md`. Ver `delivery/v2.2.1/ACCEPTANCE_CHECKLIST_v2.2.1.md`
para o checklist de aceite completo dos 17 itens, item a item.
