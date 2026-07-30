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
