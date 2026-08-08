"""BioMatCAD Nexus API — app factory (Incremento 2.1: vertical geométrica, worker bloqueado com evidência)."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from biomatcad_api import __version__
from biomatcad_api.config import get_settings
from biomatcad_api.errors import register_exception_handlers
from biomatcad_api.logging_config import configure_logging
from biomatcad_api.routers import (
    artifacts,
    auth,
    health,
    jobs,
    materials,
    observability,
    operational_state,
    projects,
    recipes,
    scientific_data,
    scientific_ingestion,
    system,
)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_secure_for_environment()
    configure_logging(settings.environment.value)
    logger = logging.getLogger("biomatcad_api")

    app = FastAPI(
        title="BioMatCAD Nexus API",
        version=__version__,
        description=(
            "Incremento 2.1 da Fase 2: primeira vertical funcional do núcleo BioMatCAD "
            "(materiais, projetos, receitas BioMatCEM, jobs geométricos, artefatos). O worker "
            "C#/PicoGK está implementado e compilado, mas sua execução real está BLOQUEADA "
            "neste ambiente (ausência de runtime nativo linux-x64) -- ver "
            "apps/geometry-worker/WORKER_STATUS.md e ADR-0007. FEM/DICOM/LIMS/prontuário/"
            "funcionalidades clínicas permanecem fora de escopo deste incremento -- ver "
            "IMPLEMENTATION_STATUS.md."
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
    app.include_router(materials.router)
    app.include_router(projects.router)
    app.include_router(recipes.router)
    app.include_router(jobs.router)
    app.include_router(artifacts.router)
    app.include_router(observability.router)
    app.include_router(scientific_data.router)
    app.include_router(scientific_ingestion.router)

    logger.info("biomatcad_api_started environment=%s", settings.environment.value)
    return app


app = create_app()
