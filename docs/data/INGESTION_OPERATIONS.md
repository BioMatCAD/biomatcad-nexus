# Operação de Ingestão Científica — Guia da Interface Web

(Incremento 2.3, Rodada 2 — Adendo de Interface Científica Mínima, Fase T)

Este documento explica como usar a interface web mínima entregue nesta rodada para visualizar
dados científicos e operar o piloto de ingestão PubChem, sem precisar da API/CLI diretamente.
Para o contrato completo do conector PubChem (arquitetura, cliente HTTP, reconciliação,
mutation testing), ver `docs/data/connectors/PUBCHEM_CONNECTOR.md`. Para o modelo de dados
subjacente, ver `docs/data/SCIENTIFIC_DATA_MODEL.md`.

## Rotas

| Rota | O que mostra | Quem vê |
|---|---|---|
| `/app/scientific-data` | Listagem de entidades científicas com busca/filtros; painel de ingestão PubChem | Qualquer usuário autenticado; painel só para admin/superadmin |
| `/app/scientific-data/:entityId` | Detalhe de uma entidade (11 abas) | Qualquer usuário autenticado com acesso à entidade (global ou da própria organização) |

Nota de nomenclatura: as rotas reais usam o prefixo `/app/` (mesma convenção de
`/app/materials`, `/app/projects`, `/app/observability`) em vez do caminho literal
`/scientific-data` mencionado nas instruções originais — decisão consciente para preservar a
arquitetura de rotas já estabelecida do produto, não um desvio silencioso.

## Como iniciar (desenvolvimento local)

```bash
# Backend
cd apps/api
alembic upgrade head
python -m biomatcad_api.seed                    # cria demo@biomatcad.example (researcher) e admin@biomatcad.example (admin)
python -m biomatcad_api.seed_scientific_data    # popula entidades/observações/proveniência/conflito sintéticos
uvicorn biomatcad_api.main:app --reload

# Frontend (outro terminal)
cd apps/web
npm run dev
```

Acesse `http://localhost:5173/login` e entre com um dos logins sintéticos abaixo.

## Logins sintéticos

| Papel | E-mail | Senha | O que consegue fazer |
|---|---|---|---|
| Pesquisador | `demo@biomatcad.example` | `demo-synthetic-password-123` | Visualizar entidades/propriedades/proveniência/conflitos. Não vê o painel de ingestão; uma chamada direta à API de submissão retorna 403. |
| Administrador | `admin@biomatcad.example` | `admin-synthetic-password-456` | Tudo o que o pesquisador vê, mais o painel de ingestão PubChem (dry-run/submissão/status/cancelamento). |

Estes são os mesmos logins usados pelo E2E (`apps/web/e2e/scientific-data.spec.ts`) e pelo
roteiro Windows dedicado (`scripts/Run-ScientificDataE2EOnly.ps1`).

## Visualizando dados científicos (qualquer usuário)

Na listagem (`/app/scientific-data`), cada linha mostra: nome preferido (link para o detalhe),
tipo de entidade, CID PubChem (quando presente — "—" quando ausente, nunca vazio/zero
fabricado), InChIKey (idem), massa molecular com unidade (idem), visibilidade
(global/organização), e o badge de estado de revisão ("não revisado (draft)" / "revisado" /
"rejeitado"). Use o campo de busca por nome e os filtros de tipo/estado de revisão para reduzir
a lista.

No detalhe de uma entidade, as abas relevantes para investigar um dado são:

- **Propriedades**: cada observação mostra nome, valor/unidade original, valor normalizado,
  condições (temperatura/pressão/pH/meio), método, incerteza, tipo de evidência (rótulo
  literal — "calculado" nunca aparece como "validado") e estado de revisão. Observações
  conflitantes de fontes diferentes sobre a mesma propriedade aparecem como linhas separadas,
  nunca uma sobrescrevendo a outra silenciosamente.
- **Proveniência**: liga cada observação à sua fonte e, quando houver, à referência
  bibliográfica.
- **Snapshots**: mostra o(s) `RawSourceRecord` associado(s) — conector, identificador externo,
  data de obtenção, SHA-256 truncado, e o `predecessor_record_id` quando o snapshot é uma nova
  versão de um payload anterior.
- **Conflitos**: qualquer `IngestionConflict` envolvendo a entidade (como lado "principal" ou
  como "outra entidade" do conflito), com o tipo de conflito e se já foi resolvido.

Três avisos aparecem sempre que aplicável, nunca condicionados a nenhum caminho de sucesso:
aviso geral de uso para pesquisa (sempre visível), aviso de fonte externa importada (quando a
entidade tem algum `RawSourceRecord` de um conector real, ex. `pubchem_pug_rest`), e aviso de
dado sintético de demonstração (quando o `RawSourceRecord` é do conector
`synthetic_demo_connector` — nunca atribuído ao PubChem).

## Operando o piloto de ingestão PubChem (somente admin/superadmin)

No topo da listagem (`/app/scientific-data`), o painel "Ingestão PubChem (piloto
administrativo)" pede:

1. **Fonte**: um `ScientificSource` já cadastrado (populado automaticamente pelo seed).
2. **CIDs**: lista separada por vírgula ou espaço, **somente números**, **máximo 10 por
   solicitação**. Qualquer entrada não numérica ou acima do limite é rejeitada localmente antes
   de qualquer chamada à API, com mensagem explícita.

Botões:

- **Dry-run**: roda o pipeline completo (busca real ao PubChem incluída, quando a rede não está
  bloqueada) mas **nunca persiste** nenhuma entidade/observação/identificador — apenas mostra a
  prévia dos contadores (recebidos/criados/atualizados/inalterados/rejeitados/conflitos).
- **Submeter ingestão**: cria uma solicitação real, que entra na fila (`queued`) para o
  dispatcher (`scripts/scientific_ingestion_dispatcher.py`, processo separado, precisa estar
  rodando para a solicitação avançar) processar.
- **Cancelar**: aparece apenas enquanto a solicitação está `queued`/`running`; cancelamento é
  cooperativo — se o dispatcher já tiver começado a processar, a solicitação ainda pode
  terminar antes do cancelamento ser observado (mesma semântica cooperativa da fila geométrica
  do Incremento 2.1).

Após submeter, a UI mostra: status legível (na fila/em execução/concluído/concluído
parcialmente/falhou/cancelado), Correlation ID (o próprio ID da solicitação, para cruzar com
logs do dispatcher), contadores quando disponíveis, e qualquer conflito detectado. O status é
atualizado por polling controlado a cada 2 segundos, que para automaticamente ao atingir um
estado terminal ou ao sair da página (nunca deixa um intervalo órfão rodando).

**Nunca há busca por nome nem importação em massa** — cada solicitação exige a lista explícita
de CIDs digitada pelo administrador.

## Diferença entre fixture sintética e ingestão PubChem real

| | Fixture sintética (`synthetic_demo_connector`) | Ingestão PubChem real (`pubchem_pug_rest`) |
|---|---|---|
| Origem | `python -m biomatcad_api.seed_scientific_data`, inserção direta via SQLAlchemy | `POST /api/v1/scientific-ingestion/requests`, processado pelo dispatcher, que chama a API oficial do PubChem via `AllowlistedHttpsClient` |
| Rede | Nenhuma chamada de rede | Chamada HTTPS real a `pubchem.ncbi.nlm.nih.gov` |
| Rótulo na UI | "Dado sintético de demonstração — não atribuído ao PubChem." | "Fonte externa importada. Exige curadoria antes de qualquer uso científico conclusivo." |
| Uso no E2E | `apps/web/e2e/scientific-data.spec.ts` (nunca toca rede real) | `apps/api/scripts/Run-PubChemPilotWindows.ps1` (piloto real, requer rede) |

## Piloto real do PubChem contra a rede oficial: ainda pendente

A execução real do conector PubChem contra `pubchem.ncbi.nlm.nih.gov` (fora da UI, via
`scripts/Run-PubChemPilotWindows.ps1`) **permanece pendente** de execução em uma máquina Windows
real — o sandbox de desenvolvimento bloqueia essa rede na camada TLS. A interface web descrita
aqui está pronta para operar essa ingestão assim que o piloto de rede for validado; até lá, todo
uso desta interface no sandbox usa exclusivamente o seed sintético. Ver
`docs/data/connectors/PUBCHEM_CONNECTOR.md` para os detalhes do bloqueio e o procedimento
completo do piloto.

## Lacunas conhecidas desta rodada

- Sem paginação de servidor na listagem (aceitável para o tamanho atual do seed sintético).
- A coluna "Fórmula molecular" não aparece na listagem: o conector calcula fórmula/SMILES/InChI
  em `normalize()`, mas o `persist()` (Rodada 2, já concluída) só grava o InChIKey como
  identificador — expandir isso é backlog explícito para uma rodada futura, fora do escopo
  desta interface mínima.
