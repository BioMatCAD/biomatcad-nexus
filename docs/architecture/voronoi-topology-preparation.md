# Preparação técnica: `VoronoiTopologyProvider` (documentação, sem implementação)

Status: **DOCUMENTAÇÃO DE ARQUITETURA — NÃO IMPLEMENTADO NESTA RODADA.**

Este documento registra a preparação técnica pedida no Incremento 2.2 Alpha Pesquisa, Seção 5.
Ele descreve uma arquitetura implementável para um futuro `VoronoiTopologyProvider` que se
encaixe no contrato `ITopologyProvider`/`TopologyProviderInfo` já registrado (ver
`docs/adr/0009-topology-provider-contract.md` e `apps/api/src/biomatcad_api/services/topology_providers.py`,
onde `"voronoi"` já aparece com `status="planned"`). Nenhum código de geração Voronoi é
implementado ou executado aqui — este documento é insumo de projeto, não uma entrega funcional.

Não implemente Voronoi completo a partir deste documento sem antes: (1) revisar esta arquitetura
com o usuário/orientação, (2) confirmar que a implementação não compromete a observabilidade, a
GUI científica nem a compatibilidade das golden recipes Gyroid já aprovadas, e (3) escrever
testes equivalentes aos already existentes para Gyroid antes de declarar qualquer resultado
Voronoi como confiável.

## 0. Origem e proveniência da referência conceitual

O usuário indicou o script `scaffold_from_anatomy_auditado.py` como referência conceitual
auditada, "se estiver disponível no contexto". O arquivo foi encontrado no conhecimento
importado da sessão (`docs/scaffold_from_anatomy_auditado.py`, cache local do projeto). Ele:

- não contém cabeçalho de licença nem declaração explícita de autoria/copyright;
- cita duas referências acadêmicas no próprio docstring:
  - Fantini M, Curto M, De Crescenzio F. *Virtual and Physical Prototyping*. 2016;11(2):77-90.
    doi:10.1080/17452759.2016.1172301 (fórmula de estimativa de número de sementes a partir do
    volume vazio-alvo e do diâmetro de poro);
  - Musthafa H-SN, Walker J. *Computation*. 2024;12(12):241. doi:10.3390/computation12120241
    (espessamento de diagrama de Voronoi em struts);
- depende de bibliotecas de terceiros com licenças próprias: `numpy`, `scipy` (BSD),
  `trimesh` (MIT), `manifold3d` (Apache-2.0/MIT conforme versão), `rtree` (LGPL/MIT
  conforme versão) -- nenhuma delas foi auditada individualmente nesta rodada.

**Decisão registrada aqui, honestamente**: nenhum trecho de código deste script foi copiado
para o repositório. O script foi usado apenas como referência CONCEITUAL para descrever, em
prosa, quais etapas algorítmicas um pipeline Voronoi anatomicamente recortado precisa cobrir
(geração de sítios, diagrama limitado por espelhamento, extração de arestas, struts
cilíndricos, calibração de porosidade por bisseção, validação watertight). Antes de qualquer
implementação real baseada nesta referência, é necessário: confirmar com o autor original (se
diferente do usuário) a situação de licença e autoria, e auditar as dependências de terceiros
(`manifold3d`, `rtree`, `trimesh`) da mesma forma que `PicoGK` foi auditado para o worker C#
(ver `apps/geometry-worker/NOTICE`). Isso é trabalho de uma rodada futura, não desta.

## 1. Visão geral do pipeline conceitual

Um `VoronoiTopologyProvider` completo precisaria, no mínimo, das seguintes etapas em sequência
(cada uma detalhada abaixo):

1. Geração de sítios (sementes) dentro do domínio.
2. Construção do diagrama de Voronoi 3D limitado ao domínio.
3. Extração do grafo (vértices/arestas únicas) a partir das células.
4. Transformação das arestas em struts (geometria sólida ao longo de cada aresta).
5. Suavização dos nós (junções entre struts).
6. Recorte pelo domínio anatômico real (não apenas pela caixa delimitadora).
7. Calibração de porosidade (ajuste iterativo do raio/espessura do strut).
8. Verificação de conectividade da rede resultante.
9. Cálculo de métricas geométricas (mesmas categorias já usadas para Gyroid: volume, porosidade
   medida, área de superfície, contagem de vértices/triângulos).
10. Validação manifold/watertight antes de qualquer exportação.
11. Respeito aos limites computacionais (mesmo contrato de `compute_limits` já usado por Gyroid).

Cada etapa abaixo descreve a técnica, as alternativas consideradas e os critérios objetivos que
uma implementação real precisaria satisfazer -- não uma escolha de implementação já tomada.

## 2. Geração dos sítios

**Objetivo**: escolher um conjunto de pontos 3D (sítios/sementes) cuja densidade determine o
tamanho médio dos poros resultantes.

**Determinismo por seed**: a receita BioMatCEM já exige `seed: number` (mesmo campo usado hoje
por Gyroid para a fase da função implícita, ver `GyroidMath.SeedToPhaseShiftRad`). Um provider
Voronoi real precisaria usar um gerador pseudoaleatório determinístico semeado por este mesmo
valor (ex.: `System.Random(seed)` no worker C#, ou `numpy.random.default_rng(seed)` se a
geração de sítios for feita por um processo auxiliar Python) -- a mesma seed deve **sempre**
produzir exatamente o mesmo conjunto de sítios, byte a byte reproduzível, do mesmo modo que
Gyroid hoje documenta que a mesma seed produz a mesma fase.

**Estimativa de contagem de sítios**: a literatura (Fantini et al. 2016) estima o número de
sítios a partir do volume vazio-alvo dividido pelo volume de uma esfera de diâmetro igual ao
tamanho de poro desejado -- uma estimativa de PROJETO, não uma garantia de diâmetro de poro
medido. Qualquer implementação real precisaria deixar claro (assim como Gyroid já deixa claro
para `target_porosity_pct`) que esta é uma calibração aproximada, sujeita a medição posterior,
nunca uma garantia geométrica exata.

**Modos de distribuição** (a serem expostos como enum no schema, análogo a `topology.kind`):

- `uniform`: amostragem quase-uniforme (ex.: sequência de baixa discrepância como Sobol) dentro
  do domínio -- produz poros de tamanho mais regular, adequado a scaffolds sem gradiente
  funcional.
- `random`: amostragem pseudoaleatória simples (rejeição dentro do domínio) -- mais rápida de
  calcular, poros com maior variância de tamanho.
- `anatomy-guided`: densidade de sítios modulada por um campo escalar derivado da anatomia (ex.:
  distância à superfície cortical, região de defeito vs. osso saudável) -- necessário para
  scaffolds com gradiente de porosidade espacialmente informado pela anatomia real do paciente;
  esta é a variante cientificamente mais interessante para o projeto de tese, mas também a mais
  complexa (exige um campo de densidade auditável e documentado, não um ajuste arbitrário).

Critério objetivo mínimo para uma implementação real: dado o mesmo `seed`, domínio e modo de
distribuição, a lista de sítios gerada deve ser bit-a-bit idêntica entre execuções (mesmo teste
de determinismo que hoje existe para Gyroid via `GyroidMathTests.SeedToPhaseShiftRad_...`).

## 3. Diagrama de Voronoi / células

O diagrama de Voronoi 3D não-limitado tem células infinitas nas bordas. Uma técnica comum
(usada na referência conceitual auditada) é espelhar os sítios nas seis faces da caixa
delimitadora antes de calcular o diagrama, de forma que toda célula relevante fique limitada
pela própria estrutura do diagrama espelhado -- evita ter que recortar manualmente células
infinitas com plano de corte. A biblioteca típica para isso em Python é `scipy.spatial.Voronoi`
(que usa Qhull); em C#/.NET não há um equivalente maduro e testado no ecossistema PicoGK
atualmente, o que é um ponto real de investigação futura (rodar o cálculo do diagrama fora do
processo do worker, ou encontrar/portar uma biblioteca .NET de Voronoi 3D, ou aceitar uma
dependência de processo cruzado Python↔C# apenas para esta etapa -- todas as três opções têm
custos de manutenção e segurança que precisam de decisão explícita antes de implementar).

Critério objetivo: toda célula usada precisa ser um poliedro convexo fechado (todas as faces
com pelo menos 3 vértices, sem vértices "no infinito"); células degeneradas (Qhull relata
degenerescência) precisam de uma estratégia de fallback documentada (ex.: perturbação
determinística "joggle" com a mesma seed, nunca aleatória sem controle).

## 4. Extração do grafo

A partir das células, extrai-se um grafo não-direcionado: vértices = vértices do diagrama de
Voronoi (compartilhados entre células vizinhas), arestas = arestas de cada face de célula. Como
cada aresta interna é compartilhada por múltiplas células, é necessário deduplicar arestas por
proximidade geométrica com uma tolerância dependente da escala do modelo (não uma tolerância
absoluta fixa, que falharia tanto para modelos muito pequenos quanto muito grandes) -- mesma
lição já aplicada em `GyroidScaffoldBuilder`/`SimpleMesh.Weld` para soldagem de vértices por
posição.

Critério objetivo: o grafo final não deve conter arestas duplicadas (mesmo par de pontos dentro
da tolerância) nem arestas de comprimento efetivamente zero.

## 5. Transformação das arestas em struts

Cada aresta do grafo vira um sólido cilíndrico (ou cápsula, ver §7) de um raio/diâmetro
determinado pela calibração de porosidade (§8). Union booleana de todos os struts individuais
produz a malha da rede completa, antes do recorte anatômico.

Escolhas técnicas em aberto para uma implementação real:
- número de segmentos (faces) por seção transversal do cilindro -- trade-off entre fidelidade
  geométrica e contagem de triângulos/tempo de união booleana;
- extensão das pontas do cilindro além do ponto exato da aresta, para garantir sobreposição
  volumétrica real na junção (sem isso, cilindros com tampas planas se tocam em área nula,
  produzindo nós frágeis ou desconexos topologicamente) -- ver §7 para a alternativa via
  suavização implícita, que resolve este problema de forma diferente.

## 6. Suavização dos nós: Catmull–Clark vs. cápsulas implícitas / smooth-union

O usuário pediu explicitamente uma comparação técnica objetiva, sem escolher uma estratégia por
preferência estética. As duas abordagens abaixo são preservadas como estratégias possíveis do
futuro provider -- nenhuma é descartada aqui.

### 6.1. Subdivisão de Catmull–Clark (pós-processamento sobre malha explícita)

Catmull–Clark é um algoritmo de subdivisão de superfícies para malhas poligonais explícitas
(quads, majoritariamente), aplicado APÓS a união booleana dos struts como um passo de
suavização geométrica da malha resultante.

- **Vantagens**: técnica bem estabelecida e amplamente implementada (inclusive em bibliotecas
  de processamento de malha de uso geral); previsível e determinística sobre uma malha de
  entrada fixa; não exige recalcular a geometria implícita, apenas suaviza a malha já
  triangulada/quadrangulada.
- **Limitações**: opera sobre a malha JÁ discretizada -- herda qualquer defeito topológico da
  união booleana anterior (não-manifold, self-intersections) em vez de evitá-lo na origem;
  tende a arredondar globalmente a malha (inclusive superfícies que deveriam permanecer
  relativamente retas, como o corpo reto de um strut longe do nó), exigindo cuidado para
  suavizar seletivamente só perto das junções; a maioria das implementações assume malhas
  predominantemente quad, e a saída de uma união booleana de cilindros triangulados
  normalmente não é quad-dominante, exigindo uma etapa de requadrangulação antes de
  subdividir -- complexidade adicional real, não trivial.
- **Critério objetivo de aceitação, se escolhida**: a malha suavizada deve permanecer
  watertight e não-autointersectante após a subdivisão, e a porosidade medida não pode
  divergir da porosidade pré-suavização além de uma tolerância documentada (a suavização não
  pode silenciosamente mudar o volume sólido de forma significativa).

### 6.2. Suavização implícita via cápsulas e smooth-union no PicoGK

Alternativa que evita a malha explícita completamente até o fim: cada strut é modelado como uma
função de distância com sinal (SDF) de uma cápsula (cilindro com tampas hemisféricas, já
naturalmente suave nas pontas) em vez de um cilindro de tampa plana; as junções entre struts são
combinadas com uma operação de "união suave" (`smooth-union`/`smin`) sobre as SDFs, em vez de
uma união booleana rígida (`max`/`min` puro) -- a mesma família de operação já usada em
`GyroidMath.IntersectSignedDistance` para combinar o campo gyroid com o domínio, generalizada
para uma versão suave (ex.: `smin` polinomial de Quilez, parametrizado por um raio de mistura).

- **Vantagens**: a suavidade da junção é uma propriedade da própria função implícita, não um
  pós-processamento sobre uma malha já potencialmente degenerada -- consistente com a
  arquitetura já usada por Gyroid (`IImplicit`/`Voxels` do PicoGK), reaproveitando o mesmo
  pipeline de voxelização/meshing/weld/validação já testado; o raio de mistura da união suave é
  um parâmetro físico explícito e auditável (não uma heurística de pós-processamento), o que
  facilita expor no schema da receita e registrar no manifesto de reprodutibilidade, do mesmo
  jeito que `wall_thickness_mm` é hoje para Gyroid.
- **Limitações**: exige avaliar a SDF combinada de todos os struts vizinhos em cada voxel (custo
  computacional cresce com o número de arestas próximas a cada ponto do domínio -- precisa de
  uma estrutura de aceleração espacial, ex.: uma árvore/grade para limitar quantos struts são
  avaliados por voxel, análogo a uma `rtree`/`cKDTree` mas dentro do pipeline voxel do PicoGK);
  a literatura de `smooth-union` para redes com MUITAS arestas (uma rede Voronoi real facilmente
  tem centenas a milhares de arestas) é menos madura que para poucos primitivos isolados --
  precisa de prototipagem e medição de desempenho antes de assumir viabilidade em tempo
  aceitável para receitas de tamanho realista.
- **Critério objetivo de aceitação, se escolhida**: o raio de mistura deve ser um parâmetro
  explícito no schema (unidade em mm, como todos os outros parâmetros geométricos do BioMatCEM);
  a porosidade medida deve continuar calibrável pelo mesmo mecanismo de bisseção já usado por
  Gyroid (measured vs. target, dentro de uma tolerância documentada); o tempo de execução para
  uma receita de tamanho comparável às golden recipes atuais deve ficar dentro dos
  `compute_limits` já existentes no schema, sem introduzir um novo limite invisível.

### 6.3. Recomendação de próxima etapa (não uma decisão definitiva)

Nenhuma das duas é escolhida aqui. A recomendação para quando a implementação real for
priorizada é: prototipar a suavização implícita (§6.2) PRIMEIRO em uma escala pequena (dezenas
de arestas, não centenas), medindo tempo de voxelização e comparando qualidade da malha contra
uma versão sem suavização (união booleana rígida + Catmull-Clark de §6.1 como comparação),
porque a suavização implícita se encaixa sem adaptação estrutural no pipeline já existente
(`IImplicit`/`Voxels`/`Library.Go`), enquanto Catmull-Clark exigiria um pipeline de
pós-processamento de malha novo, hoje inexistente no worker. Isso é uma recomendação de ordem de
investigação, não uma decisão de arquitetura definitiva -- ambas permanecem registradas como
estratégias possíveis do `VoronoiTopologyProvider`.

## 7. Recorte pelo domínio anatômico

Análogo ao recorte booleano já existente para Gyroid (`GyroidDomainImplicit`, interseção SDF
entre o campo gyroid e o domínio bloco/cilindro via `GyroidMath.IntersectSignedDistance`), a
rede de struts Voronoi precisaria ser recortada pelo domínio real -- que no caso de scaffolds
anatômicos pode ser uma malha STL de entrada (não apenas bloco/cilindro paramétrico), exigindo
uma SDF derivada de uma malha arbitrária (ex.: campo de distância assinada calculado a partir da
malha da anatomia) em vez de uma fórmula fechada como as já implementadas para bloco/cilindro.
Isso é uma extensão real do contrato `domain` do schema BioMatCEM (hoje `shape: "block" |
"cylinder"`), que precisaria ganhar um terceiro `shape: "anatomy_mesh"` com uma referência a um
artefato STL de entrada -- mudança de schema não trivial, fora do escopo desta rodada.

## 8. Calibração de porosidade

Mesma filosofia já aplicada a Gyroid (`GyroidMath.CalibratePorosityByBisection` +
`MonotonicCalibrationResult`, calibração fechada contra a malha real, nunca só a estimativa
analítica): para Voronoi, o parâmetro calibrado seria o raio do strut (ou o raio de mistura da
união suave, se a estratégia de §6.2 for escolhida), ajustado por bisseção até que a porosidade
MEDIDA na malha final (após recorte pelo domínio) fique dentro de uma tolerância do
`target_porosity_pct` solicitado -- nunca medida na caixa delimitadora, sempre no volume
efetivamente recortado, do mesmo jeito que a referência conceitual auditada já faz (calibração
"dentro da anatomia", não na bounding box).

## 9. Conectividade

Ao contrário de Gyroid (uma única superfície periódica contínua por construção), uma rede de
struts Voronoi pode, em princípio, produzir componentes desconectados (se a união booleana ou a
suavização falhar em alguma junção). Uma implementação real precisaria de uma verificação
explícita de conectividade (ex.: grafo de adjacência de triângulos/componentes conexos da malha
final) e reportar isso como um campo de métrica dedicado (análogo a `is_watertight` hoje) --
nunca assumir conectividade implicitamente.

## 10. Métricas

O mesmo conjunto de métricas já reportado por `GeometryMetricsCalculator` para Gyroid (volume,
porosidade medida, área de superfície, contagem de vértices únicos, contagem de triângulos,
watertight) se aplicaria a Voronoi sem alteração de contrato -- é exatamente o objetivo da
abstração `ITopologyProvider`: o restante do sistema (jobs, artefatos, visualizador,
observabilidade) não precisa saber qual topologia gerou a malha, apenas consumir o mesmo
contrato de métricas. Métricas adicionais específicas de Voronoi que uma implementação real
poderia justificar adicionar (como campos OPCIONAIS, nunca substituindo os já existentes):
contagem de sítios usados, distância média/mediana/percentis entre vizinhos mais próximos
(distribuição espacial dos sítios), contagem de arestas únicas, contagem de componentes conexos.

## 11. Manifold / watertight

Mesmo padrão de validação já aplicado a Gyroid (`StlExporter.ValidateWrittenFile`, validação
pós-gravação lendo o STL de volta e conferindo triangle count/watertight, nunca confiando
apenas na malha em memória): uma implementação Voronoi real precisaria da mesma dupla checagem
antes de reportar sucesso -- nunca declarar `is_watertight=true` sem uma verificação
pós-gravação real, e nunca gravar um artefato STL de uma malha que falhou nessa verificação
(mesmo comportamento de `STL_VALIDATION_FAILED_AFTER_WRITE` + limpeza de artefatos parciais já
existente em `Program.cs`).

## 12. Limites computacionais

O custo computacional de uma rede Voronoi cresce com o número de sítios (mais sítios → mais
arestas → mais struts → união booleana mais cara) de forma potencialmente muito mais acentuada
que a voxelização de Gyroid (que é dominada pela resolução do voxel, não pelo número de
elementos). Uma implementação real precisaria, no mínimo:

- estimar o número de sítios/arestas ANTES de qualquer execução pesada (mesmo padrão do
  `VOXEL_COUNT_LIMIT_EXCEEDED`/`MEMORY_LIMIT_EXCEEDED` já existente para Gyroid), rejeitando com
  erro estruturado receitas cujo tamanho de poro solicitado implique um número de sítios
  proibitivo para o volume do domínio -- exatamente como a referência conceitual auditada já
  rejeita explicitamente (`max_seeds` excedido) em vez de silenciosamente tentar processar e
  travar;
- um novo limite explícito no schema (`compute_limits.max_site_count` ou equivalente), análogo
  a `max_voxel_count`, nunca reaproveitando o limite de voxel como proxy indireto de custo de
  união booleana (são custos de natureza diferente).

## 13. Impacto no schema BioMatCEM (não implementado nesta rodada)

Para que uma implementação real de Voronoi seja aceita, o JSON Schema
(`schemas/biomatcem/geometry-recipe-v1.schema.json`) precisaria de uma nova versão (`2.0.0` ou
uma extensão retrocompatível), pois hoje `topology.kind` é `"const": "gyroid"` e `domain.shape`
só aceita `"block" | "cylinder"`. Esta rodada NÃO altera o schema -- as três golden recipes
existentes continuam validando exatamente como antes (nenhuma mudança de schema foi feita, ver
commit do contrato `TopologyProvider`, que manteve o schema intocado deliberadamente).

## 14. Resumo do que fica para uma implementação futura

Este documento não implementa: geração real de sítios, cálculo real do diagrama de Voronoi,
união booleana de struts, qualquer uma das duas estratégias de suavização, recorte por malha
anatômica arbitrária, ou qualquer novo campo de schema. Ele registra a arquitetura, as
alternativas técnicas com vantagens/limitações objetivas, e os critérios de aceitação que uma
implementação futura precisaria satisfazer para ser aceita com o mesmo rigor já aplicado a
Gyroid neste incremento.
