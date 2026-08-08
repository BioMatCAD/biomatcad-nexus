# Proveniência e Curadoria (Incremento 2.3, Rodada 1)

Este documento descreve o modelo de autorização, o fluxo de curadoria/revisão, e as regras de
proveniência aplicadas ao banco de dados científico (ver `SCIENTIFIC_DATA_MODEL.md` para o
contrato de entidades).

## Escopo de organização vs. registro global

Todas as tabelas com um campo `organization_id` (`ScientificEntity`, `PropertyObservation`,
`BiologicalEvidence`, `IngestionRun`, `ReviewDecision`) tratam esse campo como nullable com o
seguinte significado:

- `organization_id IS NULL` → registro **global/público**, visível em leitura a qualquer usuário
  autenticado do sistema, independentemente da organização a que pertence.
- `organization_id` não-nulo → registro **privado** dessa organização; usuários de outra
  organização recebem `404 Not Found` ao tentar acessá-lo (nunca `403 Forbidden`, para não
  confirmar a existência de um registro de outra organização a quem não deveria vê-lo).

Tabelas puramente de catálogo/referência (`ScientificSource`, `BibliographicReference`,
`PropertyDefinition`, `Supplier`, `SupplierProduct`, `CrystalStructureReference`,
`ScientificIdentifier`) são deliberadamente **não** organization-scoped nesta rodada — são
tratadas como dado de referência compartilhado, análogo a um catálogo/vocabulário comum.

Esta rodada expõe apenas a criação de entidades **privadas** via API (o `organization_id` da
entidade criada é sempre o do usuário autenticado). A criação de um registro **global** via API
não é exposta nesta rodada — só é possível hoje via inserção direta (como no seed sintético).

## Autorização

Leitura (`GET`) exige apenas um usuário autenticado (`get_current_user`, mecanismo já existente
desde o Incremento 1.1, reaproveitado sem nenhuma alteração). Escrita (criação de entidade) e
revisão (`POST .../review-decisions`) exigem `require_admin` — o mesmo controle mínimo de papel
administrativo (`role in {"admin", "superadmin"}`) já usado para a suíte clínica no Incremento
1.1, com o mesmo comportamento de auditar tentativas negadas via `AuditEvent`.

Esta continua sendo uma checagem **mínima** — não é o RBAC/ABAC completo com os 17 perfis
institucionais do Prompt Mestre §9 (PM-ONLY-04, backlog). Ela é suficiente para não deixar a
curadoria científica sem nenhuma verificação de autorização, exatamente como já documentado para
a suíte clínica.

## Dados não revisados continuam visíveis, mas rotulados

Um registro em estado `draft` (ou `rejected`) **não é ocultado** da leitura — ele aparece
normalmente nas listagens e detalhes, sempre acompanhado do campo `review_status` no corpo da
resposta, para que o consumidor da API nunca precise inferir implicitamente se um dado já foi
revisado. Esconder dado não revisado impediria a própria curadoria (um curador precisa poder
listar o que ainda não foi revisado).

## Fluxo de revisão

1. Uma entidade é criada em estado `draft` por um administrador/curador da própria organização
   (ou inserida diretamente como registro global, fora da API, nesta rodada).
2. Um curador avalia a entidade e registra uma `ReviewDecision`
   (`POST /api/v1/scientific-entities/{id}/review-decisions`) com uma das três decisões:
   `approved`, `rejected`, ou `changes_requested`.
3. A decisão gera uma nova linha **append-only** em `ReviewDecision` (nunca uma edição ou remoção
   de uma decisão anterior — toda a trilha permanece consultável via
   `GET .../review-history`), e também atualiza o campo `review_status` da própria
   `ScientificEntity` (`approved` → `reviewed`; `rejected` → `rejected`;
   `changes_requested` → estado inalterado). Isso **não é** uma sobrescrita de valor científico
   — é apenas a atualização do campo de status da própria entidade, o mesmo tipo de operação já
   permitida em outros fluxos de curadoria do repositório.
4. Nenhuma `PropertyObservation` é jamais reescrita por uma `ReviewDecision`. Uma observação
   considerada incorreta permanece como está (rotulada com seu `review_status` próprio) — a
   correção é sempre uma **nova** observação (de uma fonte/condição diferente, ou mesmo da mesma
   fonte revisitada), nunca a edição da linha existente.

## Proveniência obrigatória por observação

Toda `PropertyObservation` carrega, quando disponível: `source_id` (a `ScientificSource`),
`reference_id` (a `BibliographicReference`), `source_location` (página/tabela/figura),
`unit_original`, `method`, condições experimentais, `evidence_type`, e `uncertainty_low`/
`uncertainty_high`. Quando um desses dados não está disponível na fonte original, o campo fica
`NULL` — nunca é inventado ou inferido silenciosamente.

## Deduplicação nunca é sobrescrita

Ver `SCIENTIFIC_DATA_MODEL.md`, seção "Deduplicação por fingerprint". A deduplicação é uma
proteção contra **duplicatas verdadeiras** (a mesma observação inserida duas vezes), nunca um
mecanismo de "manter só o valor mais recente" ou "mais confiável" — todas as observações
genuinamente divergentes coexistem indefinidamente, e cabe ao consumidor (ou a uma futura camada
de agregação/curadoria, não implementada nesta rodada) decidir como reconciliá-las.

## Nunca validação clínica

`BiologicalEvidence.research_classification_only` é sempre `True` nesta rodada — não existe
nenhum caminho de API ou de seed que o defina como `False`. Nenhuma tabela deste modelo, isolada
ou combinada, constitui prova de segurança/eficácia clínica. Isso é reforçado tanto no código
(docstrings) quanto nesta documentação e no disclaimer central do `README.md`.
