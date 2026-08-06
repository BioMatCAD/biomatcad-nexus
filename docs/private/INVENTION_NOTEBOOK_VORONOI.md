# CONFIDENCIAL — Caderno de Invenção: `voronoi_cell_edges_v1`

**Classificação: CONFIDENCIAL.** Este documento e o diretório `docs/private/` NUNCA devem
entrar no build do GitHub Pages (`apps/web` não referencia nem importa nada de `docs/`; o
`vite build --mode demo` empacota apenas `apps/web/src` e `apps/web/public`, confirmado por
inspeção do bundle gerado nesta rodada) nem em qualquer pacote de demonstração pública
distribuído a terceiros. Nenhum trecho deste documento deve ser copiado para `docs/architecture`,
`README.md`, material de marketing ou qualquer artefato público sem uma decisão formal e
documentada em contrário.

Este é um registro técnico de laboratório (caderno de invenção), não uma minuta de
reivindicação de patente. Não contém nem deve conter: linguagem de reivindicação ("claims"),
declaração de patenteabilidade, novidade ou atividade inventiva, nem os símbolos ® ou ™. Se e
quando uma decisão formal de proteção de propriedade intelectual for tomada, ela será registrada
separadamente, com aconselhamento jurídico apropriado -- este documento serve apenas para
preservar, com data e evidência, o que foi de fato feito, decidido e testado.

---

## 1. Problema técnico

Gerar scaffolds (arcabouços porosos sintéticos) com uma topologia de poros baseada em uma
tesselação de Voronoi 3D real -- isto é, com struts (elementos de suporte cilíndricos/capsulares)
posicionados sobre as **arestas geométricas reais das células de um diagrama de Voronoi**
limitado a um domínio finito (bloco ou cilindro), e não sobre uma aproximação mais simples e
frequentemente confundida com ela: uma rede de linhas conectando sítios vizinhos entre si (que é,
matematicamente, um grafo de adjacência de Delaunay, uma estrutura DIFERENTE -- ver Seção 3).

Motivação de pesquisa: scaffolds Gyroid (TPMS, já implementados no Incremento 2.1) têm poros
regulares e periódicos; uma topologia derivada de Voronoi permite explorar estruturas porosas
estocásticas/heterogêneas, mais próximas de certas morfologias de tecido ósseo trabecular
reportadas na literatura (comparação morfológica real fica fora do escopo desta rodada -- não
foi feita, não deve ser assumida).

Restrição adicional imposta explicitamente nesta rodada: a implementação deveria rodar em um
sandbox Linux sem acesso ao runtime nativo do PicoGK (biblioteca de geometria voxel usada pelo
worker, bloqueada neste ambiente desde o Incremento 2.1 -- ver ADR-0007). Isso forçou uma
separação de responsabilidades que se revelou tecnicamente valiosa por si só (ver Seção 2).

## 2. Solução implementada

### 2.1 Separação em duas camadas independentes de PicoGK

A parte matematicamente mais delicada do problema -- geração de sítios determinística, dualidade
Delaunay/Voronoi, extração do grafo de arestas de células, tratamento de fronteira, deduplicação,
verificação de conectividade -- foi implementada em C# puro, **sem nenhuma referência a
`PicoGK.*`**, nos arquivos:

- `apps/geometry-worker/VoronoiSiteGenerator.cs` (geração de sítios).
- `apps/geometry-worker/VoronoiTessellation.cs` (tesselação e grafo de arestas).
- `apps/geometry-worker/VoronoiImplicitMath.cs` (smooth-min, SDFs de cápsula/esfera).

Isso permitiu testar de verdade (xUnit real, sem mocks do runtime nativo) 37 dos 99 testes do
worker (22 em `VoronoiMathTests.cs` + 15 em `VoronoiImplicitMathTests.cs`) neste sandbox Linux,
mesmo com o PicoGK bloqueado -- o que por sua vez permitiu iterar e corrigir a matemática do
algoritmo com alta confiança ANTES de qualquer execução real no Windows do usuário. A camada que
efetivamente depende do PicoGK (voxelização das formas implícitas, geração de malha, cálculo de
métricas sobre a malha real) fica isolada em `VoronoiScaffoldBuilder.cs`, que delega a
`VoronoiTessellation`/`VoronoiSiteGenerator` para tudo que não precisa do runtime nativo.

Esta separação (matemática pura testável vs. execução dependente de runtime nativo bloqueado) é
o mesmo padrão já usado por `GyroidMath.cs`/`GyroidScaffoldBuilder.cs` no Incremento 2.1 --
reaplicado aqui deliberadamente por já ter se mostrado eficaz.

### 2.2 Algoritmo (resumo -- definição matemática completa na Seção 3)

1. Gerar sítios deterministicamente por seed (`uniform_random` com distância mínima entre
   sítios, ou `jittered_grid`).
2. Tetraedralizar por Delaunay 3D (`MIConvexHull.Triangulation.CreateDelaunay` -- biblioteca de
   terceiros, avaliada em detalhe na Seção 6).
3. Calcular o circuncentro de cada tetraedro (regra de Cramer, sistema linear 3x3 -- Seção 3.2).
4. Para cada face triangular compartilhada entre dois tetraedros: aresta de Voronoi = segmento
   entre os dois circuncentros. Para cada face na fronteira do casco convexo: aresta de Voronoi
   = raio semi-infinito a partir do circuncentro, recortado pela SDF do domínio real (bloco ou
   cilindro) -- nunca pela bounding box.
5. Deduplicar nós (tolerância relativa) e arestas; verificar componentes conexos e nós isolados.
6. Construir struts implícitos (cápsulas por aresta) unidos por um blend suave polinomial
   (`smooth-min`, estratégia `implicit_smooth_union`) em cada nó; voxelizar via PicoGK.
7. Calibrar o raio do strut por bisseção monotônica contra a porosidade medida na malha
   real (reaproveita `GyroidMath.CalibrateByMonotonicBisection`, já genérica).
8. Calcular métricas (geométricas genéricas + específicas de rede: sítios, células válidas,
   nós, arestas, comprimentos, graus, componentes, contenção no domínio -- ver Seção 9 da
   instrução original e `VoronoiTopologyProvider.PopulateMetricsExtra`).

## 3. Definição matemática

Ver o documento completo (não confidencial, já público no repositório):
`docs/architecture/voronoi-cell-edges-v1-math-audit.md` -- contém as definições precisas de
célula de Voronoi, triangulação de Delaunay, a tabela de dualidade Delaunay-Voronoi por
dimensão, a fórmula fechada do circuncentro via regra de Cramer, a tolerância de degenerescência
relativa à escala, e o tratamento de fronteira por recorte de raio via SDF (em vez de
espelhamento de sítios). Este caderno de invenção não duplica esse conteúdo -- referencia-o como
a definição matemática de registro.

**Ponto central, reafirmado aqui por ser a distinção que motivou toda a auditoria matemática
desta rodada**: uma aresta de Voronoi corresponde a uma FACE (triângulo) da triangulação de
Delaunay -- não a uma aresta de Delaunay. Uma aresta de Delaunay (sítio_i, sítio_j) é dual de
uma FACE de Voronoi (um polígono 2D), nunca de uma aresta. O teste
`Compute_ArestasNuncaConectamSitiosDiretamente_DistinçãoRealDeDelaunay`
(`VoronoiMathTests.cs`) prova, sobre a estrutura de dados real produzida pelo código, que
nenhuma aresta do grafo final liga dois sítios diretamente.

## 4. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Grafo de adjacência de Delaunay (linhas sítio-a-sítio) | É a abordagem "ingênua" mais comum, mas geometricamente DIFERENTE de uma rede de arestas de células de Voronoi (ver Seção 3) -- a instrução desta rodada proibiu explicitamente rotular isso como Voronoi. |
| `MIConvexHull.VoronoiMesh` (classe pronta da própria biblioteca escolhida) | Leitura do código-fonte (`VoronoiMesh.Create`) mostrou que ela descarta silenciosamente as faces de fronteira do casco convexo -- nunca produz os raios não-limitados que este caso de uso exige. Usamos apenas `Triangulation.CreateDelaunay` e implementamos a extração de arestas (internas + raios) por conta própria. |
| Espelhamento de sítios nas faces do domínio (técnica usada por `scipy.spatial.Voronoi`/Qhull) para fechar o diagrama sem raios | Exige decidir quantas cópias espelhadas gerar e em quais faces; risco de arestas espúrias perto dos planos de espelhamento. A abordagem de raio-explícito-recortado-por-SDF é mais direta de auditar (cada aresta de fronteira é rastreável a uma face de tetraedro específica) e reaproveita a infraestrutura de SDF já testada para Gyroid. |
| `scipy.spatial.Voronoi` (Python/Qhull) via processo cruzado Python<->C# | Introduziria uma dependência de processo externo e uma nova superfície de falha (serialização, timeout, disponibilidade do interpretador Python no ambiente do worker) só para uma função matemática que uma biblioteca .NET gerenciada (MIConvexHull) já resolve sem dependências transitivas. |
| Suavização dos nós via Catmull-Clark (subdivisão de malha) | Documentada como alternativa FUTURA no schema e na auditoria matemática -- nunca implementada nesta rodada. A estratégia real e única implementada é `implicit_smooth_union` (smooth-min polinomial sobre as SDFs de cápsula/esfera, antes da voxelização) -- mais simples de calibrar (parâmetro escalar `node_smoothing` em [0,1]) e reaproveita a mesma infraestrutura implícita já usada pelo Gyroid. |

## 5. Decisões registradas

- **Dependência externa**: `MIConvexHull` 1.1.19.1019 (NuGet, MIT, sem dependências
  transitivas), usada exclusivamente para `Triangulation.CreateDelaunay`. Risco registrado
  honestamente: última publicação há ~7 anos (sem manutenção ativa) -- mitigado por (a) ser usada
  apenas para uma função matemática estável, (b) ter uso real em produção por outro software
  aberto (MatterControl), (c) ser puramente gerenciada, substituível sem afetar o resto do
  pipeline se necessário. Avaliação completa na Seção 6 de
  `docs/architecture/voronoi-cell-edges-v1-math-audit.md`.
- **Convenção real de adjacência do MIConvexHull** (não documentada de forma inequívoca pela
  biblioteca): `TriangulationCell.Adjacency[i]` é a célula vizinha através da face OPOSTA ao
  vértice `Vertices[i]` -- verificada empiricamente nesta rodada (não assumida da documentação),
  via um probe C# descartável que construiu uma tetraedralização conhecida e inspecionou a
  correspondência vértice-face-vizinho diretamente. Teste de regressão permanente:
  `MIConvexHull_ConvençãoDeAdjacência_OpostaAoVértice_ÉAConvençãoReal` em `VoronoiMathTests.cs`.
- **Tratamento de fronteira**: raio explícito recortado por SDF de domínio (nunca espelhamento
  de sítios) -- ver linha correspondente na tabela de alternativas acima.
- **Estratégia de suavização de nós**: `implicit_smooth_union` (única implementada), com
  `node_smoothing` (fator do blend, 0..1) e `node_radius_factor` (raio efetivo do nó =
  `strut_radius_mm x node_radius_factor`) como os dois parâmetros expostos na receita.
- **Calibração de porosidade**: reaproveita `GyroidMath.CalibrateByMonotonicBisection` sem
  nenhuma duplicação de algoritmo -- o mesmo método de bisseção monotônica, parametrizado por um
  oráculo de medição injetado (a malha real, não uma estimativa analítica), já corrigido no
  Incremento 2.1.1 para nunca declarar `converged=true` de forma enganosa.
- **Limites conservadores da receita**: `site_count` em [4, 500] (mínimo necessário para
  qualquer tetraedralização 3D não-degenerada; máximo escolhido para manter as receitas desta
  rodada pequenas e de custo computacional previsível), `strut_radius_mm` em (0.02, 3],
  `node_smoothing` em [0,1], `node_radius_factor` em [1,3], `boundary_behavior` restrito a
  `"clip"` (único implementado, mantido como enum para extensão futura em vez de booleano ou
  constante fixa).

## 6. Experimentos realizados

### 6.1 Probe de convenção de adjacência do MIConvexHull

Programa C# descartável (não commitado), construindo uma tetraedralização de 5 pontos
conhecidos e inspecionando `Adjacency[i]` de cada célula contra os vértices compartilhados dos
tetraedros vizinhos, para confirmar empiricamente qual vértice cada entrada de `Adjacency`
"exclui" (a convenção "face oposta ao vértice i"). Resultado incorporado como teste de
regressão permanente (Seção 5 acima) -- este é o tipo de fato que, se a biblioteca mudasse de
comportamento em uma versão futura (ainda que improvável dado o abandono de manutenção), seria
pego imediatamente por uma suíte que quebra, em vez de produzir uma rede de arestas sutilmente
errada sem nenhum aviso.

### 6.2 Sweep de estresse (500 casos)

Executado em rodada anterior a esta: 500 combinações de domínio (bloco/cilindro, dimensões
variadas), `site_count` e seed, verificando ausência de falhas de contenção (nós fora do
domínio) e ausência de exceções não tratadas. Nesta rodada, o resultado desse sweep motivou a
adição de uma verificação de contenção REAL e permanente no pipeline de produção (não apenas em
um script manual avulso) -- ver `VoronoiTessellation.MaxNodeContainmentViolationMm` e
`domain_containment_verified` em `metrics.Extra` (commit `d319986`, Seção 9 cont. desta rodada).

### 6.3 Probe de parâmetros para as golden recipes

Antes de commitar as 3 golden recipes desta rodada (`block-voronoi-preview-v1`,
`block-voronoi-final-v1`, `cylinder-voronoi-preview-v1`), um segundo programa C# descartável
(não commitado, referenciando apenas os arquivos PicoGK-independentes) executou de fato
`VoronoiSiteGenerator.Generate` + `VoronoiTessellation.Compute` para cada candidato de
parâmetros e reportou contagens reais (sítios efetivos/rejeitados, células, nós, arestas,
componentes conectados, checksums SHA-256 de sítios e do grafo) -- nenhum desses números foi
inventado; todos vêm de execução real do código de produção (sem PicoGK, que não estava
disponível neste sandbox). Os números exatos estão registrados nos comentários do commit
`3649550` e em `schemas/biomatcem/golden-recipes/METADATA.json`.

## 7. Bugs encontrados (e corrigidos) durante o desenvolvimento

- **Convenção de adjacência do MIConvexHull não documentada** (não é bem um "bug", mas uma
  ambiguidade real na biblioteca de terceiros que, se assumida incorretamente, produziria uma
  extração de arestas de fronteira sutilmente errada) -- resolvida por verificação empírica
  direta (Seção 6.1), nunca por suposição.
- **Ausência de verificação de contenção no caminho de produção** (Seção 9 cont., commit
  `d319986`): a única evidência de que os nós finais ficam realmente dentro do domínio vinha de
  um sweep manual avulso (Seção 6.2), não de uma checagem embutida no pipeline que roda em TODO
  job Voronoi. Corrigido adicionando `MaxNodeContainmentViolationMm`/`domain_containment_verified`
  calculados sempre, reaproveitando a mesma SDF já usada para decidir os recortes de fronteira
  (nunca uma segunda noção independente de "dentro do domínio").
- **Campos derivados triviais ausentes do manifesto** (mesmo commit): "células válidas" e
  "estratégia de suavização" eram computáveis a partir de dados já existentes, mas não estavam
  expostos como seus próprios campos explícitos no manifesto -- exigiam que o consumidor da API
  fizesse a derivação. Corrigido expondo `valid_cell_count` (derivado por subtração exata) e
  `smoothing_strategy` (string fixa refletindo a única estratégia implementada) diretamente.

## 8. Resultados (o que foi genuinamente provado nesta rodada, sem exagero)

- **Provado neste sandbox Linux** (sem PicoGK): a matemática pura de geração de sítios e
  tesselação (99/99 testes C# `dotnet test`, incluindo determinismo, contenção no domínio,
  ausência de coincidência, distinção real Voronoi-vs-Delaunay, deduplicação, componentes
  conectados/nós isolados, matemática do smooth-min/SDFs implícitas) e o schema/contratos/
  registro de provider no lado Python (181 testes `pytest` passando, 2 falhas pré-existentes e
  documentadas separadamente como dívida anterior não relacionada a Voronoi -- ver
  `TEST_EVIDENCE.md`).
- **NÃO provado neste sandbox** (depende de execução real do PicoGK no Windows do usuário, ver
  ADR-0007 e o roteiro de validação desta rodada): geração real de STL a partir de uma receita
  Voronoi, medição real de porosidade/watertight/manifold sobre uma malha voxelizada real,
  reprodutibilidade byte-a-byte (SHA-256) entre execuções repetidas do worker completo, e se
  `MaxNodeContainmentViolationMm` realmente fica dentro da tolerância nas 3 golden recipes
  aprovadas rodando de verdade (o probe da Seção 6.3, que escolheu os parâmetros dessas
  receitas, foi executado ANTES deste campo existir).

## 9. Autores e datas

- Autoria: sessão de desenvolvimento assistido por agente (Claude, via Cowork/Claude Code),
  sob supervisão e decisão do usuário (Adler), no âmbito do projeto de doutorado BioMatCAD
  Nexus.
- Datas: auditoria matemática e decisão de dependência iniciadas em 2026-08-04 (commit
  `e07a5e2`); geração de sítios/tesselação em `6790938`; struts implícitos/calibração em
  `d09a616`; provider/registro em `64d243b`; golden recipes, frontend, métricas end-to-end e
  testes completados nesta sessão, em 2026-08-06 (commits `3649550`, `284d2c6`, `d319986`,
  `e6b446e`).

## 10. Dependências e licenças

- `MIConvexHull` 1.1.19.1019 -- MIT, sem dependências transitivas (ver Seção 5 acima e Seção 6
  de `docs/architecture/voronoi-cell-edges-v1-math-audit.md` para a avaliação completa).
  Registrado em `apps/geometry-worker/NOTICE`.
- Nenhuma outra dependência nova introduzida por esta funcionalidade -- o restante do pipeline
  (PicoGK, ASP.NET, etc.) já era uma dependência existente do worker desde o Incremento 2.1.

## 11. Limitações conhecidas e próximos experimentos

- **Execução real do PicoGK pendente** (bloqueio de ambiente, não de algoritmo) -- ver Seção 8.
  Próximo experimento necessário: rodar o roteiro Windows desta rodada (PowerShell) e comparar
  SHA-256 entre execuções repetidas das 3 golden recipes, confirmando determinismo ponta a
  ponta (não apenas da tesselação matemática, já provada, mas da voxelização/malha completas).
- **`jittered_grid` pode produzir menos sítios que `site_count` perto de domínios
  não-retangulares** -- comportamento documentado e reportado honestamente em
  `effective_parameters` (`site_count_effective`), nunca escondido; não é um bug, mas uma
  limitação conhecida da estratégia de grade regular perto de fronteiras curvas (cilindro).
  Nenhum experimento adicional planejado para mitigar isso nesta rodada -- registrado como
  comportamento aceito.
- **`anatomy_guided`** (uma terceira estratégia de distribuição de sítios, mencionada apenas
  como ponto de extensão reservado no schema) permanece inteiramente fora de escopo -- nenhum
  design, experimento ou decisão foi feito sobre ela nesta rodada.
- **Comparação morfológica com tecido ósseo trabecular real** está fora do escopo desta rodada
  (e do projeto neste incremento) -- mencionada apenas como motivação de pesquisa na Seção 1,
  nunca como um resultado obtido ou validado.
- **Custo computacional por avaliação de voxel não modelado com precisão** -- a estimativa de
  custo exposta no frontend (`apps/web/src/lib/computeCostEstimate.ts`) mede apenas o tamanho
  da grade de voxels (independente da topologia); o custo adicional real de avaliar N formas
  implícitas de Voronoi por voxel (maior que o custo de avaliar uma única função gyroid
  fechada) não foi medido empiricamente nesta rodada -- apenas contornado por um aviso
  heurístico de "receita pesada" baseado em `site_count`, documentado como heurística, não
  medição.
