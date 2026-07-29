# ADR-0008: Semântica inequívoca de `wall_thickness_mm` e `isovalue` na receita Gyroid

- Status: Aceita
- Data: 2026-07-29 (Incremento 2.1.1)
- Decisor: Adler Lima Botelho de Azevedo (usuário), a partir de defeito encontrado em auditoria
  do Incremento 2.1.

## Contexto

A superfície mínima periódica (TPMS) Gyroid é definida pela função implícita clássica de Alan
Schoen (1970), de domínio público:

```
F(x, y, z) = sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x)
```

Por si só, `F(x,y,z) = isovalue` define uma superfície matemática de espessura zero — não
manufaturável. Para gerar um sólido imprimível é preciso "engordar" essa superfície numa banda em
torno de um valor central. No schema `geometry-recipe-v1.schema.json` do Incremento 2.1, tanto
`isovalue` quanto `wall_thickness_mm` existiam como campos opcionais, sem uma regra explícita de
precedência entre os dois quando ambos eram informados, e sem nenhuma regra que impedisse
combinações fisicamente impossíveis (por exemplo, uma banda mais larga que a própria célula
unitária). A auditoria do Incremento 2.1 identificou isso como uma ambiguidade real: um cliente
da API não tinha como saber, com certeza, qual campo controlava a espessura de parede final, nem
o sistema recusava combinações sem sentido físico.

## Decisão

1. **`wall_thickness_mm` passa a ser obrigatório** em `topology` e é o **único** parâmetro que
   controla a espessura de parede do scaffold. O worker converte esse valor (em mm) numa
   meia-largura de banda no espaço de campo (adimensional) através de uma aproximação
   documentada e determinística (`GyroidMath.WallThicknessMmToHalfBandWidth`, ver comentário no
   próprio arquivo `apps/geometry-worker/GyroidMath.cs`): usa a magnitude média do gradiente de
   `F` em coordenadas normalizadas (`sqrt(2) * escala`, onde `escala = 2π / cell_size_mm`) como
   fator de conversão. Isso é uma **aproximação**, não uma distância euclidiana exata — a
   superfície gyroid não tem forma fechada conhecida de distância assinada exata, ao contrário de
   primitivas convexas simples como bloco e cilindro.
2. **`isovalue` passa a ser opcional** (default `0.0`) e passa a significar exclusivamente o
   **centro** da banda sólida — `{ F(x,y,z) ∈ [isovalue - d, isovalue + d] }`, onde `d` vem de
   `wall_thickness_mm` pela conversão do item 1. `isovalue = 0.0` é a célula "balanceada"
   (~50% de fase sólida/vazia, antes de qualquer calibração de porosidade). `isovalue` nunca mais
   controla espessura.
3. **Combinações fisicamente contraditórias são rejeitadas na validação**, antes de qualquer
   execução, com erro estruturado `TOPOLOGY_PARAMETERS_INCONSISTENT` — por exemplo
   `wall_thickness_mm >= cell_size_mm / 2` (banda maior que a própria célula) ou uma banda cujo
   deslocamento a partir de `isovalue` extrapolaria a amplitude máxima teórica da função gyroid
   (que é limitada a `[-3, 3]`, mas na prática o schema já restringe `isovalue` a `[-1.5, 1.5]`
   para manter as combinações num regime fisicamente razoável).
4. **`target_porosity_pct` (opcional) calibra `wall_thickness_mm` efetivo**, não `isovalue`.
   Quando presente, o worker roda uma busca por bisseção determinística
   (`GyroidMath.CalibratePorosityByBisection`) sobre a meia-largura de banda, usando uma
   estimativa analítica de fração de volume sólido por amostragem em grade regular
   (`EstimateSolidFractionForBand`) como oráculo — nunca o PicoGK. O manifesto registra o valor
   de espessura solicitado, o valor efetivamente aplicado após calibração, e o erro residual.

## Consequências

- A API do schema fica mais restritiva (`wall_thickness_mm` obrigatório) — isso é uma mudança
  incompatível com receitas do Incremento 2.1 que omitiam esse campo; as golden recipes foram
  todas atualizadas para incluí-lo explicitamente (ver `schemas/biomatcem/golden-recipes/`).
- A conversão espessura→banda continua sendo uma **aproximação documentada**, não uma garantia de
  espessura de parede exata pós-impressão — isso é inerente à ausência de uma forma fechada de
  distância exata para a superfície gyroid, não uma limitação introduzida por esta decisão.
  Qualquer uso que exija tolerância dimensional certificada precisa de medição pós-fabricação
  (fora do escopo deste software).
- A premissa de monotonicidade (porosidade decresce com o aumento da meia-largura de banda),
  usada pela calibração por bisseção, é documentada como válida apenas dentro da faixa de
  parâmetros aceita pelo schema — não foi provada como identidade matemática geral.
- Esta correção foi validada apenas por testes unitários matemáticos (`GyroidMathTests.cs`,
  parte dos 48 testes xUnit do Incremento 2.1.1), independentes do PicoGK. A conversão
  espessura-mm→banda-isovalor real, aplicada a uma malha voxelizada de verdade, ainda depende da
  execução real do worker no Windows do usuário (ver ADR-0007, atualização Incremento 2.1.1, e
  `docs/examples/WINDOWS_EXECUTION_KIT.md`) para ser confirmada como correta na prática, não
  apenas correta na teoria.
