"""Punto de entrada de la API del facturador."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import (
    DomainError,
    domain_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging, get_logger, request_id_var

logger = get_logger(__name__)

DESCRIPTION = """
Facturador electrónico SUNAT (Perú) como microservicio.

Emite comprobantes de pago electrónicos en formato UBL 2.1, los firma con el
certificado digital de la empresa y los envía a SUNAT.

**Autenticación**: cabecera `X-API-Key` en todos los endpoints salvo `/health`.

**Idempotencia**: envía `X-Idempotency-Key` en las emisiones para que un reintento
del cliente no genere un comprobante duplicado.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(debug=settings.DEBUG)

    # Los directorios de datos se crean al arrancar: en un contenedor nuevo con
    # volumen vacío, el primer guardado fallaría si no existen.
    for directory in (settings.STORAGE_ROOT, settings.CERTIFICATE_ROOT):
        Path(directory).mkdir(parents=True, exist_ok=True)

    logger.info(
        "facturador iniciado",
        extra={"environment": settings.SUNAT_ENVIRONMENT.value, "debug": settings.DEBUG},
    )
    yield
    logger.info("facturador detenido")


app = FastAPI(
    title="sunat-biller",
    description=DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Asigna un `request_id` y lo propaga a todas las líneas de log del request."""
    incoming = request.headers.get("X-Request-ID")
    correlation_id = incoming or str(uuid.uuid4())
    token = request_id_var.set(correlation_id)

    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)

    response.headers["X-Request-ID"] = correlation_id
    logger.info(
        "request atendido",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "request_id": correlation_id,
        },
    )
    return response


app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.get(
    "/health",
    tags=["salud"],
    summary="Estado del servicio",
    status_code=status.HTTP_200_OK,
)
async def health() -> dict[str, Any]:
    """Liveness. Sin autenticación: lo consulta el orquestador de contenedores."""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "sunat_environment": settings.SUNAT_ENVIRONMENT.value,
    }


def dev() -> None:
    """Servidor de desarrollo con recarga automática."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.API_PORT, reload=True)


def prod() -> None:
    """Servidor de producción. HTTPS lo termina el reverse proxy (RNF-01.5)."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.API_PORT, reload=False)
