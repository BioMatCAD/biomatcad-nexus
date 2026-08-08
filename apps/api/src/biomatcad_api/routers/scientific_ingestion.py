"""API administrativa da fila de ingestão científica (Incremento 2.3, Rodada 2, Fase H).

Superfície deliberadamente pequena, espelhando a mesma filosofia de scientific_data.py: "não
construir uma interface administrativa extensa". Toda submissão exige uma lista EXPLÍCITA de
identificadores externos (nunca busca livre/fuzzy, nunca varredura/importação em massa -- ver
`services/connectors/base.py::ScientificDataConnector.validate_request` e
config.py::pubchem_max_cids_per_request). Todas as rotas exigem `require_admin` (papel
curador/administrador) -- não existe nenhum caminho de leitura ou escrita aberto a usuários
comuns nesta rodada, diferente de scientific_data.py (que permite leitura ampla): a fila de
ingestão em si, mesmo somente-leitura, é considerada uma ferramenta operacional, não um dado
científico de consulta geral.

Processamento em si (claim/fetch/normalize/reconcile/persist) acontece de forma assíncrona pelo
`scripts/scientific_ingestion_dispatcher.py` (Fase D) -- estas rotas apenas enfileiram,
consultam e cancelam; nenhuma rota aqui dispara uma busca de rede diretamente a partir de uma
requisição HTTP (isso manteria uma requisição HTTP presa esperando uma chamada de rede
rate-limitada, e violaria o princípio de enfileiramento assíncrono do domínio)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from biomatcad_api.db import get_db
from biomatcad_api.models.scientific_ingestion import ScientificIngestionRequest
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import require_admin
from biomatcad_api.schemas.scientific_ingestion import (
    ConnectorInfoResponse,
    IngestionConflictResponse,
    IngestionRequestCreate,
    IngestionRequestResponse,
)
from biomatcad_api.services.connectors.registry import list_connectors
from biomatcad_api.services.scientific_ingestion_service import (
    IngestionRequestError,
    list_conflicts_for_request,
    request_cancel,
    submit_ingestion_request,
)

router = APIRouter(prefix="/api/v1/scientific-ingestion", tags=["scientific-ingestion"])


def _reason_code_to_http_status(reason_code: str) -> int:
    return {
        "unknown_connector": status.HTTP_400_BAD_REQUEST,
        "invalid_request": status.HTTP_400_BAD_REQUEST,
        "invalid_transition": status.HTTP_409_CONFLICT,
    }.get(reason_code, status.HTTP_400_BAD_REQUEST)


def _visibility_filter(current_user: User):
    """Mesma regra de scientific_data.py: uma solicitação é visível se global (sem organização)
    ou da própria organização do curador -- nunca vaza a existência de uma solicitação de outra
    organização (404, nunca 403)."""
    return or_(
        ScientificIngestionRequest.organization_id.is_(None),
        ScientificIngestionRequest.organization_id == current_user.organization_id,
    )


def _get_visible_request(request_id: str, db: Session, current_user: User) -> ScientificIngestionRequest:
    request = (
        db.query(ScientificIngestionRequest)
        .filter(ScientificIngestionRequest.id == request_id, _visibility_filter(current_user))
        .first()
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação de ingestão não encontrada."
        )
    return request


@router.get("/connectors", response_model=list[ConnectorInfoResponse])
def list_ingestion_connectors(current_user: User = Depends(require_admin)) -> list[ConnectorInfoResponse]:
    """Painel de conectores -- visível apenas a admin/curador (Adendo de Interface Científica
    Mínima). Mostra o status real de cada conector (implemented/planned), nunca finge que um
    conector 'planned' pode ser usado."""
    return [
        ConnectorInfoResponse(
            connector_id=info.connector_id, version=info.version, status=info.status, description=info.description
        )
        for info in list_connectors()
    ]


@router.post("/requests", response_model=IngestionRequestResponse, status_code=201)
def submit_request(
    payload: IngestionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ScientificIngestionRequest:
    """Submete uma solicitação real (persiste dados) OU um dry_run (apenas mostra o diff), a
    depender de `payload.dry_run`. Ambos os casos passam pela MESMA validação e MESMA fila --
    a única diferença de comportamento está dentro de `process_request` (Fase D)."""
    try:
        return submit_ingestion_request(
            db,
            organization_id=current_user.organization_id,
            requested_by_user_id=current_user.id,
            connector_id=payload.connector_id,
            source_id=payload.source_id,
            external_ids=payload.external_ids,
            dry_run=payload.dry_run,
        )
    except IngestionRequestError as exc:
        raise HTTPException(status_code=_reason_code_to_http_status(exc.reason_code), detail=str(exc)) from exc


@router.post("/requests/dry-run", response_model=IngestionRequestResponse, status_code=201)
def submit_dry_run_request(
    payload: IngestionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ScientificIngestionRequest:
    """Conveniência: idêntico a `POST /requests` com `dry_run` forçado para `True`,
    independentemente do que o corpo da requisição informe -- nunca ambíguo sobre a intenção de
    quem chama este endpoint especificamente."""
    try:
        return submit_ingestion_request(
            db,
            organization_id=current_user.organization_id,
            requested_by_user_id=current_user.id,
            connector_id=payload.connector_id,
            source_id=payload.source_id,
            external_ids=payload.external_ids,
            dry_run=True,
        )
    except IngestionRequestError as exc:
        raise HTTPException(status_code=_reason_code_to_http_status(exc.reason_code), detail=str(exc)) from exc


@router.get("/requests", response_model=list[IngestionRequestResponse])
def list_requests(
    db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> list[ScientificIngestionRequest]:
    return (
        db.query(ScientificIngestionRequest)
        .filter(_visibility_filter(current_user))
        .order_by(ScientificIngestionRequest.created_at.desc())
        .all()
    )


@router.get("/requests/{request_id}", response_model=IngestionRequestResponse)
def get_request_status(
    request_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> ScientificIngestionRequest:
    """Status + resumo (summary/error) -- `summary` é a fonte de verdade de contadores
    (received/created/updated/skipped/rejected/conflicts) enquanto `status` reflete o estado da
    máquina de estados (queued/running/succeeded/partial/failed/cancelled)."""
    return _get_visible_request(request_id, db, current_user)


@router.get("/requests/{request_id}/conflicts", response_model=list[IngestionConflictResponse])
def get_request_conflicts(
    request_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> list:
    """Conflitos estruturados (ex.: InChIKey compartilhado com outra entidade) -- nunca
    resolvidos automaticamente por esta rota; apenas expostos para decisão humana futura."""
    _get_visible_request(request_id, db, current_user)
    return list_conflicts_for_request(db, request_id=request_id)


@router.post("/requests/{request_id}/cancel", response_model=IngestionRequestResponse)
def cancel_request(
    request_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> ScientificIngestionRequest:
    """Cancelamento cooperativo -- idempotente (chamar de novo em uma já cancelada não é erro);
    rejeita apenas transição a partir de um estado terminal já finalizado (succeeded/partial/
    failed) com 409."""
    request = _get_visible_request(request_id, db, current_user)
    try:
        return request_cancel(db, request=request, cancelled_by_user_id=current_user.id)
    except IngestionRequestError as exc:
        raise HTTPException(status_code=_reason_code_to_http_status(exc.reason_code), detail=str(exc)) from exc
