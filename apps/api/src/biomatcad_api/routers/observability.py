"""GET /api/v1/observability/status -- painel de observabilidade real (Incremento 2.2, Seção
7). Requer autenticação: jobs ativos/falhos são escopados pela organização do usuário
(Incremento 2.1.1, Seção 5 -- isolamento entre organizações), nunca vazam dados de outra
organização. Os componentes de infraestrutura (API/banco/dispatcher/worker/fila/storage) são
verificações do ambiente compartilhado, não dados de organização."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from biomatcad_api.config import Settings, get_settings
from biomatcad_api.db import get_db
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user
from biomatcad_api.schemas.observability import ObservabilityStatusResponse
from biomatcad_api.services.observability_service import build_observability_status

router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

# apps/api/src/biomatcad_api/routers/observability.py -> repo root (5 níveis acima, mesmo
# padrão usado em scripts/geometry_dispatcher.py::REPO_ROOT, ajustado pela profundidade extra
# de src/biomatcad_api/routers/).
_REPO_ROOT = Path(__file__).resolve().parents[5]


@router.get("/status", response_model=ObservabilityStatusResponse)
def observability_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> ObservabilityStatusResponse:
    return build_observability_status(
        db=db,
        settings=settings,
        repo_root=_REPO_ROOT,
        organization_id=current_user.organization_id,
    )
