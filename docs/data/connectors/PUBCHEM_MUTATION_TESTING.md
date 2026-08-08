# Testes de mutação manual — Conector PubChem (Incremento 2.3, Rodada 2, Fase J)

Este documento registra literalmente o exercício de mutation testing manual exigido pela
Regra 9 das instruções da Rodada 2. Cada mutação foi aplicada por script Python
(substituição de string, nunca `sed`, devido a caracteres `://` no código), confirmada
visualmente no arquivo, executada contra o(s) teste(s)-alvo esperando **falha**, e então
revertida via `git checkout --` com confirmação de árvore limpa (`grep MUTANTE_N` retornando
vazio e `git status --porcelain` vazio). Nenhuma mutação permanece aplicada no código.

Nenhum timeout foi aumentado para mascarar falha em nenhum momento deste exercício.

## Resumo

| # | Alvo | Comportamento mutado | Teste(s) que deveriam falhar | Resultado |
|---|------|----------------------|-------------------------------|-----------|
| 1 | `services/connectors/http_client.py` (`AllowlistedHttpsClient`) | Permitir path com URL absoluta/protocol-relative embutida, contornando o allowlist de host | `test_pubchem_http_client.py::test_rejects_path_with_embedded_absolute_url`, `::test_rejects_path_starting_with_protocol_relative_url` | **Matou como esperado** |
| 2 | `routers/scientific_ingestion.py` (dependência de autorização) | Remover exigência de `require_admin` no endpoint de submissão | `test_scientific_ingestion_api.py::test_submit_request_requires_admin` | **Matou como esperado** |
| 3 | `services/scientific_ingestion_service.py` (`process_request`, ramo dry-run) | Persistir efeitos mesmo com `dry_run=True` | `test_scientific_ingestion_service.py::test_process_request_dry_run_never_persists_anything` | **Matou como esperado** |
| 4 | `services/scientific_ingestion_service.py` (`claim_next_queued_request`) | Quebrar atomicidade do `SELECT FOR UPDATE SKIP LOCKED`, permitindo dupla reivindicação | `test_scientific_ingestion_concurrency.py` (única prova de concorrência real, 2 threads/`SessionLocal()` independentes, 24 requisições) | **Matou como esperado** — 48 reivindicações registradas em vez de 24 (dupla reivindicação exata) |
| 5 | `services/scientific_ingestion_service.py` (`_persist_raw_source_record`) | Sempre criar novo `RawSourceRecord`, ignorando checksum SHA-256 igual (quebra idempotência por payload) | `test_scientific_ingestion_service.py::test_persist_raw_source_record_same_payload_reuses_existing_row` | **Matou como esperado** |
| 5b | (mesma mutação acima) | — | `test_scientific_ingestion_service.py::test_process_request_idempotent_second_run_is_unchanged` (teste pré-existente, nível de resumo) | **NÃO matou** — ver nuance abaixo |
| 6 | `services/connectors/base.py` (`reconcile`, ramo de colisão de InChIKey) | Nunca registrar `IngestionConflict` ao detectar InChIKey já usado por outra entidade | `test_pubchem_connector.py::test_reconcile_flags_inchikey_collision_with_other_entity_never_auto_merges`, `test_scientific_ingestion_service.py::test_process_request_records_conflict_never_auto_merges` | **Matou como esperado** |
| 7 | `services/connectors/base.py` (`reconcile`, criação de entidade nova) | Criar entidade nova já como `CurationState.REVIEWED` em vez de `DRAFT` | `test_pubchem_connector.py::test_reconcile_creates_new_entity_as_draft_unreviewed`, `test_scientific_ingestion_service.py::test_process_request_never_promotes_to_reviewed` | **Matou como esperado** |

**7 de 7 mutações planejadas mataram pelo menos um teste dedicado.** Todas as 7 foram
revertidas e a árvore de trabalho confirmada limpa após cada uma.

## Nuance importante: mutação 5

A mutação 5 (quebra de idempotência por checksum em `_persist_raw_source_record`) **não foi
detectada** pelo teste pré-existente `test_process_request_idempotent_second_run_is_unchanged`,
que verifica apenas contadores agregados no resumo (`summary["created_count"]` etc.) após duas
execuções do mesmo `process_request`. Como o cenário de teste usa CIDs cujo conteúdo não muda
entre as duas chamadas, e o `dedup_fingerprint` a nível de `PropertyObservation`/identificador
já absorve boa parte da idempotência de alto nível, o contador agregado permaneceu estável
mesmo com a mutação aplicada — mascarando a regressão real (criação de um novo
`RawSourceRecord` duplicado a cada chamada, com `predecessor_record_id` nunca populado).

Isso expôs uma lacuna de cobertura: idempotência a nível de **resumo/contadores** não é
suficiente para provar idempotência a nível de **registro bruto versionado**
(`RawSourceRecord`). Por isso foram adicionados os dois testes dedicados:

- `test_persist_raw_source_record_same_payload_reuses_existing_row` — mesmo payload
  (mesmo SHA-256 canônico) não cria nova linha.
- `test_persist_raw_source_record_changed_payload_creates_new_version_with_predecessor` —
  payload diferente cria nova linha com `predecessor_record_id` apontando para a anterior.

Ambos foram confirmados como matando a mutação 5 antes da reversão.

## Metodologia (reprodutível)

Para cada mutação, nesta ordem exata:

1. Aplicar via script Python de substituição de string (`old`/`new` únicos no arquivo,
   `assert content.count(old) == 1` antes de substituir), inserindo um comentário
   `# MUTANTE_N_<DESCRICAO>` no ponto exato da mudança.
2. Confirmar visualmente a mutação no arquivo (`grep -n "MUTANTE_N"` / leitura do trecho).
3. Rodar o(s) teste(s)-alvo específico(s) via `pytest`, esperando falha — nunca a suíte
   inteira, para manter o sinal claro de causa-efeito.
4. Reverter com `git checkout -- <arquivo>`.
5. Confirmar reversão limpa: `grep -n "MUTANTE_N" <arquivo>` retorna vazio (exit code 1) e
   `git status --porcelain` não lista o arquivo.

Nenhum timeout de teste foi alterado durante o exercício. Nenhuma mutação foi deixada
aplicada no repositório após seu teste.
