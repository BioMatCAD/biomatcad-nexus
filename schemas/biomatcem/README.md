# BioMatCEM — Engenharia Computacional de Biomateriais (Incremento 2.1, semântica corrigida no 2.1.1)

BioMatCEM é o nome do subsistema próprio do BioMatCAD Nexus responsável por gerar geometria
científica (scaffolds/estruturas) a partir de uma receita declarativa validada — não é uma cópia
nem deriva de nenhum software proprietário de terceiros. A metodologia (parametrizar domínio +
topologia + resolução + limites computacionais, validar, enfileirar, executar em worker
separado, medir, empacotar com reprodutibilidade) segue a prática pública de Computational
Engineering aplicada a biomateriais porosos, sem copiar implementação de nenhuma ferramenta
comercial específica. Ver ADR-0006 para a decisão de versionamento do schema, ADR-0008 para a
semântica espessura/isovalor corrigida no Incremento 2.1.1, e
`apps/geometry-worker/WORKER_STATUS.md`/ADR-0007 para o estado real (bloqueado) da execução
geométrica neste ambiente.

## O que existe nesta versão (v1 / Incremento 2.1)

- Um único schema versionado: `geometry-recipe-v1.schema.json` (JSON Schema Draft 2020-12).
- Uma única topologia: **gyroid** (superfície mínima triplamente periódica, fórmula clássica de
  Alan Schoen, 1970, domínio público — `sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x) = isovalue`).
- Dois domínios: **block** (caixa retangular) e **cylinder**.
- Dois modos de execução: **preview** (resolução reduzida, iteração rápida) e **final**.

Qualquer topologia ou domínio adicional (TPMS Schwarz-P, malha importada, etc.) é um novo
incremento, com novo valor de `schema_version` — nunca uma edição retroativa do schema v1
(ADR-0006).

## Campos da receita (resumo; ver o `.schema.json` para a definição normativa)

| Campo | Obrigatório | Descrição |
|---|---|---|
| `schema_version` | sim | `"1.0.0"` — constante nesta versão. |
| `domain.shape` / `domain.dimensions_mm` | sim | `block` (x/y/z em mm) ou `cylinder` (raio/altura em mm). |
| `topology.kind` | sim | sempre `"gyroid"` nesta versão. |
| `topology.cell_size_mm` | sim | tamanho da célula unitária TPMS, em mm. |
| `topology.wall_thickness_mm` | **sim** (obrigatório desde o Incremento 2.1.1) | único controlador de espessura de parede, em mm — ver ADR-0008. |
| `topology.isovalue` | **não** (opcional desde o Incremento 2.1.1, default `0.0`) | centro da banda da superfície implícita — NÃO controla espessura (ver ADR-0008). |
| `topology.target_porosity_pct` | não | porosidade-alvo aproximada (calibra `wall_thickness_mm` efetivo por bisseção — estimativa, não garantia). |
| `resolution.voxel_size_mm` | não (default 0.2) | resolução de voxelização, em mm. |
| `mode` | sim | `preview` ou `final`. |
| `seed` | sim | semente determinística (mesma receita + mesma versão do worker ⇒ mesmo resultado). |
| `compute_limits.*` | sim | `max_duration_seconds`, `max_memory_mb`, `max_voxel_count` — limites obrigatórios, sem default implícito. |
| `output_formats` | sim | array com `stl` e/ou `vdb` — `vdb` só é honrado se o worker instalado suportar oficialmente; caso contrário o job falha com `OUTPUT_FORMAT_UNSUPPORTED` (nunca degradado silenciosamente para STL apenas). |

Todas as dimensões e resoluções têm unidade explícita no próprio nome do campo (`_mm`) — nunca
uma unidade implícita, conforme exigido pelo Prompt Mestre.

**Semântica espessura/isovalor (Incremento 2.1.1, ADR-0008)**: no Incremento 2.1, os dois campos
tinham papéis ambíguos/sobrepostos, sem regra clara de precedência quando ambos eram informados.
Desde o 2.1.1, `wall_thickness_mm` é obrigatório e é o único controlador de espessura;
`isovalue` é opcional e é apenas o centro da banda sólida. Combinações fisicamente
contraditórias (ex.: `wall_thickness_mm >= cell_size_mm / 2`) são rejeitadas com
`TOPOLOGY_PARAMETERS_INCONSISTENT` antes de qualquer execução.

## Fluxo de validação (duas camadas, nunca uma só)

1. **Frontend** (`apps/web/src/pages/RecipeEditorPage.tsx`): chama
   `POST /api/v1/recipes/validate` (debounced, 300ms) contra o backend real; no modo demo
   (GitHub Pages, sem backend) usa `recipeValidationOffline.ts` — desde o Incremento 2.1.1, essa
   validação usa Ajv (`ajv/dist/2020`) contra uma cópia local do MESMO schema real
   (`apps/web/src/schemas/geometry-recipe-v1.schema.json`), sincronizada e verificada
   byte-a-byte por `schemaSync.test.ts` — substituindo as ~15 regras manuais reimplementadas em
   JS do Incremento 2.1, que podiam divergir do schema oficial. Continua rotulada como auxiliar
   de demonstração, nunca como fonte de verdade.
2. **Backend** (`services/recipe_service.py`): `jsonschema.Draft202012Validator` contra o
   `.schema.json` é a **única** fonte de verdade. Roda de novo em toda criação/validação de
   receita, mesmo que o frontend já tenha validado — o backend nunca confia cegamente no
   cliente.

Qualquer campo fora do schema é rejeitado (`additionalProperties: false` em todos os níveis) —
esse é o mecanismo que impede o envio de código/expressões arbitrárias pelo navegador (Prompt
Mestre, item 2 do Incremento 2.1).

## Canonicalização e checksum

Toda receita validada é serializada em forma canônica (chaves ordenadas, separadores compactos)
antes de ser persistida, e recebe um `checksum_sha256` real, calculado pelo backend
(`compute_checksum()` em `recipe_service.py`). O `fingerprint()` do modo demo (FNV-1a) **não**
é criptográfico e nunca é comparado contra o checksum real — existe apenas para dar uma
indicação visual de mudança no cliente sintético.

## Receitas de exemplo (golden recipes)

Três receitas pequenas e versionadas em `golden-recipes/` (bloco, cilindro, preview de baixa
resolução) — ver `golden-recipes/README.md`. Usadas em testes de schema, criação de job e no
caminho de falha controlada do worker. Nenhuma contém dados clínicos.

## Limitação conhecida (Incremento 2.1 e 2.1.1)

A geometria real gerada a partir de uma receita BioMatCEM (o STL determinístico do scaffold
gyroid em si) não pôde ser produzida nem verificada neste sandbox — o worker C#/PicoGK está
bloqueado por ausência de runtime nativo linux-x64 no pacote oficial (ADR-0007), e isso não
mudou no Incremento 2.1.1. O que está testado e verificado é: validação de schema (24 testes,
incluindo a nova semântica espessura/isovalor e a rejeição de combinações contraditórias),
canonicalização, checksum, contrato JSON de entrada/saída do worker, a matemática do gyroid
independente de PicoGK (`GyroidMath.cs`, 27 testes) e o caminho de falha controlada quando o
worker real é invocado neste ambiente. A conversão espessura→banda-isovalor aplicada de fato a
uma malha voxelizada real permanece não verificada até a execução do worker no Windows do
usuário (ver `docs/examples/WINDOWS_EXECUTION_KIT.md`).
