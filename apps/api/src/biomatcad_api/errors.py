"""Tratamento padronizado de erros da API."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("biomatcad_api.errors")


def _error_payload(*, error_id: str, code: str, message: str, details: object | None = None) -> dict:
    return {
        "error": {
            "id": error_id,
            "code": code,
            "message": message,
            "details": details,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        error_id = str(uuid.uuid4())
        logger.warning("http_error id=%s status=%s path=%s", error_id, exc.status_code, request.url.path)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(error_id=error_id, code=f"HTTP_{exc.status_code}", message=str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        error_id = str(uuid.uuid4())
        logger.warning("validation_error id=%s path=%s", error_id, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                error_id=error_id,
                code="VALIDATION_ERROR",
                message="Erro de validação nos dados enviados.",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        error_id = str(uuid.uuid4())
        logger.error("unhandled_error id=%s path=%s type=%s", error_id, request.url.path, type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                error_id=error_id,
                code="INTERNAL_ERROR",
                message="Erro interno. Consulte os logs do servidor pelo identificador informado.",
            ),
        )
