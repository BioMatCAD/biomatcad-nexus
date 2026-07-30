# Auditoria do visualizador 3D (`StlViewer.tsx`) -- Incremento 2.2, item "Consolidar visualizador 3D"

Auditoria feita ANTES de qualquer alteração de código, sobre o estado real do componente
`apps/web/src/components/viewer/StlViewer.tsx` (existente desde o Incremento 2.1) e de como ele
é usado em `apps/web/src/pages/JobDetailPage.tsx`. Convenção de status: **OK** (implementado e
correto, não será substituído), **PARCIAL** (existe mas com lacuna real), **AUSENTE** (não
existe), **BUG** (existe mas está funcionalmente quebrado contra um backend real).

| # | Requisito | Implementação atual | Teste existente | Lacuna | Correção necessária |
|---|---|---|---|---|---|
| 1 | Carregamento do STL | `fetch(stlUrl, { headers: fetchHeaders })` dentro do próprio `StlViewer` | Nenhum (só smoke test do estado vazio) | Formato só binário (ver #34); sem verificação de checksum; sem limite de tamanho | Extrair para um helper autenticado com verificação de tamanho/checksum (ver Seção 2 do escopo) |
| 2 | Origem do arquivo | `client.artifactDownloadUrl(artifact.id)` -- URL da API, nunca caminho físico do servidor | Nenhum | -- | OK, manter |
| 3 | Autenticação | **BUG real encontrado nesta auditoria**: `JobDetailPage.tsx` passa `stlUrl={client.artifactDownloadUrl(stlArtifact.id)}` para `StlViewer` **sem passar `fetchHeaders`** -- o backend (`GET /api/v1/artifacts/{id}/download`, `apps/api/src/biomatcad_api/routers/artifacts.py`) exige `Depends(get_current_user)`, que lê exclusivamente o header `Authorization: Bearer <token>` (sem fallback de cookie). Contra um backend real, o `fetch` do visualizador e os links `<a href download>` da lista de artefatos retornariam **401**. Isso nunca foi pego porque (a) o modo demo (`demoApiClient`) serve um arquivo estático público, sem exigir auth, e (b) o E2E Playwright aprovado no Windows (`f7a9614`) verificou apenas a presença do link/testid, não um clique real seguido de download bem-sucedido | Nenhum cobria isso | **BUG de autenticação real, não testado** | Corrigir: passar o token para o fetch do STL; converter os links de download da lista de artefatos de `<a href>` estático para download autenticado via Blob |
| 4 | Orbit | `OrbitControls` do three.js | Não | -- | OK, manter |
| 5 | Pan | `OrbitControls` (pan habilitado por padrão) | Não | -- | OK, manter |
| 6 | Zoom | `OrbitControls` (zoom habilitado por padrão) | Não | -- | OK, manter |
| 7 | Wireframe | Checkbox + `material.wireframe` | Não | -- | OK, manter |
| 8 | Transparência | Checkbox booleano (opacity fixa 0.4 quando ativa) | Não | Sem controle granular de opacidade | Adicionar slider de opacidade |
| 9 | Eixos | `THREE.AxesHelper`, toggle | Não | -- | OK, manter |
| 10 | Grade/escala | `THREE.GridHelper`, toggle | Não | Grade não rotulada em mm; não há indicação textual da escala | Adicionar rótulo de escala (mm) |
| 11 | Clipping plane | `THREE.Plane` + slider de posição | Não | Direção do plano fixa (normal `(0,0,-1)`); falta seleção de eixo/orientação | Manter posição; documentar limitação de orientação fixa (não simular controle de orientação que não existe) |
| 12 | Screenshot | `renderer.domElement.toDataURL()` + download | Não | -- | OK, manter |
| 13 | Bounding box | **AUSENTE** -- geometria centraliza a câmera via `boundingSphere`, mas não há um `THREE.BoxHelper` visível opcional | Não | Ausente | Adicionar toggle de bounding box visível |
| 14 | Métricas (triângulos) | Contagem de triângulos exibida (`triangleCount`) | Não | Só triângulos; falta separar métricas do worker/manifesto | Adicionar painel de proveniência (Seção 4 do escopo) |
| 15 | Nível de detalhe | Prop `levelOfDetail` (texto livre, opcional) exibida ao lado da contagem de triângulos | Não | Nenhuma lógica real de LOD (não decima malha) | Manter como indicador textual apenas; documentar que NÃO há decimação real (não fabricar isso) |
| 16 | Loading | Estado `"loading"` + componente `Loading` | Não | Sem opção de cancelar o carregamento | Adicionar `AbortController` + botão cancelar |
| 17 | Falha | Estado `"error"` + `ErrorState` com mensagem | Não | Mensagem de erro pode vazar detalhes técnicos brutos (`err.message`) | Sanitizar mensagem antes de exibir |
| 18 | Artefato indisponível | Estado `"empty"` quando `stlUrl` é `null`/undefined | 1 smoke test (`StlViewer.test.tsx`) | -- | OK, manter |
| 19 | Responsividade | `container.clientWidth`/`clientHeight` no momento do mount; **sem listener de `resize`** | Não | Redimensionar a janela não atualiza `camera.aspect`/`renderer.setSize` | Adicionar `ResizeObserver` |
| 20 | Descarte de recursos WebGL | `controls.dispose()`, `renderer.dispose()`, `container.innerHTML = ""` no cleanup do efeito | Não | **Faltam**: `geometry.dispose()`, `material.dispose()`, remoção de listener de `webglcontextlost`/`restored` (que ainda não existe), proteção contra `setState` após unmount durante um fetch em andamento | Completar dispose e adicionar guarda de unmount |
| (extra) | Validação de tamanho antes/durante carregamento | **AUSENTE** | Não | Nenhum limite -- um STL arbitrariamente grande seria completamente baixado e parseado | Adicionar limite configurável, usando `size_bytes` do `Artifact` (já conhecido ANTES do fetch) como primeiro filtro |
| (extra) | Checksum/metadados registrados | **AUSENTE no cliente** (o backend já calcula e armazena `sha256`, mas o frontend nunca verifica os bytes recebidos contra ele) | Não | Sem verificação client-side | Calcular SHA-256 via `crypto.subtle` após o download e comparar com `artifact.sha256`; falha de verificação = estado de erro, nunca renderização silenciosa |
| (extra) | Formato ASCII do STL | **AUSENTE** -- `parseBinaryStl` (`src/lib/stlParser.ts`) só entende STL binário; um STL ASCII válido (`solid ... facet normal ... endsolid`) faz o parser ler lixo binário ou estourar os limites do buffer | Nenhum teste de ASCII | Real lacuna de formato | Implementar parser ASCII + detecção de formato |
| (extra) | Cancelamento de contexto WebGL perdido | **AUSENTE** | Não | Sem handler de `webglcontextlost`/`webglcontextrestored` | Adicionar handlers com estado dedicado |
| (extra) | Fallback sem WebGL | **AUSENTE** -- se `renderer = new THREE.WebGLRenderer(...)` falhar (ambiente sem WebGL), a exceção não é capturada e quebra o componente | Não | Real lacuna | Envolver criação do renderer em try/catch com estado `"webgl-unavailable"` |
| (extra) | Fullscreen | **AUSENTE** | Não | Ausente | Adicionar botão de fullscreen via Fullscreen API, com verificação de suporte |
| (extra) | Aviso literal de não-validação experimental | Existe uma nota de proveniência em `JobDetailPage.tsx` (`metrics-provenance-note`), mas com texto diferente do literal pedido nesta rodada | 1 teste (`JobDetailPage.test.tsx`) | Falta o texto literal exato | Adicionar o aviso literal `Resultado computacional — não validado experimentalmente.` junto ao visualizador (além da nota já existente, que permanece) |
| (extra) | Inconsistência entre métricas da API e do manifesto | **AUSENTE** -- hoje só `job.metrics` (API) é exibido; o manifesto tem seu próprio `metrics` (deveria ser o mesmo dict, mas nunca comparado) | Não | Nenhuma comparação | Adicionar comparação explícita e um estado de alerta de inconsistência |
| (extra) | Identidade visual no visualizador | Não usa nenhuma cor/estilo fora do padrão -- não há conflito | -- | -- | Nenhuma ação necessária além de manter o padrão de tema (`var(--color-*)`) já usado |

## Não substituído / mantido como está

Confirmando a instrução "não substitua funcionalidade existente que já esteja correta": orbit,
pan, zoom (via `OrbitControls`), wireframe, eixos, grade (toggle), clipping (posição), screenshot,
estado vazio inicial, e a extração de triângulos via `parseBinaryStl` para arquivos binários
continuam sendo usados como estão -- apenas estendidos, não reescritos do zero.

## Bibliotecas 3D usadas (para NOTICES.md)

Nenhuma biblioteca nova é introduzida nesta rodada: `three` 0.169.0 (já registrado em
`NOTICES.md`) continua sendo a única dependência de renderização 3D. Nenhum loader de STL de
terceiros é adicionado -- o parser próprio (`src/lib/stlParser.ts`) é estendido para ASCII, mas
continua sem dependência externa.

## Estado final desta rodada (pós-implementação, todos os itens acima fechados)

Registro feito DEPOIS da implementação completa, por transparência (Prompt Mestre §3.1): cada
item marcado **AUSENTE**/**PARCIAL**/**BUG** na tabela acima foi de fato corrigido/implementado
e re-verificado por teste real, nesta ordem de commits (`incremento-2.2-alpha-pesquisa`):

1. `32f4969` -- esta auditoria (antes de qualquer alteração de código).
2. `61e8e2e` -- carregamento seguro: `stlParser.ts` ganhou `detectStlFormat`/`parseAsciiStl`
   (formato ASCII, item #34 da tabela); novo módulo `src/lib/artifactDownload.ts` com
   `fetchArtifactBuffer` (download autenticado via `Authorization: Bearer`, nunca token na URL;
   limite de tamanho via `maxBytes`; verificação de checksum via `crypto.subtle.digest`) e
   `downloadArtifactAsFile` (Blob + ObjectURL + revogação em `finally`).
3. `fa7d09f` -- `StlViewer.tsx` reescrito: todos os controles pedidos (orbit/pan/zoom já
   existentes via `OrbitControls`; wireframe; transparência com slider de opacidade granular;
   eixos; grade; bounding box via `THREE.BoxHelper` opcional; clipping plane com slider de
   posição -- orientação permanece fixa, documentada como limitação conhecida, não simulada;
   screenshot; fullscreen via Fullscreen API com verificação de suporte); painel de
   proveniência em `JobDetailPage.tsx` (métricas da API vs. manifesto comparadas campo a
   campo, com `findMetricsDivergence` -- nunca escolhe um valor silenciosamente em caso de
   divergência); aviso literal `Resultado computacional — não validado experimentalmente.`;
   limites configuráveis (`DEFAULT_MAX_BYTES = 50 MiB`, `DEFAULT_MAX_TRIANGLES_DIRECT =
   500_000` -- acima disso, aviso de malha densa, sem decimação automática); cancelamento via
   `AbortController`; descarte completo (`geometry.dispose()`, `material.dispose()`,
   `controls.dispose()`, `renderer.dispose()`, listeners de `webglcontextlost`/`restored`
   removidos, guarda contra `setState` pós-desmontagem); fallback `"webgl-unavailable"` via
   try/catch ao redor da criação do `WebGLRenderer`; `ResizeObserver` com guarda
   `typeof ResizeObserver !== "undefined"` (jsdom não o implementa).
4. `35c51ee` -- suíte de testes de componente do `StlViewer` (21 casos) e teste de isolamento
   entre organizações no endpoint `GET /artifacts/{id}/download` (backend). Ao escrever esses
   testes, três bugs REAIS de ciclo de vida React/WebGL foram encontrados e corrigidos no
   próprio `StlViewer.tsx` (não apenas nos testes) -- ver corpo do commit para o diagnóstico
   completo de cada um: (a) a div do container WebGL não ficava montada durante o status
   `"loading"`; (b) o efeito de carregamento dependia de um valor derivado de `status` que ele
   mesmo mudava, causando um cleanup/dispose imediato após o sucesso; (c) o botão "Carregar
   mesmo assim" do aviso de tamanho quebrou como efeito colateral da correção de (b), corrigido
   unificando a UI de `"size-warning"` no mesmo bloco condicional dos demais estados.
5. `4180a67` -- corrigido um QUARTO bug real, encontrado ao escrever o teste de ponta a ponta
   da demonstração sintética do GitHub Pages: `demoClient.ts` declarava um SHA-256 placeholder
   (`"0".repeat(64)`) para o artefato STL de demonstração, o que fazia a verificação de
   checksum do cliente (item 4 acima) falhar SEMPRE no modo demo -- quebrando exatamente o
   requisito desta rodada de que o GitHub Pages sirva um STL sintético funcional. Corrigido
   substituindo o placeholder pelo SHA-256 real do arquivo
   (`public/demo-assets/sample-scaffold-block-gyroid.stl`, verificado via `sha256sum`);
   regressão coberta por `apps/web/tests/demoStlViewer.test.tsx` (2 casos, incluindo um teste
   que exercita o fluxo real e completo do `demoApiClient` contra os bytes reais do arquivo em
   disco, não um buffer fabricado em memória).

### Limitações conhecidas, registradas (não escondidas)

- **Sem decimação/LOD real**: o indicador de nível de detalhe (`levelOfDetail`) é apenas texto
  informativo opcional; nenhuma simplificação de malha é aplicada. Uma malha acima de 500.000
  triângulos mostra aviso, mas é renderizada por completo (o artefato original nunca é
  substituído por uma versão reduzida).
- **Clipping plane com orientação fixa**: apenas a posição ao longo da normal `(0,0,-1)` é
  ajustável; não há seleção de eixo/orientação do plano de corte.
- **E2E Playwright continua bloqueado neste sandbox** (mesma limitação de incrementos
  anteriores -- falta biblioteca nativa do Chromium, sem `sudo`). O E2E já aprovado no Windows
  (`f7a9614`, ver `apps/web/e2e/README.md`) verifica a presença do botão de download
  (`data-testid="stl-download-link"`, preservado nesta rodada mesmo após a mudança de `<a
  href>` para `<button>`) mas **não** exercita nenhum dos novos controles desta rodada
  (wireframe, transparência, eixos, grade, bounding box, clipping, screenshot, fullscreen,
  cancelamento) em navegador real -- essa cobertura hoje existe apenas em nível de componente
  (`StlViewer.test.tsx`, 21 casos, jsdom + `three.js` real exceto `WebGLRenderer`). Registrado
  como lacuna explícita para um roteiro Windows futuro, não fabricado como "coberto".
- **Achado de ambiente, não regressão desta rodada**: ao rodar a suíte backend contra o
  fallback SQLite padrão de `apps/api/tests/conftest.py` (usado quando `TEST_DATABASE_URL` não
  está definida), `test_clinical_suite.py::test_clinical_suite_expiration_is_respected` falhou
  com `TypeError: can't compare offset-naive and offset-aware datetimes`. Rodando a suíte
  completa contra uma instância Postgres efêmera NOVA via `pgserver` (o caminho pretendido,
  documentado no próprio `conftest.py`), em dois lotes: **136 testes aprovados, 2 pulados, 0
  falhas** -- consistente com o achado já registrado na rodada anterior em
  `IMPLEMENTATION_STATUS.md` ("Achado real de ambiente de teste") sobre dados residuais de
  execuções de teste anteriores persistindo entre invocações do sandbox (arquivo
  `apps/api/test_biomatcad.db` do SQLite, ou diretório de dados do `pgserver`). Não bloqueia
  esta rodada; não foi introduzido por ela.

### Evidência de que nenhuma geometria substituta foi usada

Em nenhum estado do `StlViewer` (`"error"`, `"size-warning"`, `"webgl-unavailable"`,
`"context-lost"`, `"cancelled"`) existe qualquer malha/geometria placeholder renderizada --
esses estados mostram apenas texto (via `EmptyState`/`ErrorState`) ou, no caso de
`"size-warning"`, um botão explícito para o usuário decidir prosseguir. Verificado por teste
(`StlViewer.test.tsx`, describe "artefato inválido/corrompido"): um STL binário truncado e um
STL com checksum divergente do esperado ambos resultam em estado `"error"` com mensagem
sanitizada, nunca em uma malha renderizada.
