"""Excepciones de dominio y su traducción a respuestas HTTP.

Convención del proyecto (docs/GUIA_PROYECTO.md §10): los servicios lanzan
excepciones de **dominio**, nunca `HTTPException`. El router deja que suban y los
manejadores registrados en `app.main` las traducen al `ErrorResponse` estándar.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorResponse


class DomainError(Exception):
    """Base de todos los errores de negocio del facturador."""

    error_code: str = "DOMAIN_ERROR"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error_code=self.error_code,
            message=self.message[:500],
            details=self.details or None,
        )


class NotFoundError(DomainError):
    error_code = "NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class ForbiddenError(DomainError):
    """El recurso existe pero no pertenece a la empresa autenticada."""

    error_code = "FORBIDDEN"
    status_code = status.HTTP_403_FORBIDDEN


class UnauthorizedError(DomainError):
    error_code = "UNAUTHORIZED"
    status_code = status.HTTP_401_UNAUTHORIZED


class ConflictError(DomainError):
    error_code = "CONFLICT"
    status_code = status.HTTP_409_CONFLICT


class BusinessRuleError(DomainError):
    """Violación de una regla de negocio o de un requisito SUNAT."""

    error_code = "BUSINESS_RULE_VIOLATION"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class InvalidRucError(BusinessRuleError):
    error_code = "INVALID_RUC"


class TotalsMismatchError(BusinessRuleError):
    """Los importes enviados no cuadran con los calculados por el backend."""

    error_code = "TOTALS_MISMATCH"


class CertificateError(DomainError):
    error_code = "CERTIFICATE_ERROR"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class SigningError(DomainError):
    """Fallo al firmar el XML: es un error del servicio, no del cliente."""

    error_code = "SIGNING_ERROR"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class StorageError(DomainError):
    error_code = "STORAGE_ERROR"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class SunatError(DomainError):
    """Fallo al comunicarse con SUNAT (red, timeout, SOAP Fault).

    OJO: un *rechazo* de SUNAT no es esto. Un rechazo es una respuesta válida del
    servicio y se devuelve como 200 con `status = REJECTED` (§13 de la guía).
    Esta excepción es solo para cuando no se pudo obtener respuesta.
    """

    error_code = "SUNAT_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        retryable: bool = True,
        sunat_code: str | None = None,
    ) -> None:
        super().__init__(message, details)
        self.retryable = retryable
        self.sunat_code = sunat_code


# ─────────────────────────────────────────────────────────── manejadores HTTP


def _json(status_code: int, payload: ErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return _json(exc.status_code, exc.to_response())


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Normaliza los 422 de Pydantic al mismo `ErrorResponse` que el resto."""
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()
    first = errors[0] if errors else {}
    location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = first.get("msg", "Datos de entrada inválidos")
    return _json(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorResponse(
            error_code="VALIDATION_ERROR",
            message=f"{location}: {message}"[:500] if location else message[:500],
            details={"errors": jsonable_encoder(errors)},
        ),
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Última red de seguridad: nunca filtrar trazas ni secretos al cliente."""
    return _json(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="Error interno del servidor.",
            details=None,
        ),
    )
