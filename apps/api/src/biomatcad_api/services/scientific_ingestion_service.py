"""Orquestração da fila de ingestão científica (Incremento 2.3, Rodada 2 -- Fase D).

Mesmo PADRÃO de concorrência de `geometry_job_service.py` (claim atômico via
`SELECT ... FOR UPDATE SKIP LOCKED`, heartbeat, recuperação de órfão) implementado de forma
independente aqui -- os dois domínios têm estados/transições/efeitos colaterais distintos o
suficiente (um dispara um subprocess C#/PicoGK; o outro faz requisições HTTP rate-limitadas e
grava observações científicas) para não valer a pena uma abstração genérica prematura entre
eles, mas o padrão de concorrência é deliberadamente idêntico -- ver docstring de
`models/scientific_ingestion.py::ScientificIngestionRequest`.

`process_request` é o coração da Fase D: para cada identificador externo (CID) da solicitação,
busca (`connector.fetch`), normaliza (`connector.normalize`), e -- a menos que seja um
`dry_run` -- grava o snapshot bruto imutável (`RawSourceRecord`, com deduplicação por checksum:
mesmo payload não gera nova versão) e reconcilia/persiste (`connector.reconcile`/`persist`,
Fase B/G: nunca funde por nome, nunca sobrescreve observação revisada, nunca promove
automaticamente para revisado). Cancelamento cooperativo: o loop verifica
`cancel_requested_at` entre CADA CID, nunca no meio de uma chamada de rede já em andamento."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.scientific_data import IngestionRun, IngestionStatus, ScientificIdentifier
from biomatcad_api.models.scientific_ingestion import (
    IngestionConflict,
    IngestionRequestStatus,
    ParsingStatus,
    RawSourceRecord,
    ScientificIngestionRequest,
)
from biomatcad_api.services.connectors.base import (
    MAX_PAYLOAD_BYTES,
    FetchResult,
    NormalizedExternalRecord,
    PersistOutcome,
    ScientificDataConnector,
    canonical_json_bytes,
    sha256_of_payload,
)
from biomatcad_api.services.connectors.registry import (
    UnknownConnectorError,
    get_connector,
    get_connector_info,
)

# Ingestão envolve rede rate-limitada (até 4 req/s no máximo absoluto, ver
# config.py::validate_pubchem_rate_limit) -- um lote de 10 CIDs pode legitimamente levar dezenas
# de segundos. O timeout de órfão precisa ser bem maior que o do dispatcher geométrico
# (ORPHAN_HEARTBEAT_TIMEOUT_SECONDS = 120 em geometry_job_service.py) para não recuperar
# prematuramente uma solicitação que só está sendo lenta de propósito (respeitando rate limit).
ORPHAN_HEARTBEAT_TIMEOUT_SECONDS = 300
HEARTBEAT_MIN_INTERVAL_SECONDS = 2.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    """Normaliza um datetime possivelmente 'naive' (lido de volta do banco -- alguns drivers/
    backends, notadamente SQLite, não preservam tzinfo mesmo em uma coluna `DateTime(timezone=
    True)`) para UTC-aware, antes de subtrair de `_utcnow()`. Sem isto, comparar um heartbeat
    lido do banco com `_utcnow()` levanta `TypeError: can't subtract offset-naive and
    offset-aware datetimes` -- um bug real encontrado pelos próprios testes desta rodada ao
    rodar contra o SQLite de desenvolvimento local (o alvo oficial de verificação continua
    sendo PostgreSQL real, que preserva tzinfo corretamente, mas a normalização aqui é uma
    defesa barata e correta independentemente do backend)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class IngestionRequestError(RuntimeError):
    """Erro estruturado de validação/transição de uma solicitação de ingestão -- carrega um
    `reason_code` para o router/CLI traduzir em HTTP 400/404/409 ou mensagem de linha de
    comando, sem depender de parsing de texto livre."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


class PayloadTooLargeError(RuntimeError):
    """Levantado quando o payload canônico de um registro bruto excede `MAX_PAYLOAD_BYTES` --
    nunca truncado silenciosamente; o identificador correspondente é rejeitado com este motivo
    estruturado (ver `_persist_raw_source_record`)."""


@dataclass
class DryRunDiff:
    """Um item do resultado de uma solicitação `dry_run` -- nunca grava nada; apenas mostra o
    que SERIA feito (Fase H: "consulta/normaliza/mostra diff/não persiste entidades
    científicas")."""

    external_identifier: str
    would_create_new_entity: bool
    existing_entity_id: str | None
    preferred_name: str | None
    formula: str | None
    inchikey: str | None
    calculated_properties: list[dict]
    missing_fields: list[str]
    mapping_warnings: list[str]


def submit_ingestion_request(
    db: Session,
    *,
    organization_id: str | None,
    requested_by_user_id: str,
    connector_id: str,
    source_id: str,
    external_ids: list[str],
    dry_run: bool = False,
) -> ScientificIngestionRequest:
    """Submete uma nova solicitação (Fase H: só admin/curador pode chamar isto -- a checagem de
    papel é feita no router/CLI, nunca aqui, para este módulo permanecer testável sem HTTP).
    Valida o conector e a lista de identificadores ANTES de enfileirar -- uma solicitação
    inválida nunca chega a existir na fila (nunca fica "queued" para falhar depois)."""
    try:
        get_connector_info(connector_id)
    except UnknownConnectorError as exc:
        # get_connector_info() (registry.py, mesmo padrão de topology_providers.py) já trata
        # "id desconhecido" e "id conhecido mas status='planned'" de forma idêntica -- do ponto
        # de vista de quem submete uma solicitação, ambos significam "este conector não pode
        # ser usado agora", então um único reason_code é suficiente (nunca vaza a distinção
        # interna do registro como se fosse uma garantia de API estável).
        raise IngestionRequestError("unknown_connector", str(exc)) from exc

    connector = get_connector(connector_id)
    validation_errors = connector.validate_request(list(external_ids))
    if validation_errors:
        raise IngestionRequestError("invalid_request", "; ".join(validation_errors))

    request = ScientificIngestionRequest(
        organization_id=organization_id,
        requested_by_user_id=requested_by_user_id,
        connector_id=connector_id,
        source_id=source_id,
        external_ids=list(external_ids),
        dry_run=dry_run,
        status=IngestionRequestStatus.QUEUED,
    )
    db.add(request)
    db.flush()
    db.add(
        AuditEvent(
            actor_user_id=requested_by_user_id,
            organization_id=organization_id,
            event_type="scientific_ingestion_request_submitted",
            description=(
                f"Solicitação de ingestão {request.id} submetida: conector={connector_id}, "
                f"{len(external_ids)} identificador(es) explícito(s), dry_run={dry_run}."
            ),
        )
    )
    db.commit()
    db.refresh(request)
    return request


def claim_next_queued_request(db: Session, *, dispatcher_id: str) -> ScientificIngestionRequest | None:
    """Reivindica atomicamente a solicitação mais antiga na fila -- mesmo mecanismo de
    `claim_next_queued_job` (ver geometry_job_service.py): `SELECT ... FOR UPDATE SKIP LOCKED`
    garante que dois dispatchers concorrentes nunca reivindicam a mesma solicitação."""
    request = (
        db.query(ScientificIngestionRequest)
        .filter(ScientificIngestionRequest.status == IngestionRequestStatus.QUEUED)
        .order_by(ScientificIngestionRequest.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if request is None:
        return None
    now = _utcnow()
    request.status = IngestionRequestStatus.RUNNING
    request.started_at = now
    request.claimed_by_dispatcher_id = dispatcher_id
    request.claimed_at = now
    request.heartbeat_at = now
    db.commit()
    db.refresh(request)
    return request


def claim_specific_request(
    db: Session, *, request_id: str, dispatcher_id: str
) -> ScientificIngestionRequest | None:
    """Reivindica atomicamente APENAS a solicitação `request_id` informada -- nunca qualquer
    outra linha da fila, mesmo que exista uma mais antiga pendente. Mesmo mecanismo de
    `claim_next_queued_request` (`SELECT ... FOR UPDATE SKIP LOCKED`), mas filtrado por `id` em
    vez de ordenado globalmente por `created_at`.

    Existe especificamente para consumidores que precisam garantir progresso em UMA solicitação
    própria sem nunca ter efeito colateral sobre o resto da fila -- caso de uso real: o piloto
    Windows do conector PubChem (`scripts/Run-PubChemPilotWindows.ps1` via
    `scripts/pubchem_pilot_wait_for_terminal.py`), que na Run 3 (2026-08-10) processou por
    engano uma solicitação REAL antiga e não relacionada enquanto aguardava seu próprio dry run
    terminar, porque a função de acompanhamento usava `claim_next_queued_request` (FIFO global)
    para "drenar a fila enquanto espera" -- criando `RawSourceRecord`s reais atribuídos
    erroneamente ao dry run (`QUEUE_CONTAMINATION`, ver
    docs/data/connectors/PUBCHEM_CONNECTOR.md). Um dispatcher de produção real continua livre
    para usar `claim_next_queued_request` normalmente em paralelo -- esta função nunca compete
    por outras linhas, então não interfere nele.

    Devolve `None` se a solicitação não existir, não estiver mais `queued` (já reivindicada por
    outro processo, ou já terminal), ou estiver bloqueada por outra transação (nunca espera
    indefinidamente por causa de `skip_locked=True`)."""
    request = (
        db.query(ScientificIngestionRequest)
        .filter(
            ScientificIngestionRequest.id == request_id,
            ScientificIngestionRequest.status == IngestionRequestStatus.QUEUED,
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if request is None:
        return None
    now = _utcnow()
    request.status = IngestionRequestStatus.RUNNING
    request.started_at = now
    request.claimed_by_dispatcher_id = dispatcher_id
    request.claimed_at = now
    request.heartbeat_at = now
    db.commit()
    db.refresh(request)
    return request


def recover_orphaned_requests(
    db: Session, *, heartbeat_timeout_seconds: int = ORPHAN_HEARTBEAT_TIMEOUT_SECONDS
) -> list[str]:
    """Solicitações em `running` cujo heartbeat parou de avançar (dispatcher morreu/travou sem
    finalizar) são recolocadas na fila para uma nova tentativa -- nunca ficam presas em
    `running` para sempre. Mesma lógica de `recover_orphaned_jobs`."""
    threshold = _utcnow() - timedelta(seconds=heartbeat_timeout_seconds)
    stuck = (
        db.query(ScientificIngestionRequest)
        .filter(
            ScientificIngestionRequest.status == IngestionRequestStatus.RUNNING,
            (ScientificIngestionRequest.heartbeat_at.is_(None))
            | (ScientificIngestionRequest.heartbeat_at < threshold),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    recovered_ids = []
    for request in stuck:
        request.status = IngestionRequestStatus.QUEUED
        request.claimed_by_dispatcher_id = None
        request.claimed_at = None
        request.heartbeat_at = None
        request.started_at = None
        request.attempt_number += 1
        db.add(
            AuditEvent(
                organization_id=request.organization_id,
                event_type="scientific_ingestion_request_orphan_recovered",
                description=(
                    f"Solicitação {request.id} recuperada de estado órfão (heartbeat expirado) "
                    "e recolocada na fila."
                ),
            )
        )
        recovered_ids.append(request.id)
    if recovered_ids:
        db.commit()
    return recovered_ids


def request_cancel(
    db: Session, *, request: ScientificIngestionRequest, cancelled_by_user_id: str
) -> ScientificIngestionRequest:
    """Cancelamento cooperativo (Fase D/H): se a solicitação ainda está `queued`, cancela
    imediatamente; se está `running`, apenas sinaliza -- `process_request` observa
    `cancel_requested_at` entre cada CID e interrompe o processamento na próxima oportunidade.
    Idempotente: chamar duas vezes nunca é erro."""
    if request.status == IngestionRequestStatus.CANCELLED:
        return request
    if request.status in (
        IngestionRequestStatus.SUCCEEDED,
        IngestionRequestStatus.PARTIAL,
        IngestionRequestStatus.FAILED,
    ):
        raise IngestionRequestError(
            "invalid_transition",
            f"Solicitação {request.id} não pode ser cancelada no estado {request.status.value}.",
        )
    if request.cancel_requested_at is not None:
        return request

    now = _utcnow()
    request.cancel_requested_at = now
    if request.status == IngestionRequestStatus.QUEUED:
        request.status = IngestionRequestStatus.CANCELLED
        request.finished_at = now
    db.add(
        AuditEvent(
            actor_user_id=cancelled_by_user_id,
            organization_id=request.organization_id,
            event_type="scientific_ingestion_request_cancel_requested",
            description=(
                f"Cancelamento solicitado para {request.id} (estado no momento: "
                f"{request.status.value})."
            ),
        )
    )
    db.commit()
    db.refresh(request)
    return request


def list_conflicts_for_request(db: Session, *, request_id: str) -> list[IngestionConflict]:
    """Fase G/H: "listar conflitos" -- nunca resolvidos automaticamente por este módulo, apenas
    expostos para decisão humana (uma `ReviewDecision` futura, fora do escopo desta rodada)."""
    return (
        db.query(IngestionConflict)
        .filter(IngestionConflict.ingestion_request_id == request_id)
        .order_by(IngestionConflict.created_at.asc())
        .all()
    )


def _persist_raw_source_record(
    db: Session,
    *,
    connector: ScientificDataConnector,
    request: ScientificIngestionRequest,
    fetch_result: FetchResult,
) -> RawSourceRecord:
    """Fase C, aplicada aqui: idempotência por checksum. Mesmo CID + mesmo payload (mesmo
    checksum SHA-256 do JSON canônico) -- nunca duplica, devolve a versão já existente. Mesmo
    CID + payload alterado -- sempre uma NOVA linha, com `predecessor_record_id` apontando para
    a versão anterior (nunca sobrescrita/apagada)."""
    payload = fetch_result.payload_json or {}
    canonical_bytes = canonical_json_bytes(payload)
    if len(canonical_bytes) > MAX_PAYLOAD_BYTES:
        raise PayloadTooLargeError(
            f"Payload de {fetch_result.external_id} tem {len(canonical_bytes)} bytes, acima do "
            f"limite de {MAX_PAYLOAD_BYTES} bytes para este piloto -- nunca truncado silenciosamente."
        )
    checksum = sha256_of_payload(payload)

    latest = (
        db.query(RawSourceRecord)
        .filter(
            RawSourceRecord.source_id == request.source_id,
            RawSourceRecord.connector_id == connector.connector_id,
            RawSourceRecord.external_record_id == fetch_result.external_id,
        )
        .order_by(RawSourceRecord.created_at.desc())
        .first()
    )
    if latest is not None and latest.payload_sha256 == checksum:
        # Idempotente: mesmo payload -- "unchanged", nenhuma nova versão criada.
        return latest

    record = RawSourceRecord(
        source_id=request.source_id,
        connector_id=connector.connector_id,
        connector_version=connector.connector_version,
        external_record_id=fetch_result.external_id,
        requested_endpoint=fetch_result.requested_endpoint,
        http_status=fetch_result.http_status,
        content_type=fetch_result.content_type,
        fetched_at=fetch_result.fetched_at,
        payload_json=payload,
        payload_sha256=checksum,
        payload_size_bytes=len(canonical_bytes),
        schema_mapping_version=connector.schema_mapping_version,
        predecessor_record_id=latest.id if latest is not None else None,
        parsing_status=fetch_result.parsing_status,
        parsing_error=fetch_result.parsing_error,
    )
    db.add(record)
    db.flush()
    return record


def _build_dry_run_diff(
    db: Session, connector: ScientificDataConnector, normalized: NormalizedExternalRecord
) -> DryRunDiff:
    """Fase H: `dry_run` só CONSULTA (esta função nunca chama `db.add`) -- mostra se um CID
    resolveria para uma entidade já existente ou criaria uma nova, e quais propriedades seriam
    gravadas, sem persistir nada."""
    existing_identifier = (
        db.query(ScientificIdentifier)
        .filter(
            ScientificIdentifier.namespace == connector.primary_identifier_namespace,
            ScientificIdentifier.identifier_normalized == normalized.external_identifier.strip().upper(),
        )
        .first()
    )
    return DryRunDiff(
        external_identifier=normalized.external_identifier,
        would_create_new_entity=existing_identifier is None,
        existing_entity_id=existing_identifier.entity_id if existing_identifier is not None else None,
        preferred_name=normalized.preferred_name,
        formula=normalized.formula,
        inchikey=normalized.inchikey,
        calculated_properties=[
            {"key": p.property_key, "value": p.value_numeric, "unit": p.unit}
            for p in normalized.calculated_properties
        ],
        missing_fields=normalized.missing_fields,
        mapping_warnings=normalized.mapping_warnings,
    )


def process_request(db: Session, *, request: ScientificIngestionRequest) -> ScientificIngestionRequest:
    """Executa uma solicitação JÁ REIVINDICADA (running) por `claim_next_queued_request`.
    Processa cada identificador externo em sequência (respeitando o rate limit do conector,
    aplicado dentro de `AllowlistedHttpsClient`); verifica `cancel_requested_at` ANTES de cada
    CID (cancelamento cooperativo, nunca no meio de uma requisição de rede já em andamento)."""
    if request.status != IngestionRequestStatus.RUNNING:
        raise IngestionRequestError(
            "invalid_transition",
            f"Solicitação {request.id} não está running (estado atual: {request.status.value}) -- "
            "process_request espera uma solicitação já reivindicada por claim_next_queued_request.",
        )

    connector = get_connector(request.connector_id)
    persist_outcomes: list[PersistOutcome] = []
    dry_run_diffs: list[DryRunDiff] = []
    # Falhas de busca (rede bloqueada, CID inexistente, JSON inválido etc.) durante um dry_run
    # nunca podem ser silenciosamente descartadas do resumo -- um dry_run que não conseguiu
    # sequer buscar um CID não deve parecer indistinguível de um dry_run bem-sucedido com zero
    # resultados (bug real encontrado ao rodar o dispatcher de ponta a ponta contra a rede
    # bloqueada desta rodada, ver Fase I).
    dry_run_fetch_errors: list[dict] = []
    cancelled = False
    last_heartbeat = {"at": _ensure_aware(request.heartbeat_at) if request.heartbeat_at else _utcnow()}

    def _heartbeat() -> None:
        now = _utcnow()
        if (now - last_heartbeat["at"]).total_seconds() >= HEARTBEAT_MIN_INTERVAL_SECONDS:
            request.heartbeat_at = now
            db.commit()
            last_heartbeat["at"] = now

    for external_id in request.external_ids:
        _heartbeat()
        db.expire(request)
        fresh = db.get(ScientificIngestionRequest, request.id)
        if fresh is not None and fresh.cancel_requested_at is not None:
            cancelled = True
            break

        fetch_result = connector.fetch(external_id)

        if fetch_result.parsing_status == ParsingStatus.FAILED:
            if request.dry_run:
                dry_run_fetch_errors.append(
                    {"external_identifier": external_id, "error": fetch_result.parsing_error}
                )
            else:
                persist_outcomes.append(
                    PersistOutcome(
                        external_id=external_id,
                        entity_id=None,
                        raw_source_record_id=None,
                        created_entity=False,
                        created_observations=0,
                        unchanged=False,
                        conflicts=[],
                        rejected=True,
                        rejection_reason=str(fetch_result.parsing_error),
                    )
                )
            continue

        normalized = connector.normalize(fetch_result)

        if request.dry_run:
            dry_run_diffs.append(_build_dry_run_diff(db, connector, normalized))
            continue

        try:
            raw_source_record = _persist_raw_source_record(
                db, connector=connector, request=request, fetch_result=fetch_result
            )
        except PayloadTooLargeError as exc:
            persist_outcomes.append(
                PersistOutcome(
                    external_id=external_id,
                    entity_id=None,
                    raw_source_record_id=None,
                    created_entity=False,
                    created_observations=0,
                    unchanged=False,
                    conflicts=[],
                    rejected=True,
                    rejection_reason=str(exc),
                )
            )
            continue

        reconcile_outcome = connector.reconcile(db, normalized)
        for conflict in reconcile_outcome.conflicts:
            db.add(
                IngestionConflict(
                    ingestion_request_id=request.id,
                    external_record_id=external_id,
                    conflict_type=conflict.conflict_type,
                    entity_id=conflict.entity_id,
                    other_entity_id=conflict.other_entity_id,
                    details=conflict.details,
                )
            )
        persist_outcome = connector.persist(
            db,
            normalized=normalized,
            fetch_result=fetch_result,
            source_id=request.source_id,
            raw_source_record=raw_source_record,
            reconcile_outcome=reconcile_outcome,
        )
        persist_outcomes.append(persist_outcome)
        db.commit()

    now = _utcnow()
    request.finished_at = now

    if request.dry_run:
        # Nunca "succeeded" sem ressalva se pelo menos uma busca falhou -- reaproveita os
        # mesmos três estados (SUCCEEDED/PARTIAL/FAILED) que a execução real usa, para que um
        # dry_run com falhas de rede não seja indistinguível de um dry_run limpo.
        if cancelled:
            request.status = IngestionRequestStatus.CANCELLED
        elif not dry_run_fetch_errors:
            request.status = IngestionRequestStatus.SUCCEEDED
        elif dry_run_diffs:
            request.status = IngestionRequestStatus.PARTIAL
        else:
            request.status = IngestionRequestStatus.FAILED
        request.summary = {
            "dry_run": True,
            "cancelled": cancelled,
            "results": [
                {
                    "external_identifier": d.external_identifier,
                    "would_create_new_entity": d.would_create_new_entity,
                    "existing_entity_id": d.existing_entity_id,
                    "preferred_name": d.preferred_name,
                    "formula": d.formula,
                    "inchikey": d.inchikey,
                    "calculated_properties": d.calculated_properties,
                    "missing_fields": d.missing_fields,
                    "mapping_warnings": d.mapping_warnings,
                }
                for d in dry_run_diffs
            ],
            "fetch_errors": dry_run_fetch_errors,
        }
        if dry_run_fetch_errors:
            request.error = {
                "rejected_external_ids": [e["external_identifier"] for e in dry_run_fetch_errors],
                "reasons": [e["error"] for e in dry_run_fetch_errors],
            }
        db.add(
            AuditEvent(
                organization_id=request.organization_id,
                event_type="scientific_ingestion_request_finished",
                description=(
                    f"Solicitação {request.id} (dry_run) finalizada com status "
                    f"{request.status.value}. Nenhuma entidade científica foi persistida."
                ),
            )
        )
        db.commit()
        db.refresh(request)
        return request

    summary = connector.summarize(persist_outcomes)
    request.summary = summary
    received = summary["received_count"]
    rejected = summary["rejected_count"]

    if cancelled:
        request.status = IngestionRequestStatus.CANCELLED
        # IngestionStatus (Rodada 1) não tem um valor CANCELLED -- PARTIAL é o que melhor
        # reflete "execução interrompida antes de processar todos os identificadores
        # solicitados" sem inventar um novo valor de enum fora do escopo desta rodada.
        run_status = IngestionStatus.PARTIAL
    elif rejected == 0:
        request.status = IngestionRequestStatus.SUCCEEDED
        run_status = IngestionStatus.SUCCEEDED
    elif rejected < received:
        request.status = IngestionRequestStatus.PARTIAL
        run_status = IngestionStatus.PARTIAL
    else:
        request.status = IngestionRequestStatus.FAILED
        run_status = IngestionStatus.FAILED

    if rejected > 0:
        request.error = {
            "rejected_external_ids": [o.external_id for o in persist_outcomes if o.rejected],
            "reasons": [o.rejection_reason for o in persist_outcomes if o.rejected],
        }

    ingestion_run = IngestionRun(
        organization_id=request.organization_id,
        source_id=request.source_id,
        connector_name=connector.connector_id,
        connector_version=connector.connector_version,
        finished_at=now,
        parameters={"external_ids": request.external_ids, "cancelled": cancelled},
        received_count=summary["received_count"],
        created_count=summary["created_count"],
        updated_count=summary["updated_count"],
        skipped_count=summary["skipped_count"],
        rejected_count=summary["rejected_count"],
        status=run_status,
        errors=[o.rejection_reason for o in persist_outcomes if o.rejected] or None,
    )
    db.add(ingestion_run)
    db.flush()
    request.ingestion_run_id = ingestion_run.id

    db.add(
        AuditEvent(
            organization_id=request.organization_id,
            event_type="scientific_ingestion_request_finished",
            description=(
                f"Solicitação {request.id} finalizada com status {request.status.value} "
                f"(recebidos={received}, rejeitados={rejected}, conflitos={summary['conflicts_count']})."
            ),
        )
    )
    db.commit()
    db.refresh(request)
    return request
