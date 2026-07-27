"""GET /health, /ready, /version — Prompt Mestre Incremento 1."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from biomatcad_api import __version__
from biomatcad_api.config import Settings, get_settings
from biomatcad_api.db import get_db
from biomatcad_api.schemas.system import HealthResponse, ReadyResponse, VersionResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness: o processo está de pé. Não verifica dependências externas."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
def ready(db: Session = Depends(get_db)) -> ReadyResponse:
    """Readiness: verifica conexão real com o banco de dados."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:  # noqa: BLE001 — readiness probe deliberadamente tolerante a qualquer falha de DB
        db_status = "unavailable"
    return ReadyResponse(status="ok" if db_status == "connected" else "degraded", database=db_status)


@router.get("/version", response_model=VersionResponse)
def version(settings: Settings = Depends(get_settings)) -> VersionResponse:
    return VersionResponse(version=__version__, environment=settings.environment.value)
