# Modelo de Dados Científico (Incremento 2.3, Rodada 1)

Este documento descreve o contrato de domínio implementado em
`apps/api/src/biomatcad_api/models/scientific_data.py` e a migração Alembic
`4920cd8fd160_incremento_2_3_fundacao_do_banco_de_.py`. É a fundação persistente do banco de
dados científico de materiais, biomateriais, substâncias químicas, fármacos, formulações,
nanomateriais, produtos de fornecedor, estruturas cristalográficas e evidência bibliográfica.

Esta rodada **não** faz nenhuma coleta de dados externa nem importação em massa de bases reais
— ver `SOURCE_REGISTRY_POLICY.md` para o registro de fontes candidatas futuras. O objetivo é
exclusivamente tornar o sistema capaz de armazenar dado científico com proveniência completa.

## Princípio central

Um valor científico nunca existe desacompanhado de: fonte, data de acesso, método/contexto de
medição (quando disponível), unidade, condições experimentais relevantes, nível de evidência,
estado de revisão e licença/termos de reutilização conhecidos (ainda que "desconhecidos" seja o
próprio valor registrado — nunca se assume permissão por omissão).

Nenhuma tabela deste modelo sobrescreve silenciosamente um valor divergente. Observações de
fontes diferentes — ou da mesma fonte em condições diferentes — sempre coexistem como linhas
separadas em `PropertyObservation`. A única forma de duas observações serem consideradas
"a mesma" é terem fingerprint SHA-256 idêntico (ver seção "Deduplicação" abaixo).

## As 12 entidades

### 1. `ScientificEntity`

A entidade científica canônica — o registro central ao qual identificadores externos,
observações de propriedades, evidência biológica, produtos de fornecedor e referências
cristalográficas se conectam.

Campos: `id` (UUID), `organization_id` (nullable — `NULL` = registro global/público, visível a
qualquer usuário autenticado; não-nulo = privado a essa organização), `entity_type` (enum:
`biomaterial`, `chemical_substance`, `drug`, `formulation`, `nanomaterial`, `other`),
`preferred_name`, `description`, `review_status` (enum `CurationState`: `draft`, `reviewed`,
`rejected`, `deprecated`), `is_active` (soft-delete — nunca apaga evidência histórica associada;
ver teste `test_soft_delete_of_entity_preserves_related_evidence`), `created_at`, `updated_at`.

Nunca é, por si só, um produto comercial (ver `SupplierProduct`) nem uma receita geométrica
(`GeometryRecipe`, domínio de fabricação/topologia distinto, Incremento 2.1).

### 2. `ScientificIdentifier`

Identificador externo (namespace + valor), por exemplo CID, ChEBI, ChEMBL, CAS, DOI, PMID, COD,
PDB — nenhum desses conectores é implementado nesta rodada; o modelo apenas contempla o
armazenamento futuro. Restrição única em `(namespace, identifier_normalized)` para impedir
duplicidade silenciosa (dois registros do mesmo identificador em grafias diferentes). Campo
`verification_status` (`unverified`, `verified`, `disputed`).

### 3. `ScientificSource`

Registro de uma fonte de dados: nome, tipo (`database`, `publisher`, `supplier`,
`institutional`, `other`), URL base, editora, licença, versão, termos de uso, data de acesso, e
`redistribution_status` (`allowed`, `prohibited`, `unknown` — o padrão seguro é sempre
`unknown`, nunca `allowed` por omissão).

### 4. `BibliographicReference`

Referência bibliográfica: DOI/PMID/outro identificador (todos opcionais — nunca inventados
quando a fonte não os fornece), título, autores, veículo, ano, URL, fonte dos metadados.

### 5. `PropertyDefinition`

Vocabulário canônico de propriedades (ex.: `young_modulus`, `melting_point`): chave canônica
única, nome, dimensão física/biológica, unidade canônica, tipo de valor, domínio de
aplicabilidade. A unidade canônica é declarada aqui uma única vez; cada observação individual
registra sua própria unidade original.

### 6. `PropertyObservation`

O núcleo do domínio: um único valor científico observado, sempre com proveniência completa.

Campos principais: entidade, definição de propriedade, valor (numérico, faixa min/max, ou
texto), `unit_original` (obrigatória) e `value_normalized` (opcional — só preenchida quando a
conversão para a unidade canônica for comprovada, nunca uma estimativa silenciosa), método,
condições experimentais explícitas (`condition_temperature_k`, `condition_pressure_kpa`,
`condition_ph`, `condition_medium`, mais `conditions_extra` como JSON aberto para qualquer outra
condição não coberta pelos campos fixos), incerteza (`uncertainty_low`/`uncertainty_high`),
`evidence_type` (ver seção seguinte), referência bibliográfica, fonte, localização na fonte
(página/tabela/figura), produto de fornecedor relacionado (quando a observação for
`supplier_declared`), `review_status`, notas, e `dedup_fingerprint`.

**Nunca é atualizada em memória por cima de um valor divergente anterior.** Uma nova observação
de fonte diferente (ou condições diferentes) é sempre uma NOVA linha. O único mecanismo de
"correção" é uma nova `ReviewDecision` que muda o `review_status`, nunca a reescrita do valor em
si.

#### Distinção obrigatória de `EvidenceType`

Seis valores, nunca confundidos entre si (princípio 5 da rodada — nenhum, por si só, é validação
clínica): `experimental`, `calculated`, `supplier_declared`, `inferred`, `synthetic_demo`,
`unverified`.

#### Deduplicação por fingerprint

`compute_observation_fingerprint(...)` calcula um SHA-256 determinístico sobre
`entidade|propriedade|fonte|valor_numérico|valor_min|valor_max|valor_texto|unidade|método|condições`.
Duas observações só são consideradas duplicatas verdadeiras se todos esses campos forem
idênticos — qualquer diferença (incluindo apenas as condições experimentais) produz um
fingerprint diferente, e a restrição única `uq_property_observation_fingerprint` garante isso no
nível de banco, não apenas de aplicação (ver teste
`test_true_duplicate_fingerprint_is_rejected_by_unique_constraint`, uma mutação manual que prova
a rejeição real).

### 7. `BiologicalEvidence`

Evidência biológica associada a uma entidade: tipo de ensaio, modelo biológico, espécie/
linhagem celular/organismo (quando aplicável), endpoint, resultado, dose/concentração, duração,
condições (JSON), referência e fonte. Campo `research_classification_only` (sempre `True` nesta
rodada, não configurável para `False` por nenhum caminho de API) — nunca apresentada como
validação clínica.

### 8. `Supplier` e `SupplierProduct`

Um fornecedor (nome, URL, região) e seus produtos comerciais (catálogo/SKU — único por
fornecedor, nome comercial, URL, região, lote, datas de validade de registro, propriedades
declaradas pelo fornecedor em JSON, sempre rotuladas como tal). `SupplierProduct.entity_id` é
opcional e nullable: um produto pode existir sem vínculo com uma entidade canônica ainda
(pendente de curadoria) — e mesmo quando vinculado, **o produto nunca substitui ou é tratado
como a entidade em si** (princípio 3 da rodada; ver teste
`test_supplier_product_is_never_the_canonical_entity`).

### 9. `CrystalStructureReference`

Referência a uma estrutura cristalográfica externa (ex.: COD, RCSB PDB): banco, accession,
fórmula, sistema cristalino, grupo espacial, parâmetros de célula, URL, licença, checksum de
arquivo (para uso futuro). Restrição única em `(database_name, accession_id)`. **Nenhum arquivo
cristalográfico (CIF/PDB) é baixado, incorporado ou redistribuído nesta rodada** — apenas
metadados de referência.

### 10. `IngestionRun`

Execução de um conector de ingestão: fonte, nome/versão do conector, início/fim, parâmetros,
contagens (`received_count`, `created_count`, `updated_count`, `skipped_count`,
`rejected_count`), status (`running`, `succeeded`, `partial`, `failed`), erros estruturados
(JSON), checksum do payload bruto (para preservação futura), correlação com `AuditEvent`.
**Nenhum conector real existe nesta rodada** — a tabela documenta o contrato para quando um
conector (PubChem, ChEBI etc.) for implementado em rodada futura, exercitada nos testes e no
seed via um conector fictício (`synthetic_demo_connector`).

### 11. `ReviewDecision`

Trilha de decisão de revisão: objeto revisado (via par polimórfico `subject_type`+`subject_id`,
evitando uma FK física por tipo revisável), decisão (`approved`, `rejected`,
`changes_requested`), revisor, justificativa, timestamp, estado anterior/novo. **Append-only por
convenção da camada de aplicação** — nenhum endpoint de `UPDATE`/`DELETE` é exposto, mesmo padrão
já usado por `AuditEvent` (Incremento 1.1). Isso não é imutabilidade garantida por
infraestrutura, apenas convenção de aplicação — mesma ressalva já registrada para `AuditEvent`.

## Compatibilidade com `MaterialRecord` (Incremento 2.1)

`MaterialRecord`/`MaterialProperty`/`ScientificReference` (modelo legado do Incremento 2.1)
permanecem **completamente intocados**, com a mesma tabela `material_records` já referenciada
por `GeometryJob.material_id` (orquestração de jobs geométricos) e por `manifest_service.py`
(geração de manifesto de artefatos). `MaterialRecord` ganha apenas uma coluna nova e opcional
(`scientific_entity_id`, nullable, sem backfill) para permitir consolidação futura entre os dois
modelos sem quebrar nenhum contrato existente — sempre `NULL` para registros já existentes.
Nenhum endpoint, teste ou comportamento do Incremento 2.1/2.2 é alterado por este vínculo.

## Diagrama de relacionamento (simplificado)

```
ScientificEntity ──┬── ScientificIdentifier (N)
                    ├── PropertyObservation (N) ── PropertyDefinition
                    │                          └── ScientificSource
                    │                          └── BibliographicReference
                    │                          └── SupplierProduct (quando supplier_declared)
                    ├── BiologicalEvidence (N) ── BibliographicReference / ScientificSource
                    ├── SupplierProduct (N, opcional) ── Supplier
                    ├── CrystalStructureReference (N)
                    └── ReviewDecision (N, via subject_type/subject_id)

MaterialRecord (Incremento 2.1) ──[FK opcional, nullable]── ScientificEntity
IngestionRun ── ScientificSource
```

Ver `PROVENANCE_AND_CURATION.md` para o fluxo de curadoria/revisão e
`docs/api/` (a atualizar em rodada futura) para o contrato HTTP completo da API mínima de
pesquisa (`routers/scientific_data.py`).
