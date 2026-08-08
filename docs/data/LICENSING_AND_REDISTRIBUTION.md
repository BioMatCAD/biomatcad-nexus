# Licenciamento e Redistribuição (Incremento 2.3, Rodada 1)

Este documento descreve como o modelo de dados científico trata licenciamento e permissão de
redistribuição de dado de terceiros — um requisito transversal a toda fonte externa candidata
listada em `SOURCE_REGISTRY_POLICY.md`.

## Por que isso importa desde a fundação do modelo

Um banco de dados científico que agrega conteúdo de fontes de terceiros (bases públicas,
publicações, fichas técnicas de fornecedores) precisa registrar, desde o desenho inicial das
tabelas, se cada fonte permite redistribuição — e não apenas se ela é "gratuita" ou "de acesso
aberto". Acesso aberto para LEITURA não implica automaticamente permissão de REDISTRIBUIÇÃO
(reempacotar e servir o dado por meio da própria API do BioMatCAD Nexus). Essa distinção é a
razão de `ScientificSource.redistribution_status` existir como campo obrigatório desde esta
rodada, mesmo sem nenhum conector real ainda implementado.

## O campo `redistribution_status`

`ScientificSource.redistribution_status` (enum `RedistributionStatus`) aceita três valores:

- **`allowed`** — a fonte confirmadamente permite redistribuição, com os termos registrados em
  `ScientificSource.terms_of_use`/`license`.
- **`prohibited`** — a fonte proíbe explicitamente a redistribuição.
- **`unknown`** — a permissão não foi confirmada. **Este é o valor padrão** de todo registro
  novo (`default=RedistributionStatus.UNKNOWN`), e é a postura de segurança adotada em toda a
  documentação desta rodada (ver `SOURCE_REGISTRY_POLICY.md`, onde nenhuma fonte candidata é
  marcada como `allowed` sem uma confirmação formal futura).

**Nunca se assume `allowed` por omissão.** Uma fonte cujo status de redistribuição não foi
explicitamente verificado permanece `unknown` indefinidamente, mesmo que pareça razoavelmente
aberta (ex.: bases mantidas por instituições públicas) — a confirmação é sempre um passo
explícito e documentado, não um valor implícito.

## Onde a licença é registrada

- `ScientificSource.license`, `ScientificSource.terms_of_use`, `ScientificSource.version`,
  `ScientificSource.accessed_at` — a licença, os termos de uso completos (texto livre), a versão
  da fonte no momento do acesso, e a própria data de acesso, para que uma mudança futura de
  licença por parte da fonte não seja confundida com o estado vigente no momento em que o dado
  foi coletado.
- `CrystalStructureReference.license` — licença específica de uma estrutura cristalográfica de
  referência (pode divergir da licença geral da base, caso a caso).

## Regra de aplicação nesta rodada

Como nenhum conector real de ingestão existe ainda (ver `SOURCE_REGISTRY_POLICY.md` e o
`IngestionRun` fictício do seed sintético), nenhuma decisão de redistribuição precisou ser
tomada de fato nesta rodada — o objetivo aqui é apenas garantir que o modelo de dados **já
force** essa decisão a ser registrada explicitamente antes que qualquer dado real de terceiros
possa ser ingerido em uma rodada futura. Um conector de ingestão futuro que tentar inserir dado
de uma fonte com `redistribution_status=prohibited` deve ser bloqueado na camada de aplicação
(regra a implementar junto do primeiro conector real, fora do escopo desta rodada).

## Referências (fonte) vs. conteúdo integral

`BibliographicReference` armazena apenas **metadados** de uma publicação (DOI, título, autores,
veículo, ano, URL) — nunca o texto integral do artigo. Mesmo quando os metadados de uma fonte
como Crossref são de domínio público (CC0), isso nunca implica em licença para redistribuir o
conteúdo integral do artigo referenciado, que segue os termos da editora original.

## Dados declarados por fornecedor

`SupplierProduct.declared_properties` armazena o dado exatamente como declarado pelo fornecedor,
sempre com `evidence_type=SUPPLIER_DECLARED` quando promovido a uma `PropertyObservation` — a
ficha técnica comercial de um fornecedor tipicamente não concede permissão de redistribuição
integral do seu catálogo (ver `SOURCE_REGISTRY_POLICY.md`, seção "Bases de fornecedores
comerciais"), então o campo `Supplier`/`SupplierProduct` em si não referencia um
`ScientificSource.redistribution_status` — cada implementação futura de conector de fornecedor
precisará avaliar isso individualmente, por fornecedor, antes de ingerir qualquer conteúdo em
massa.
