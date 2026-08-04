# Auditoria matemática: `voronoi_cell_edges_v1` (Incremento 2.2, rodada Voronoi)

Status: **DECISÃO DE IMPLEMENTAÇÃO** — ao contrário de `docs/architecture/voronoi-topology-preparation.md`
(documento de preparação conceitual, sem código, mantido como registro histórico), este
documento define PRECISAMENTE qual estrutura matemática será implementada nesta rodada, antes
de qualquer linha de código de geração real ter sido escrita. Convenção: sempre que este
documento e o de preparação divergirem em algum ponto técnico (ex.: a disponibilidade de uma
biblioteca .NET para Voronoi 3D), este documento é o mais atual e correto — o de preparação
não é retroativamente editado, para preservar o registro honesto do que era conhecido em cada
momento.

## 0. Por que esta seção existe antes de qualquer código

A instrução desta rodada foi explícita: "Não confunda células de Voronoi; arestas das células
de Voronoi; grafo de adjacência; triangulação de Delaunay; arestas de Delaunay. Se a
implementação usar ligações entre sítios vizinhos, ela é uma rede baseada em Delaunay e não
deve ser rotulada como 'arestas Voronoi'." Esta seção existe para tornar essa distinção
inequívoca e para amarrar cada termo usado no código a uma definição matemática precisa, de
modo que um revisor futuro (humano ou IA) possa verificar, olhando o código, que ele realmente
implementa o que diz implementar.

## 1. Definições matemáticas precisas

Seja `S = {p_1, ..., p_n} ⊂ ℝ³` um conjunto finito de sítios (pontos), todos distintos.

**Célula de Voronoi** de `p_i`:

```
V_i = { x ∈ ℝ³ : |x - p_i| ≤ |x - p_j|  para todo j ≠ i }
```

Cada `V_i` é um poliedro convexo (interseção de semiespaços, um por vizinho `p_j`, delimitado
pelo plano bissetor perpendicular ao segmento `p_i p_j`). O conjunto `{V_1, ..., V_n}` particiona
`ℝ³` (a menos de fronteiras de medida nula) — este é **o diagrama de Voronoi**.

**Triangulação de Delaunay** (dual combinatório do diagrama de Voronoi, assumindo posição
geral — nenhum grupo de 5+ sítios coesférico): decomposição de `ℝ³` em tetraedros cujos vértices
são sítios de `S`, tal que a esfera circunscrita de cada tetraedro não contém nenhum outro sítio
de `S` em seu interior. É a estrutura DUAL do diagrama de Voronoi, ligada por esta
correspondência exata (dimensão `k` ↔ dimensão `3-k`):

| Elemento de Delaunay | Dimensão | Elemento de Voronoi correspondente | Dimensão |
|---|---|---|---|
| Sítio (vértice de Delaunay) `p_i` | 0 | Célula `V_i` | 3 |
| Aresta de Delaunay `(p_i, p_j)` | 1 | Face de Voronoi (polígono bissetor `V_i ∩ V_j`) | 2 |
| **Face de Delaunay (triângulo `p_i,p_j,p_k`)** | **2** | **Aresta de Voronoi** | **1** |
| Célula de Delaunay (tetraedro `p_i,p_j,p_k,p_l`) | 3 | Vértice de Voronoi (0D) | 0 |

Ou seja, e isto é o ponto central desta auditoria: **uma aresta de Voronoi corresponde a uma
FACE (triângulo) da triangulação de Delaunay, não a uma aresta de Delaunay**. Uma aresta de
Delaunay `(p_i, p_j)` — uma ligação direta entre dois SÍTIOS — é dual de uma FACE de Voronoi
(um polígono 2D, não uma aresta), e nunca deve ser desenhada como um strut de "aresta de
célula de Voronoi". Se este código algum dia desenhar segmentos `sítio_i → sítio_j`, isso seria
uma rede de Delaunay (ou, mais precisamente, o "grafo de vizinhança de Delaunay"), e o nome
`voronoi_cell_edges_v1` estaria sendo usado de forma incorreta — este é exatamente o erro que a
instrução desta rodada pediu para nunca cometer, e que este documento existe para prevenir de
forma verificável.

**Vértice de Voronoi**: o circuncentro `c` de um tetraedro de Delaunay `(p_i,p_j,p_k,p_l)` —
o único ponto equidistante dos 4 sítios (`|c-p_i| = |c-p_j| = |c-p_k| = |c-p_l|`), sendo o
centro da esfera circunscrita.

**Aresta de Voronoi**: o segmento entre os vértices de Voronoi (circuncentros) de dois
tetraedros de Delaunay ADJACENTES (que compartilham uma face triangular) — geometricamente, o
lugar dos pontos equidistantes de exatamente 3 sítios (a interseção dos 3 planos bissetores
correspondentes). Se a face triangular compartilhada estiver na fronteira do casco convexo dos
sítios (pertence a um único tetraedro), a aresta de Voronoi correspondente é, matematicamente,
um RAIO semi-infinito (não um segmento) que parte do circuncentro na direção normal externa à
face — este é o caso de fronteira tratado explicitamente na Seção 5 abaixo (recorte pelo
domínio).

**Grafo de adjacência de Delaunay** (para deixar claro o que este código explicitamente NÃO
constrói como rede de struts): grafo cujos nós são os sítios `p_i` e cujas arestas são pares
`(p_i,p_j)` que aparecem como aresta de algum tetraedro de Delaunay. Este é o que muitas
implementações "ingênuas" de redes tipo-Voronoi usam por engano (é mais simples de calcular
porque não exige achar circuncentros) — mas produz uma malha de struts CONECTANDO OS PRÓPRIOS
SÍTIOS, geometricamente diferente de uma rede de arestas de células de Voronoi (que conecta
pontos equidistantes entre sítios, nunca os sítios em si). Este documento e o código
resultante rejeitam esta abordagem para `voronoi_cell_edges_v1`.

## 2. Estrutura escolhida para `voronoi_cell_edges_v1`

**Objetivo confirmado desta rodada** (não o objetivo alternativo baseado em Delaunay): os
struts são construídos sobre as ARESTAS DE VORONOI reais, conforme definidas acima — segmentos
entre circuncentros de tetraedros de Delaunay adjacentes, mais os raios de fronteira recortados
pelo domínio.

## 3. Algoritmo

1. **Gerar sítios** `S` dentro do domínio (bloco ou cilindro), deterministicamente por seed
   (Seção 4 do plano de implementação / `VoronoiSiteGenerator.cs`).
2. **Triangulação de Delaunay 3D** de `S`, via `MIConvexHull.Triangulation.CreateDelaunay`
   (biblioteca de terceiros, ver auditoria de dependência na Seção 6 abaixo) — devolve uma lista
   de células (tetraedros), cada uma com os 4 sítios que a formam e a lista de até 4 células
   vizinhas (`null` onde a face correspondente está na fronteira do casco convexo).
3. **Para cada célula (tetraedro) de Delaunay**: calcular seu circuncentro `c` (vértice de
   Voronoi) por solução de sistema linear 3×3 (Seção 4 abaixo). Se o determinante do sistema for
   próximo de zero (tetraedro degenerado/quase-coplanar), marcar como degenerado e excluir da
   rede (nunca produzir `NaN`/`Infinity` na saída — ver Seção 7).
4. **Para cada face triangular de cada tetraedro**:
   - Se a face for compartilhada com OUTRO tetraedro (não-fronteira, ambos não-degenerados):
     aresta de Voronoi = segmento entre os dois circuncentros.
   - Se a face estiver na fronteira do casco convexo (célula vizinha é `null`, ou é
     degenerada): aresta de Voronoi = RAIO a partir do circuncentro, na direção da normal
     externa à face triangular, recortado pela caixa delimitadora expandida do domínio (nunca
     desenhado como infinito — ver Seção 5).
5. **Deduplicar** arestas (cada face interna é visitada duas vezes, uma a partir de cada
   tetraedro adjacente) e nós (circuncentros numericamente muito próximos, dentro de uma
   tolerância relativa à escala do modelo — ver Seção 7).
6. **Recortar** a rede resultante pelo domínio real (bloco ou cilindro) — remover/truncar
   arestas fora do domínio, usando a mesma técnica de SDF (`GyroidMath.BoxSignedDistanceMm` /
   `CappedCylinderSignedDistanceMm`) já usada por Gyroid para consistência de convenção.
7. **Verificar conectividade** (componentes conexos do grafo resultante; nós isolados).
8. **Construir struts implícitos** (cápsulas por aresta + suavização por nó, ver documento de
   preparação, §6.2, estratégia `implicit_smooth_union`) e voxelizar via PicoGK — ver Seção 6 do
   plano de implementação desta rodada.
9. **Calibrar** o raio do strut por bisseção monotônica contra a porosidade medida na malha real
   (reaproveitando `GyroidMath.CalibrateByMonotonicBisection`, que já é genérico o suficiente
   para qualquer parâmetro escalar calibrado por um oráculo de medição injetado — não é
   específico de Gyroid apesar do nome dos campos).
10. **Métricas e exportação** — mesmo `GeometryMetricsCalculator.ComputeAll` (já agnóstico de
    topologia), mais métricas específicas de rede (Seção 9 do plano de implementação).

## 4. Cálculo do circuncentro de um tetraedro (fórmula fechada, determinística)

Dados 4 pontos não-coplanares `p0, p1, p2, p3`, o circuncentro `c` satisfaz
`|c-p0|² = |c-p1|² = |c-p2|² = |c-p3|²`. Subtraindo a equação de `p0` das demais, obtém-se um
sistema linear 3×3:

```
2(p1-p0)·c = |p1|² - |p0|²
2(p2-p0)·c = |p2|² - |p0|²
2(p3-p0)·c = |p3|² - |p0|²
```

Resolvido por regra de Cramer (determinante da matriz 3×3 formada pelas linhas `2(p1-p0)`,
`2(p2-p0)`, `2(p3-p0)`). O determinante é proporcional a 6× o volume (com sinal) do tetraedro —
próximo de zero exatamente quando os 4 pontos são quase-coplanares (tetraedro degenerado). Esta
é a MESMA condição que torna a triangulação de Delaunay numericamente instável para esses 4
pontos — não uma coincidência, é uma propriedade bem conhecida da dualidade Delaunay/Voronoi
(Preparata & Shamos, 1985, cap. 5).

**Tolerância de degenerescência**: `|det| < ε_relativo · (escala do modelo)³`, onde
`ε_relativo` é um parâmetro documentado (não um número mágico absoluto) — análogo ao próprio
`PlaneDistanceTolerance` que o MIConvexHull já expõe como parâmetro (default `1e-10`, mas
absoluto, não relativo à escala; este código aplica uma segunda checagem relativa à escala do
domínio, adicional à do MIConvexHull, documentada na Seção 7).

## 5. Tratamento da fronteira (arestas não-limitadas)

Diferente de uma implementação que espelha sítios nas faces da bounding box (técnica usada por
`scipy.spatial.Voronoi`/Qhull, citada no documento de preparação), esta implementação NÃO
espelha sítios. Em vez disso, trata explicitamente cada face triangular de fronteira (aquela
cuja célula-vizinha do MIConvexHull é `null`) como origem de uma aresta de Voronoi
semi-infinita: raio a partir do circuncentro do tetraedro de fronteira, na direção da normal
externa à face (calculada a partir dos 3 sítios da face, orientada para fora do tetraedro via o
4º sítio do tetraedro como referência interna). Este raio é recortado (Seção 3, passo 6) pela
mesma SDF de domínio já usada por Gyroid, garantindo que a rede final nunca ultrapasse o
domínio real (nunca apenas a bounding box) — mesmo princípio que corrigiu o recorte cilíndrico
de Gyroid no Incremento 2.1.1 (SDF real, não bounding box).

**Por que não espelhar sítios**: a técnica de espelhamento (usada por Qhull/scipy) produz um
diagrama de Voronoi "fechado" sem raios, mas exige decidir quantas cópias espelhadas gerar e em
quais faces, e pode introduzir arestas espúrias perto dos planos de espelhamento se a
implementação não for cuidadosa. A abordagem de raio-explícito-recortado-por-SDF é mais direta
de auditar (cada aresta de fronteira é rastreável a uma face de tetraedro específica, sem
sítios fantasmas) e reaproveita a mesma infraestrutura de SDF de domínio já testada e aprovada
para Gyroid — critério de simplicidade auditável, não apenas preferência de implementação.

## 6. Dependência externa: MIConvexHull (avaliação completa, Seção 2 desta rodada)

**Biblioteca escolhida**: [MIConvexHull](https://github.com/DesignEngrLab/MIConvexHull)
(`DesignEngrLab/MIConvexHull`), usada **apenas** para a triangulação de Delaunay 3D
(`Triangulation.CreateDelaunay`) — toda a extração de arestas de Voronoi, cálculo de
circuncentro, deduplicação, recorte de fronteira e verificação de degenerescência é código
próprio deste repositório (`VoronoiTessellation.cs`), não delegado à biblioteca.

Critérios de avaliação (pedidos explicitamente nesta rodada) e resposta a cada um, com
evidência:

| Critério | Resposta | Evidência |
|---|---|---|
| Origem oficial | `github.com/DesignEngrLab/MIConvexHull`, 378 estrelas, 148 commits, também publicado no NuGet como `MIConvexHull` | Verificado via fetch direto do GitHub e do NuGet Gallery nesta rodada |
| Versão | `1.1.19.1019` (NuGet), a mais recente publicada | NuGet Gallery, página de versões |
| Manutenção | **Última publicação NuGet: 19/10/2019** — aproximadamente 7 anos sem nova versão publicada. Risco real de dependência sem manutenção ativa, registrado honestamente (não escondido) | NuGet Gallery, campo "Last updated" |
| Licença | **MIT**, cabeçalho de licença presente em cada arquivo-fonte (`Copyright (c) 2015 David Sehnal, Matthew Campbell`) | Lido diretamente do arquivo-fonte `VoronoiMesh.cs` e confirmado na página do GitHub ("MIT license") |
| Suporte a .NET | `netstandard1.0` (compatibilidade extremamente ampla: netstandard1.0+, incluindo net5.0–net10.0, netcoreapp, .NET Framework 4.5+) — compatível com o `net9.0` usado pelo worker | Página do pacote NuGet, tabela de frameworks compatíveis |
| Suporte real a Voronoi 3D | **Sim, mas apenas o dual (Delaunay + adjacência de células)** — a classe `VoronoiMesh<TVertex,TCell,TEdge>` calcula a triangulação de Delaunay e monta arestas entre células adjacentes (`Source`/`Target` = tetraedros vizinhos), que são exatamente os vértices/arestas de Voronoi conforme a Seção 1 acima. **Importante, e por isso não usamos `VoronoiMesh` diretamente**: o código-fonte de `VoronoiMesh.Create` (lido nesta auditoria) SKIPA explicitamente qualquer face de fronteira (`if (af != null) edges.Add(...)`, onde `af` é a célula vizinha) — ou seja, a própria biblioteca NÃO produz os raios não-limitados de fronteira. Por isso, usamos apenas `Triangulation.CreateDelaunay` (que expõe `Cells` com `.Vertices` e `.Adjacency`, incluindo onde `Adjacency[i] == null`) e implementamos nós mesmos a extração completa de arestas (internas + raios de fronteira recortados), em vez de usar a classe `VoronoiMesh` pronta | Lido o código-fonte completo de `MIConvexHull/Triangulation/VoronoiMesh.cs` nesta auditoria (reproduzido/citado abaixo) |
| Comportamento determinístico | O algoritmo (QuickHull, elevado à dimensão 4 via mapa de levantamento parabólico padrão para obter Delaunay 3D a partir de casco convexo 4D — técnica clássica de Preparata & Shamos) processa os pontos de entrada em ordem fixa, sem uso de números aleatórios — mesma lista de sítios (mesma ordem, mesmas coordenadas) produz sempre a mesma triangulação. **Verificação própria**: esta rodada inclui um teste de determinismo dedicado (`VoronoiTessellationTests.SameSitesSameOrder_ProducesIdenticalEdgeSet`) que roda a tesselação duas vezes sobre os mesmos sítios e compara o conjunto de arestas resultante byte-a-byte (coordenadas), não apenas "não lança exceção" | Documentação do próprio algoritmo (QuickHull determinístico, sem RNG interno) + teste próprio nesta rodada |
| Risco de dependência abandonada | Real e registrado: sem release há ~7 anos. Mitigação: (a) é usada apenas para uma função matemática estável (triangulação de Delaunay não muda de definição), baixo risco de precisar de correção; (b) é usada por software de produção real e ativo (`MatterControl`, software de fatiamento/impressão 3D de código aberto com uso corrente), reduzindo o risco de bugs não descobertos em uso prático; (c) por ser puramente gerenciada (sem binário nativo), pode ser facilmente substituída por outra implementação de Delaunay 3D no futuro sem afetar o resto do pipeline, caso surja um problema real | NuGet "Used By" (TVGL, MatterControl, agg-sharp) |
| Compatibilidade com distribuição comercial | MIT permite uso comercial, modificação, redistribuição, sem exigir divulgação de código-fonte próprio — compatível com o modelo de repositório privado desta rodada (Seção 14) | Texto da licença MIT, padrão e sem cláusulas atípicas |
| Dependências transitivas | **Nenhuma** (`netstandard1.0`, "No dependencies" listado na página do NuGet) | NuGet Gallery, aba "Dependencies" |

**Decisão**: adotar `MIConvexHull` 1.1.19.1019 (MIT) via `PackageReference` no
`.csproj` do worker, exclusivamente para `Triangulation.CreateDelaunay`. Registrar em
`apps/geometry-worker/NOTICE` (Seção 16 desta rodada). Não usar `VoronoiMesh` (a classe
pronta da biblioteca) pelos motivos acima — apenas o núcleo de triangulação.

**Alternativas descartadas, com motivo**:
- `scipy.spatial.Voronoi` (Python/Qhull): exigiria processo cruzado Python↔C# só para esta
  etapa (mesmo ponto de investigação já registrado no documento de preparação, §3) — mais
  superfície de ataque/manutenção que uma dependência .NET pura, e viola a instrução desta
  rodada de "não usar serviço externo" no sentido de não introduzir uma dependência de runtime
  cruzado desnecessária quando existe alternativa .NET nativa madura.
- Implementação própria de triangulação de Delaunay 3D do zero: tecnicamente possível, mas
  desnecessariamente arriscado — um algoritmo de Delaunay 3D correto e robusto a casos
  degenerados é uma peça de engenharia de geometria computacional não-trivial (é exatamente o
  tipo de "núcleo mínimo necessário" que a instrução desta rodada permite implementar de forma
  própria SE não houver dependência adequada — mas há uma, MIT, testada em produção). Reservado
  como opção de último recurso caso `MIConvexHull` se mostre defeituoso em teste real (não
  ocorreu nesta rodada).

## 7. Tolerâncias, deduplicação e degenerescências (resumo operacional)

- **Tolerância de coincidência de sítios**: dois sítios gerados a menos de
  `siteMinSeparationMm` (derivado do domínio e `site_count`, nunca um valor absoluto fixo) são
  tratados como colisão — o gerador de sítios rejeita/reamostra deterministicamente (mesma
  seed, mesma sequência de tentativas) em vez de alimentar pontos coincidentes ao MIConvexHull
  (que pode se comportar de forma indefinida com entrada degenerada).
- **Tolerância de degenerescência de tetraedro**: `|det| < 1e-9 · L³`, onde `L` é a maior
  dimensão do domínio em mm (torna a tolerância relativa à escala do modelo, não um número
  absoluto que falharia tanto para modelos milimétricos quanto para modelos de metros).
- **Deduplicação de nós (circuncentros)**: solda por posição com tolerância
  `weldEpsilonMm = max(1e-6, L · 1e-9)` mm — mesmo princípio já usado por `SimpleMesh.Weld` para
  a malha final, aplicado aqui ao grafo de nós/arestas antes da geometria implícita.
  Deduplicação de arestas: duas arestas são a mesma se conectam o mesmo par de nós (após solda),
  em qualquer ordem.
- **Arestas degeneradas**: comprimento efetivo abaixo de `weldEpsilonMm` são descartadas (nunca
  produzem um strut de comprimento ~0).
- **Rejeição de `NaN`/`Infinito`**: qualquer coordenada de circuncentro não-finita
  (`double.IsNaN`/`double.IsInfinity`) marca o tetraedro correspondente como degenerado e o
  exclui — nunca propagada adiante.

## 8. Complexidade

- Triangulação de Delaunay via QuickHull elevado (MIConvexHull): complexidade esperada
  `O(n log n)` para sítios bem distribuídos (nosso caso — distribuições `uniform_random` e
  `jittered_grid`, Seção 3 do plano de implementação), pior caso `O(n²)` para configurações
  adversariais (Preparata & Shamos, 1985). Número de tetraedros de Delaunay é `O(n)` esperado
  para pontos em posição geral em 3D.
- Extração de arestas de Voronoi: linear no número de faces de tetraedros, `O(n)` esperado.
- Deduplicação: `O(n log n)` com uma estrutura de busca por posição (dicionário com chave
  arredondada pela tolerância de solda).
- União suave dos struts (PicoGK, Seção 6 do plano de implementação): custo domina a
  voxelização — por voxel, avaliar a SDF de cada strut próximo exige uma estrutura de aceleração
  espacial (grade de buckets), sem a qual o custo seria `O(voxels × arestas)`, proibitivo para
  redes de centenas de arestas.

## 9. Limitações desta implementação (registradas, não escondidas)

- Distribuições de sítios limitadas a `uniform_random` e `jittered_grid` nesta rodada;
  `anatomy_guided` é um ponto de extensão reservado no schema, sem implementação real (Seção 3
  do plano de implementação).
- Recorte apenas por domínios paramétricos (bloco, cilindro) — recorte por malha anatômica
  arbitrária (`shape: "anatomy_mesh"`) permanece fora de escopo, como já registrado no documento
  de preparação.
- `MIConvexHull` não recebe novas versões há ~7 anos — risco de manutenção real, mitigado
  conforme Seção 6.
- A execução real da voxelização/união suave via PicoGK (Seção 6 do plano de implementação)
  **não pode ser verificada neste sandbox Linux** — mesmo bloqueio estrutural já documentado
  para Gyroid (ADR-0007, ausência de runtime nativo PicoGK linux-x64). Toda a matemática
  PicoGK-independente (geração de sítios, tesselação, extração de arestas, deduplicação,
  conectividade, calibração via oráculo injetado) é testada de verdade neste sandbox, seguindo
  exatamente o mesmo padrão já estabelecido por `GyroidMath.cs`/`GyroidMathTests`.

## 10. Referências

- Okabe, A., Boots, B., Sugihara, K., Chiu, S.N. (2000). *Spatial Tessellations: Concepts and
  Applications of Voronoi Diagrams*, 2nd ed. Wiley.
- Aurenhammer, F. (1991). "Voronoi diagrams — a survey of a fundamental geometric data
  structure." *ACM Computing Surveys*, 23(3), 345–405.
- Preparata, F.P., Shamos, M.I. (1985). *Computational Geometry: An Introduction*. Springer
  (capítulo 5: dualidade Delaunay/Voronoi; mapa de levantamento parabólico para Delaunay via
  casco convexo em dimensão superior).
- Barber, C.B., Dobkin, D.P., Huhdanpaa, H. (1996). "The Quickhull algorithm for convex hulls."
  *ACM Transactions on Mathematical Software*, 22(4), 469–483 (algoritmo implementado por
  MIConvexHull).
- Quilez, I. "Distance functions" / "smooth minimum" (técnicas públicas de modelagem implícita
  por SDF, mesma família já citada e usada em `GyroidMath.cs` para `IntersectSignedDistance`;
  a versão suave (`smin` polinomial) é usada nesta rodada para a união dos struts, ver plano de
  implementação Seção 6).
- Schoen, A. (1970). Superfície mínima periódica Gyroid — já citada e usada em `GyroidMath.cs`,
  não repetida aqui além da referência cruzada.

## 11. Nota de confidencialidade

Este documento descreve técnica que pode ser objeto de avaliação de patenteabilidade pelo NIT
da instituição do usuário (ver `docs/private/INVENTION_NOTEBOOK_VORONOI.md`, criado nesta
mesma rodada). Este arquivo, por não conter especificamente reivindicações ou dados
experimentais proprietários — apenas definições matemáticas de domínio público (Voronoi,
Delaunay, SDF) e uma auditoria de dependência de terceiros — permanece em
`docs/architecture/` (não em `docs/private/`), mas o repositório continua privado e nenhuma
destas informações deve ser publicada em GitHub Pages ou qualquer build público de
demonstração.
