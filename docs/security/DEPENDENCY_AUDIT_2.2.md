# Auditoria de dependências npm — Fase E, fechamento do Incremento 2.2

Escopo: `apps/web` (frontend). Auditoria feita com `npm audit` (somente leitura) e
`npm audit fix --dry-run` (somente leitura) antes de qualquer alteração, seguida de
`npm audit fix` (sem `--force`) para os itens realmente corrigíveis sem mudança
incompatível. Nenhuma dependência foi atualizada por atualização em massa, e nenhuma
vulnerabilidade foi mascarada ou ignorada por configuração de auditoria.

## Estado antes da correção (11 avisos)

| Pacote | Severidade | Direto/transitivo | Só ferramenta/build ou também runtime |
|---|---|---|---|
| `@vitest/mocker` | moderada | transitivo (via vite/vitest) | ferramenta (dev/test) |
| `brace-expansion` | alta | transitivo (via eslint/typescript-eslint -> minimatch) | ferramenta (lint) |
| `esbuild` | moderada | transitivo (via vite) | ferramenta (dev server do vite) |
| `fast-uri` | alta | transitivo (via `ajv`, que e dependencia de producao real) | runtime, mas caminho vulneravel inatingivel (ver abaixo) |
| `js-yaml` | alta | transitivo (via eslint) | ferramenta (lint) |
| `nanoid` | alta | transitivo (via vite -> postcss) | ferramenta (build, nunca embarcado no bundle do navegador) |
| `react-router` | moderada | transitivo (via react-router-dom) | runtime, mas caminho vulneravel inatingivel (ver abaixo) |
| `react-router-dom` | moderada | direto (`^6.26.2`) | runtime, mas caminho vulneravel inatingivel (ver abaixo) |
| `vite` | alta | direto (devDependency) | ferramenta (dev server apenas) |
| `vite-node` | moderada | transitivo (via vitest) | ferramenta (test runner) |
| `vitest` | critica | direto (devDependency) | ferramenta (test runner) |

Total: 5 moderadas, 5 altas, 1 critica -- bate com o total de 11 ja relatado
anteriormente pelo usuario em execucao real no Windows.

## Correcoes aplicadas nesta rodada (sem `--force`, sem mudanca incompativel)

`npm audit fix --dry-run` mostrou que 4 dos 11 avisos tinham correcao estritamente
de versao de PATCH, sem qualquer `isSemVerMajor`. Aplicado via `npm audit fix`
(sem `--force`) e reverificado:

| Pacote | Antes | Depois | Natureza da mudanca |
|---|---|---|---|
| `brace-expansion` | 1.1.17 | 1.1.18 | patch, transitivo via eslint (dev-only) |
| `js-yaml` | 4.3.0 | 4.3.1 | patch, transitivo via eslint (dev-only) |
| `nanoid` | 3.3.16 | 3.3.18 | patch, transitivo via vite/postcss (build-only) |
| `fast-uri` | 3.1.4 | 3.1.5 | patch, transitivo via `ajv` (ver analise de alcancabilidade abaixo) |

Apos a correcao, `npm audit` reporta **7 avisos** (5 moderados, 1 alto, 1 critico),
confirmando que os 4 patches foram aplicados e nenhum novo aviso surgiu.

Verificacao pos-correcao (suite completa do frontend, sandbox):

- `tsc --noEmit`: sem erros.
- `eslint . --max-warnings 0`: sem erros/avisos.
- `vitest run`: 24 arquivos, **128/128 testes passaram**.
- `npm run build` (producao) e `npm run build:pages` (GitHub Pages): ambos concluidos
  sem erro, bundle gerado normalmente.

Nenhum teste foi enfraquecido ou removido para acomodar a atualizacao.

## Itens restantes (7) -- analise de alcancabilidade e decisao

### 1. `vitest` (critica), `@vitest/mocker` (moderada), `vite-node` (moderada)

CVE do `vitest`: leitura/execucao arbitraria de arquivo quando o servidor de UI do
Vitest (`vitest --ui`) esta escutando. `@vitest/mocker` e `vite-node` sao
dependencias transitivas do proprio `vitest`.

- **Direto/transitivo**: `vitest` e devDependency direta; os outros dois, transitivos.
- **Runtime vs ferramenta**: exclusivamente ferramenta de teste -- nao compoe o
  bundle de producao, nao roda em ambiente de pesquisa do usuario final.
- **Alcancabilidade**: o projeto nunca invoca `vitest --ui` em CI, scripts npm ou
  documentacao. Confirmado via `grep` em `package.json` e nos workflows --
  `vitest run` e o unico modo usado. Sem o modo UI ativo, o vetor nao existe.
- **Correcao disponivel**: apenas via `vitest@4.1.10`, uma major (3->4) com breaking
  changes na API de configuracao e mocks -- nao e uma atualizacao segura para
  aplicar de forma automatica dentro deste fechamento.
- **Decisao**: **deferida**, com mitigacao ja em vigor (nunca executar
  `vitest --ui`). Reavaliar migracao para Vitest 4 em incremento futuro, fora do
  escopo de pesquisa do 2.2.

### 2. `esbuild` (moderada), `vite` (alta)

CVEs relacionados ao **servidor de desenvolvimento** do Vite (bypass de
`server.fs.deny`, path traversal em dependencias pre-otimizadas, exposicao de hash
NTLMv2 no Windows via `launch-editor`).

- **Direto/transitivo**: `vite` e devDependency direta; `esbuild`, transitivo via `vite`.
- **Runtime vs ferramenta**: os tres CVEs sao exclusivamente do dev server
  (`vite dev`/`vite serve`); nenhum afeta a saida estatica gerada por `vite build`,
  que e o que de fato e servido/distribuido (`dist/`).
- **Alcancabilidade**: o ambiente de pesquisa nao expoe o dev server do Vite fora
  da maquina do pesquisador; nao ha uso de `vite dev` em producao/distribuicao.
- **Correcao disponivel**: apenas via `vite@8.2.1`, major (5->8), com breaking
  changes de configuracao e plugins -- fora do escopo de uma correcao segura e
  isolada neste fechamento.
- **Decisao**: **deferida**, com mitigacao (dev server nunca exposto fora de
  `localhost`/maquina do pesquisador). Reavaliar migracao major do Vite em
  incremento futuro.

### 3. `react-router` (moderada), `react-router-dom` (moderada)

CVEs: open redirect via barra invertida em `<Link>`/`useNavigate`, e injecao de
construtor arbitrario via `deserializeErrors()` na hidratacao SSR.

- **Direto/transitivo**: `react-router-dom` e dependencia de producao direta
  (`^6.26.2`, resolvida em `6.30.4`); `react-router` e transitivo via ela.
- **Runtime vs ferramenta**: dependencia de producao real, usada em todo o roteamento do frontend.
- **Alcancabilidade**:
  - A aplicacao **nao usa SSR** (e uma SPA servida como build estatico via
    `vite build`/GitHub Pages) -- o vetor de `deserializeErrors()` na hidratacao SSR
    nao se aplica.
  - Todo uso de `<Link to=...>`/`useNavigate(...)` no codigo (`grep` confirmado em
    `apps/web/src/pages/*.tsx` e `Sidebar.tsx`) usa exclusivamente **templates de
    caminho internos fixos** interpolados com **UUIDs emitidos pelo proprio
    servidor** (`project.id`, `r.id`, `m.id`, `newJob.id`, `created.id`) ou
    literais estaticos (`"/about"`, `"/login"`, `"/app"`). Nenhuma dessas chamadas
    recebe segmento de caminho vindo de entrada de usuario bruta ou de origem
    externa -- logo o vetor de open-redirect via backslash nao tem superficie de
    ataque real neste codigo.
- **Correcao disponivel**: `npm audit fix --dry-run` reporta `fixAvailable: true`
  para ambos, mas a execucao real do fix **nao altera a versao instalada**
  (permanece em `6.30.4`) porque a faixa vulneravel reportada
  (`6.0.0 - 7.17.0`) cobre toda a linha 6.x compativel com o `^6.26.2` do
  `package.json` -- nao existe release 6.x fora da faixa vulneravel. A correcao
  real exigiria migrar para react-router 7.x, uma mudanca de major com API
  diferente (fora do escopo de uma correcao pontual e isolada).
- **Decisao**: **deferida**, com mitigacao ja vigente por construcao (nenhuma
  entrada de usuario chega a `to=`/`navigate()`). Migracao para v7 fica registrada
  como trabalho futuro, fora do escopo de pesquisa do 2.2.

## Proibicoes respeitadas

- Nao foi executado `npm audit fix --force`.
- Nao houve atualizacao em massa de dependencias.
- Nenhuma vulnerabilidade foi mascarada (nenhuma configuracao de
  `.npmrc`/`audit-level`/`overrides` foi usada para silenciar avisos).
- Nenhum item foi declarado "sem risco" apenas porque os testes passam -- cada um
  dos 7 itens restantes tem uma analise explicita de alcancabilidade documentada
  acima, e os que exigem mudanca incompativel foram formalmente adiados com a
  mitigacao em vigor descrita.

## Resumo final

- **4 de 11** avisos corrigidos nesta rodada com atualizacao de patch, sem
  mudanca de comportamento, com suite completa (typecheck/eslint/vitest/build)
  verde apos a correcao.
- **7 de 11** avisos permanecem, todos exigindo mudanca de versao major
  (breaking change) para correcao completa; todos analisados individualmente e
  classificados como **nao alcancaveis nas condicoes reais de uso deste
  sistema** (dev-server-only, test-runner-only, ou entrada de usuario nunca
  chega ao codigo vulneravel), com mitigacao documentada e migracao maior
  explicitamente deferida para incremento futuro.
