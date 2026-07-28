"""BioMatCAD Nexus API — app factory (Incremento 1: fundação executável)."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from biomatcad_api import __version__
from biomatcad_api.config import get_settings
from biomatcad_api.errors import register_exception_handlers
from biomatcad_api.logging_config import configure_logging
from biomatcad_api.routers import auth, health, operational_state, system


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_secure_for_environment()
    configure_logging(settings.environment.value)
    logger = logging.getLogger("biomatcad_api")

    app = FastAPI(
        title="BioMatCAD Nexus API",
        version=__version__,
        description=(
            "Incremento 1 da Fase 1: fundação executável (health/status, auth mínima, "
            "estado operacional). Módulos científicos (CAD/FEM/ML) e clínicos/laboratoriais "
            "ainda não implementados — ver IMPLEMENTATION_STATUS.md."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(operational_state.router)

    logger.info("biomatcad_api_started environment=%s", settings.environment.value)
    return app


app = create_app()
