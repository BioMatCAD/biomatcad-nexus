# Conector PubChem (piloto) — Incremento 2.3, Rodada 2

Este documento descreve o primeiro conector real de ingestão científica externa
(`pubchem_pug_rest`, PubChem PUG REST) e a infraestrutura comum de conectores construída
para suportá-lo. É um **piloto controlado**: no máximo 10 CIDs por solicitação (padrão
`DEFAULT_MAX_CIDS_PER_REQUEST`/`config.py::pubchem_max_cids_per_request`), nunca busca livre,
nunca varredura/importação em massa, sempre com lista explícita de identificadores.

## Status: bloqueio de rede do sandbox de desenvolvimento

O sandbox Linux usado para desenvolver esta rodada tem sua saída de rede para
`pubchem.ncbi.nlm.nih.gov` bloqueada por um proxy que devolve, na camada TLS, o erro:

```
error:0A00010B:SSL routines::wrong version number
```

Confirmado repetidamente (`curl -v https://pubchem.ncbi.nlm.nih.gov/...`) e através do próprio
`AllowlistedHttpsClient` de produção — nunca através de um mock. O handshake HTTPS nem chega a
completar (o proxy responde `200 CONNECT` e então devolve bytes que não são um `ServerHello`
TLS válido). **Isto é tratado como um bloqueio de ambiente do sandbox, nunca como uma falha do
PubChem ou do conector** — não há evidência de que o mesmo aconteça fora deste sandbox.

Consequência prática: nenhum dado real do PubChem foi obtido durante o desenvolvimento desta
rodada. Toda a suíte de testes deste conector (`tests/test_pubchem_connector.py`,
`tests/test_pubchem_http_client.py`, `tests/test_scientific_ingestion_*.py`) roda inteiramente
contra um `_FakeClient`/`_FakeHttpxClient` injetado — nunca contra a rede real. Os fixtures de
payload (`_aspirin_payload()` e equivalentes) são explicitamente rotulados no código como
`synthetic_contract_fixture`: imitam o **formato** documentado da resposta PUG REST
(estrutura/chaves do `PropertyTable`), usando valores numéricos/estruturais que são fatos
químicos públicos e verificáveis (peso molecular, SMILES, InChI/InChIKey da aspirina), mas
**nunca foram capturados de uma resposta real do PubChem nesta sessão** e nunca devem ser
tratados como tal.

A única forma de obter uma resposta real e comprová-la é rodar `Run-PubChemPilotWindows.ps1`
(ver seção própria abaixo) em uma máquina Windows com acesso de rede normal — fora deste
sandbox. Até essa execução acontecer e ser registrada com evidência literal (hashes, JSON de
relatório), este piloto permanece **não validado contra a rede oficial**, apenas validado por
teste de contrato sintético.

## Distinção: teste de contrato sintético vs. ingestão oficial real

| | Teste de contrato sintético (o que existe hoje) | Ingestão oficial real (pendente do usuário) |
|---|---|---|
| Onde roda | Sandbox Linux de desenvolvimento | Windows do usuário, via `Run-PubChemPilotWindows.ps1` |
| Rede | Nenhuma — `_FakeClient` injetado no lugar de `AllowlistedHttpsClient` | Rede real, `https://pubchem.ncbi.nlm.nih.gov` |
| Payload | `synthetic_contract_fixture` (formato real, captura NÃO real) | Payload bruto realmente devolvido pelo PubChem, preservado com hash SHA-256 |
| Prova de idempotência | Testes unitários chamando `_persist_raw_source_record` duas vezes em memória | Execução ponta-a-ponta do roteiro Windows enviando a mesma lista de CIDs duas vezes, comparando hashes entre as duas rodadas |
| O que prova | Que a lógica de parsing/reconciliação/persistência está correta para o formato documentado | Que o conector funciona de fato contra o serviço PubChem real, hoje |
| O que NÃO prova | Nada sobre disponibilidade/comportamento atual do serviço PubChem real | — |

## Arquitetura

### Contrato comum de conectores

`services/connectors/base.py::ScientificDataConnector` (classe abstrata) define o fluxo comum
a qualquer conector futuro: `validate_request` → `fetch` → `normalize` → `reconcile` →
`persist`. Regras aplicadas nesta camada, válidas para qualquer conector, não apenas PubChem:

- Todo dado externo entra sempre como `CurationState.DRAFT` (importado, não revisado).
  Nenhum código de ingestão jamais promove uma entidade/observação para `REVIEWED`
  automaticamente — isso exige uma `ReviewDecision` humana explícita.
- Uma observação com `review_status == REVIEWED` nunca é sobrescrita.
- Identidade de entidade é decidida **somente** pelo identificador primário do conector (CID,
  no caso do PubChem) — nunca por casamento de nome livre.
- Colisão de InChIKey com uma entidade diferente já existente nunca é fundida automaticamente:
  é registrada como `IngestionConflict` (`IngestionConflictType.INCHIKEY_SHARED_WITH_OTHER_ENTITY`)
  para decisão humana futura.
- Categorização de entidade nova é sempre conservadora (`ScientificEntityType.CHEMICAL_SUBSTANCE`)
  — nunca infere uma classificação mais específica (ex.: "fármaco") apenas por existir na fonte.

### Registro bruto versionado (`RawSourceRecord`)

Cada resposta obtida de uma fonte externa vira uma linha imutável em `raw_source_records`:
endpoint requisitado (path + query pública, nunca credenciais), status HTTP, timestamp,
payload JSON completo, e `payload_sha256` (SHA-256 do JSON canônico — chaves ordenadas,
separadores compactos, mesma convenção de `recipe_service.canonicalize_recipe`). Uma nova
consulta ao mesmo identificador (`source_id` + `external_record_id`) com o **mesmo** checksum
reaproveita a linha existente; um checksum **diferente** cria uma nova linha com
`predecessor_record_id` apontando para a anterior — nunca sobrescreve, nunca apaga a versão
antiga. Política de retenção declarada explicitamente como `pilot_indefinite` neste piloto
(nunca implícita).

### Cliente HTTP seguro (`AllowlistedHttpsClient`)

`services/connectors/http_client.py`. Uma instância = um único host permitido (para o PubChem,
`PUBCHEM_ALLOWED_HOST = "pubchem.ncbi.nlm.nih.gov"`, definido em `services/connectors/pubchem.py`).
Nunca aceita URL/host embutido no path (`test_rejects_path_with_embedded_absolute_url`,
`test_rejects_path_starting_with_protocol_relative_url`). TLS sempre verificado
(`verify=True`), redirecionamentos nunca seguidos automaticamente, timeout e limite de tamanho
de resposta sempre aplicados, retry/backoff apenas para falhas transitórias (429/500/502/503/
timeout/erro de conexão), taxa máxima de requisições limitada a 4/s por validação de
configuração (`config.py::validate_pubchem_rate_limit`), `Retry-After` respeitado em 429.

### Fila de ingestão + dispatcher

`models/scientific_ingestion.py::ScientificIngestionRequest` é uma fila persistente com o
mesmo padrão de claim atômico já usado por `GeometryJob`
(`SELECT ... FOR UPDATE SKIP LOCKED`, provado livre de dupla reivindicação por
`tests/test_scientific_ingestion_concurrency.py` com duas conexões `SessionLocal()`
independentes competindo por 24 solicitações). O processamento em si
(claim/fetch/normalize/reconcile/persist) roda em um processo separado,
`scripts/scientific_ingestion_dispatcher.py`, nunca dentro de uma requisição HTTP síncrona —
as rotas da API apenas enfileiram, consultam e cancelam.

Cada solicitação carrega uma lista **explícita** de CIDs (`external_ids`, JSON) e uma flag
`dry_run`: em `dry_run=True`, todo o pipeline roda (fetch real incluído) mas
`process_request` nunca persiste efeito algum no banco — apenas produz o mesmo `summary` que
seria produzido numa execução real, para inspeção prévia.

## Superfície de operação

### API administrativa (`/api/v1/scientific-ingestion`, todas as rotas exigem `require_admin`)

- `GET /connectors` — lista conectores registrados e seu status (`implemented`/`planned`).
- `POST /requests` — submete uma solicitação real ou dry-run (a depender de `payload.dry_run`).
- `POST /requests/dry-run` — conveniência, força `dry_run=True` independentemente do corpo.
- `GET /requests` — lista solicitações visíveis ao curador (globais + da própria organização).
- `GET /requests/{id}` — status + `summary` (contadores) + `error` estruturado.
- `GET /requests/{id}/conflicts` — conflitos estruturados daquela solicitação.
- `POST /requests/{id}/cancel` — cancelamento cooperativo, idempotente; rejeita apenas
  transição a partir de um estado terminal já finalizado (409).

Não existe endpoint de busca livre nem de importação em massa nesta rodada — cada submissão
exige uma lista explícita de CIDs, com máximo de 10 por solicitação.

### Interface web administrativa (Adendo de Interface Científica Mínima, Rodada 2)

Além da API e do CLI abaixo, existe um painel real na UI (`/app/scientific-data`, visível
apenas para `role in {admin, superadmin}`) que cobre a mesma superfície de operação
(dry-run/submissão/status/cancelamento) sem exigir linha de comando. Ver
`docs/data/INGESTION_OPERATIONS.md` para o guia de uso completo do painel, e
`apps/web/e2e/scientific-data.spec.ts` para a prova E2E de que ele funciona ponta a ponta contra
a API real.

### CLI (`apps/api/scripts/pubchem_ingest_cli.py`)

Uso via `SessionLocal` direto (nunca via HTTP), pensado para uso interativo/roteiros:

```
python scripts/pubchem_ingest_cli.py --requested-by-email admin@biomatcad.example \
    --source-id <id-da-fonte-pubchem> --cid 2244 --cid 702 --dry-run

python scripts/pubchem_ingest_cli.py --requested-by-email admin@biomatcad.example \
    --source-id <id-da-fonte-pubchem> --cid 2244 --wait --wait-timeout-seconds 120
```

Exige `--requested-by-email` de um usuário com papel admin/superadmin **já existente** no
banco (mesmos papéis de `routers/auth.py::ADMIN_ROLES`) — o script nunca cria um usuário.
Apenas enfileira; o processamento em si é sempre feito pelo dispatcher. `--wait` faz o CLI
aguardar (com timeout configurável) até a solicitação sair de `queued`/`running`.

### Dispatcher (`apps/api/scripts/scientific_ingestion_dispatcher.py`)

Processo independente do dispatcher geométrico (`geometry_dispatcher.py`) — nunca compartilha
estado em memória com ele, e uma falha em um nunca derruba o outro. Roda em `--once` (uma
única passada pela fila, usado pelo roteiro Windows) ou em modo contínuo (backoff geométrico
quando a fila está vazia, shutdown gracioso via `SIGINT`/`SIGTERM` ou arquivo sentinela, logs
estruturados em JSON, arquivo de status).

### Utilitário `ensure_pubchem_source.py`

Get-or-create idempotente do `ScientificSource` real "PubChem" — nunca duplica se já existir
um registro com esse nome exato, nunca reaproveita o registro fictício de demonstração criado
por `seed_scientific_data.py`. Cria com `redistribution_status=RedistributionStatus.UNKNOWN`
deliberadamente: mesmo a política pública do NIH/PubChem sendo geralmente permissiva, este
projeto nunca assume permissão de redistribuição por omissão — requer verificação humana
explícita e documentada antes de mudar para `ALLOWED`.

### Roteiro Windows real (`apps/api/scripts/Run-PubChemPilotWindows.ps1`)

Único meio capaz de provar o conector contra a rede oficial (o sandbox de desenvolvimento não
consegue, ver seção de bloqueio de rede acima). Parâmetros: `-RepoPath` (obrigatório),
`-OutputDir` (obrigatório), `-DatabaseUrl` (padrão
`postgresql+psycopg2://biomatcad:biomatcad@localhost:5432/biomatcad`), `-Cids` (padrão
`2244, 702, 5090` — aspirina/etanol/ibuprofeno; máximo rígido de 3), `-PythonBin` (padrão
`<RepoPath>\apps\api\.venv\Scripts\python.exe`), `-PollIntervalSeconds` (padrão `3.0`) e
`-TimeoutSeconds` (padrão `300.0`) — novos desde a correção da Run 2 (ver abaixo): controlam o
intervalo/prazo com que o roteiro acompanha o `request_id` exato de cada submissão até estado
terminal.

Sequência executada (aborta com relatório de falha em qualquer passo malsucedido):

1. Verifica PostgreSQL acessível na `-DatabaseUrl` (teste de conexão real).
2. `alembic upgrade head` (idempotente).
3. Garante o usuário administrador sintético via `biomatcad_api.seed` — reaproveita as
   credenciais sintéticas **já existentes** do Incremento 1.1 (`admin@biomatcad.example` /
   `admin-synthetic-password-456`, ver `apps/api/src/biomatcad_api/seed.py`); nunca cria uma
   senha nova.
4. Garante um `ScientificSource` real "PubChem" (`ensure_pubchem_source.py`, idempotente).
5. Submete um **dry run** dos CIDs informados (`pubchem_ingest_cli.py --dry-run`).
6. Acompanha o `request_id` EXATO do dry run até estado terminal via
   `pubchem_pilot_wait_and_validate.py --kind dry_run` (drena a fila internamente, reprocessando
   até esse request específico terminar ou até `-TimeoutSeconds` esgotar — nunca aceita
   `queued`/`running` como sucesso, e nunca se contenta com "algum" request ter sido processado;
   ver a correção da Run 2 abaixo). É este passo que de fato bate na rede oficial do PubChem.
7. Exibe o diff do dry run e valida (`pubchem_pilot_validation.py::validate_dry_run_report`) que
   o estado terminal é `succeeded`, `started_at`/`finished_at` estão preenchidos, e **zero**
   `RawSourceRecord` foi persistido para qualquer CID esperado (nenhuma entidade científica pode
   ter sido persistida neste passo).
8. Submete a MESMA lista de CIDs como solicitação real (`dry_run=false`).
9. Acompanha esse `request_id` até estado terminal (`--kind real`) e valida
   (`validate_real_report`) que o estado é `succeeded`, sem erro, e que existe exatamente 1
   `RawSourceRecord` por CID esperado com pelo menos 1 versão e SHA-256 não vazio — desta vez
   persiste de fato (`RawSourceRecord` + `ScientificEntity`/`PropertyObservation` em rascunho,
   nunca revisado).
10. Submete a MESMA lista de CIDs uma segunda vez (prova de idempotência).
11. Acompanha esse segundo `request_id` até estado terminal e valida da mesma forma.
12. Compara os relatórios das rodadas 9 e 11 via
    `pubchem_pilot_check_idempotency.py::validate_idempotency`: o SHA-256 do payload de cada CID
    esperado deve ser idêntico, nenhuma nova versão de `RawSourceRecord` deve ter sido criada, e
    a lista de CIDs comparados nunca pode ser vazia — prova real de idempotência, não apenas
    assumida.

Ao final, uma **agregação fail-closed** relê todos os passos registrados no relatório: só
declara `final_status=SUCCEEDED`/`exit 0` se literalmente todos tiverem `ok=true` — qualquer
passo com `ok=false` reprova o piloto (`FAILED_VALIDATION`), mesmo que nenhum `exit` anterior
tenha disparado (correção adicionada após a Run 2, ver abaixo).

Nunca imprime segredos (senha do usuário sintético, `DATABASE_URL` com credenciais) no console
ou no relatório — apenas o e-mail do usuário administrador e a URL do banco com a senha
mascarada (`Get-MaskedDatabaseUrl`). Encerra apenas processos que ele mesmo iniciou (o
dispatcher roda sempre em `--once`, processo de vida curta que termina sozinho).

Cada CID só avança para persistência depois que a resposta real da API confirma que o CID
retornado bate com o solicitado (`services/connectors/pubchem.py::fetch`, erro estruturado
`cid_mismatch` caso contrário) — nunca escolhido de memória sem essa confirmação em tempo
real.

**Run 1 (2026-08-09): `FAILED_PREFLIGHT` corrigido.** A primeira execução real no Windows
abortou no Passo 1 com `PilotExitCode=1`, mesmo com o PostgreSQL real acessível (serviços
`Running`, porta 5432 aberta) — o PubChem sequer chegou a ser consultado. Causa confirmada:
normalização de URL frágil (`.replace('postgresql+psycopg2://', 'postgresql://')`), que não
cobria o dialeto `postgresql+psycopg://` (psycopg 3) usado na URL oficial fornecida. Corrigido
com uma função explícita e testada em `scripts/db_url_normalization.py::to_psycopg2_dsn`
(aceita `postgresql://`, `postgresql+psycopg2://` e `postgresql+psycopg://`, preserva o resto
da URL via `urlsplit`/`urlunsplit`) e um script de preflight isolado
(`scripts/pubchem_pilot_preflight_check.py`) que nunca deixa a senha vazar para o log/relatório
mesmo dentro de uma mensagem de exceção. Ver `TEST_EVIDENCE.md` para o detalhamento completo e
`IMPLEMENTATION_STATUS.md` (Fase I) para o registro na matriz de fases.

**Run 2 (2026-08-10): `final_status: SUCCEEDED`/`exit 0` — `INVALID_FALSE_POSITIVE` confirmado,
NUNCA um piloto aprovado, roteiro corrigido.** A segunda execução real produziu relatório JSON
com SHA-256 `83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f` e log de texto com
SHA-256 `85aaf81d87d7fe7b6abf32879234ac06eebd7a50432c3726e4a1e87b43275225`, mas o próprio
relatório se contradizia: `dry_run_result.ok=false` (`status=queued`);
`real_result_1`/`real_result_2` com `status=queued`, sem `started_at`/`finished_at`, todos os
CIDs com `version_count=0`; `idempotency_proof.extra` com os três CIDs `ok=false` ("sem
RawSourceRecord") — e, ainda assim, `final_status=SUCCEEDED`. Causa raiz: (1)
`claim_next_queued_request` é um FIFO global sem escopo por `request_id` (correto para
produção), e o antigo `Invoke-DispatcherOnce` só conferia a contagem processada pelo
dispatcher `--once`, nunca se o request processado era o que o próprio roteiro tinha acabado de
submeter — uma solicitação `queued` mais antiga, deixada por uma execução anterior no banco
persistente do Windows, foi processada no lugar, e a solicitação da Run 2 nunca saiu de
`queued`; (2) a condição antiga `-Ok ($report.status -ne "failed")` aceitava `"queued"` como
sucesso; (3) o laço de idempotência tinha um ramo que fazia `continue` sem nunca propagar
`$idempotencyOk = $false`; (4) o roteiro não tinha nenhuma agregação fail-closed final — só
abortava nas condições explicitamente codificadas, nenhuma das quais disparou aqui. Corrigido
com `scripts/pubchem_pilot_wait_for_terminal.py` (acompanha o `request_id` exato até estado
terminal, com timeout explícito), `scripts/pubchem_pilot_validation.py` (validações fail-closed
puras), os novos CLIs `pubchem_pilot_wait_and_validate.py`/`pubchem_pilot_check_idempotency.py`,
e uma agregação fail-closed final adicionada ao `.ps1`. Ver `TEST_EVIDENCE.md` para o
detalhamento completo (incluindo os 22 testes que reproduzem literalmente a Run 2 e provam a
rejeição) e `IMPLEMENTATION_STATUS.md` (Fase I).

**Comando de exemplo:**

```powershell
.\Run-PubChemPilotWindows.ps1 -RepoPath C:\Users\adler\Documents\GitHub\biomatcad-nexus -OutputDir C:\biomatcad-runs\pubchem-pilot-<data>
```

## Como remover apenas o piloto PubChem

Este piloto foi construído para ser removível sem afetar o restante do Incremento 2.3
(Rodada 1 — fundação de dados científicos) ou qualquer incremento anterior:

1. Reverter a migração desta rodada: `alembic downgrade 4920cd8fd160` (revision anterior,
   `4920cd8fd160`) a partir de `511279411501` — remove `raw_source_records`,
   `scientific_ingestion_requests`, `ingestion_conflicts`, e a coluna nullable
   `property_observations.raw_source_record_id`. Nenhuma tabela da Rodada 1 é tocada.
2. Remover os arquivos de produção específicos deste piloto: `models/scientific_ingestion.py`,
   `schemas/scientific_ingestion.py`, `routers/scientific_ingestion.py`,
   `services/scientific_ingestion_service.py`, `services/connectors/` (inteiro, incluindo
   `base.py`, `pubchem.py`, `http_client.py`, `registry.py`),
   `scripts/scientific_ingestion_dispatcher.py`, `scripts/pubchem_ingest_cli.py`,
   `scripts/ensure_pubchem_source.py`, `scripts/pubchem_pilot_report.py`,
   `scripts/Run-PubChemPilotWindows.ps1`, `scripts/pubchem_pilot_preflight_check.py`,
   `scripts/db_url_normalization.py` (usado apenas pelo preflight deste piloto),
   `scripts/pubchem_pilot_wait_for_terminal.py`, `scripts/pubchem_pilot_validation.py`,
   `scripts/pubchem_pilot_wait_and_validate.py`, `scripts/pubchem_pilot_check_idempotency.py`
   (adicionados na correção do falso positivo da Run 2).
3. Remover o registro do router em `main.py` (`app.include_router(scientific_ingestion.router)`
   e o import correspondente).
4. Remover os arquivos de teste específicos: `tests/test_pubchem_connector.py`,
   `tests/test_pubchem_http_client.py`, `tests/test_pubchem_ingest_cli.py`,
   `tests/test_scientific_ingestion_api.py`, `tests/test_scientific_ingestion_concurrency.py`,
   `tests/test_scientific_ingestion_service.py`,
   `tests/test_pubchem_pilot_db_url_normalization.py`,
   `tests/test_pubchem_pilot_validation.py`, `tests/test_pubchem_pilot_wait_for_terminal.py`.
5. Remover esta pasta de documentação (`docs/data/connectors/`).

Nenhum outro módulo do sistema (materiais/projetos/receitas/jobs geométricos, dados
científicos da Rodada 1, launcher, dispatcher geométrico) depende de nada listado acima.

## Testes

Ver `docs/data/connectors/PUBCHEM_MUTATION_TESTING.md` para o registro literal do exercício
de mutation testing manual (7 mutações, todas mortas por teste dedicado, todas revertidas).
Suíte completa relevante (executada contra PostgreSQL real neste sandbox, nunca SQLite):
`test_pubchem_connector.py`, `test_pubchem_http_client.py`, `test_pubchem_ingest_cli.py`,
`test_scientific_ingestion_api.py`, `test_scientific_ingestion_concurrency.py`,
`test_scientific_ingestion_service.py` — 90 testes somados (21+18+7+14+1+29), todos passando; `ruff`/`mypy`
limpos.
