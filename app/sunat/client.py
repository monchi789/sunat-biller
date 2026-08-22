"""Cliente HTTP del billService de SUNAT.

Traduce respuestas SOAP a resultados de dominio y clasifica cada fallo según si
merece reintento (ver `app.catalogs.cdr_codes`). Un **rechazo** de SUNAT no es
una excepción: es una respuesta válida que se devuelve como `CdrResult`. Solo se
lanza `SunatError` cuando no se pudo obtener respuesta.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
from typing import Final

import httpx
from lxml import etree

from app.catalogs.cdr_codes import (
    TICKET_ACCEPTED,
    TICKET_IN_PROCESS,
    TICKET_REJECTED,
    CdrOutcome,
    classify_cdr_code,
)
from app.core.errors import SunatError
from app.core.logging import get_logger
from app.sunat import envelopes
from app.xml.cdr_parser import CdrResult, parse_cdr
from app.xml.zip_helper import extract_cdr

logger = get_logger(__name__)

CONNECT_TIMEOUT: Final = 10.0
DEFAULT_READ_TIMEOUT: Final = 25.0

_HEADERS: Final = {
    "Content-Type": "text/xml;charset=UTF-8",
    "SOAPAction": "",
}


class TicketStatus(str, Enum):
    """Estado de un ticket de `sendSummary`."""

    IN_PROCESS = "IN_PROCESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class TicketResult:
    status: TicketStatus
    status_code: str
    cdr: CdrResult | None = None


@dataclass(frozen=True, slots=True)
class SunatCredentials:
    ruc: str
    sol_user: str
    sol_password: str


def _local(node: etree._Element, name: str) -> str | None:
    """Busca por `local-name()`: los prefijos de SUNAT varían entre ambientes."""
    for element in node.xpath(f"//*[local-name()='{name}']"):
        if element.text and element.text.strip():
            return element.text.strip()
    return None


def _raise_for_fault(root: etree._Element) -> None:
    """Convierte un `soap:Fault` en `SunatError` ya clasificado."""
    faults = root.xpath("//*[local-name()='Fault']")
    if not faults:
        return

    fault = faults[0]
    code = _local(fault, "faultcode") or ""
    message = _local(fault, "faultstring") or "SUNAT devolvió un SOAP Fault sin detalle."
    outcome = classify_cdr_code(code)

    raise SunatError(
        message,
        details={"faultcode": code},
        retryable=outcome is CdrOutcome.RETRYABLE,
        sunat_code=code,
    )


class SunatClient:
    """Cliente del billService.

    :param transport: permite inyectar `httpx.MockTransport` en los tests, así
        que la suite no depende de que SUNAT esté disponible.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = DEFAULT_READ_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT),
            headers=_HEADERS,
            transport=transport,
            follow_redirects=False,
        )

    def __enter__(self) -> SunatClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ── transporte ──────────────────────────────────────────────────────────

    def _post(self, envelope: bytes, operation: str) -> etree._Element:
        try:
            response = self._client.post(self._url, content=envelope)
        except httpx.TimeoutException as exc:
            raise SunatError(
                f"SUNAT no respondió a tiempo en {operation}.", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise SunatError(
                f"No se pudo contactar a SUNAT en {operation}: {exc}", retryable=True
            ) from exc

        if response.status_code >= 500:
            raise SunatError(
                f"SUNAT devolvió HTTP {response.status_code} en {operation}.",
                details={"status_code": response.status_code},
                retryable=True,
            )

        try:
            root = etree.fromstring(response.content)
        except etree.XMLSyntaxError as exc:
            raise SunatError(
                f"La respuesta de SUNAT no es XML válido en {operation}.",
                retryable=response.status_code < 400,
            ) from exc

        _raise_for_fault(root)

        if response.status_code >= 400:
            raise SunatError(
                f"SUNAT devolvió HTTP {response.status_code} en {operation}.",
                details={"status_code": response.status_code},
                retryable=False,
            )

        return root

    @staticmethod
    def _decode_cdr(root: etree._Element, field: str = "applicationResponse") -> CdrResult:
        payload = _local(root, field)
        if not payload:
            raise SunatError(
                f"La respuesta de SUNAT no contiene <{field}>.", retryable=True
            )
        return parse_cdr(extract_cdr(base64.b64decode(payload)))

    # ── operaciones ─────────────────────────────────────────────────────────

    def send_bill(
        self, credentials: SunatCredentials, filename: str, zip_content: bytes
    ) -> CdrResult:
        """Envío síncrono. Devuelve el CDR, sea aceptación o rechazo."""
        envelope = envelopes.build_send_bill(
            credentials.ruc, credentials.sol_user, credentials.sol_password,
            filename, zip_content,
        )
        root = self._post(envelope, "sendBill")
        result = self._decode_cdr(root)
        logger.info(
            "sendBill respondido",
            extra={"filename": filename, "sunat_code": result.response_code,
                   "outcome": result.outcome.value},
        )
        return result

    def send_summary(
        self, credentials: SunatCredentials, filename: str, zip_content: bytes
    ) -> str:
        """Envío asíncrono. Devuelve el ticket a consultar con `get_status`."""
        envelope = envelopes.build_send_summary(
            credentials.ruc, credentials.sol_user, credentials.sol_password,
            filename, zip_content,
        )
        root = self._post(envelope, "sendSummary")
        ticket = _local(root, "ticket")
        if not ticket:
            raise SunatError("SUNAT no devolvió ticket en sendSummary.", retryable=True)
        logger.info("sendSummary respondido", extra={"filename": filename, "ticket": ticket})
        return ticket

    def get_status(self, credentials: SunatCredentials, ticket: str) -> TicketResult:
        """Consulta un ticket. Mientras devuelva `98` sigue en proceso."""
        envelope = envelopes.build_get_status(
            credentials.ruc, credentials.sol_user, credentials.sol_password, ticket
        )
        root = self._post(envelope, "getStatus")

        status_code = _local(root, "statusCode")
        if status_code is None:
            raise SunatError("SUNAT no devolvió statusCode en getStatus.", retryable=True)

        if status_code == TICKET_IN_PROCESS:
            return TicketResult(status=TicketStatus.IN_PROCESS, status_code=status_code)

        cdr = self._decode_cdr(root, "content")
        status = TicketStatus.ACCEPTED if status_code == TICKET_ACCEPTED else TicketStatus.REJECTED
        if status_code not in (TICKET_ACCEPTED, TICKET_REJECTED):
            # Códigos no documentados: se decide por el CDR, que es la verdad.
            status = TicketStatus.ACCEPTED if cdr.is_accepted else TicketStatus.REJECTED
        return TicketResult(status=status, status_code=status_code, cdr=cdr)

    def get_status_cdr(
        self, credentials: SunatCredentials, document_type: str, series: str, number: int
    ) -> CdrResult:
        """Recupera el CDR de un comprobante ya enviado.

        Es la vía de reconciliación tras un envío sin respuesta: pregunta en vez
        de reenviar, evitando el duplicado que devolvería el código 1033.
        """
        envelope = envelopes.build_get_status_cdr(
            credentials.ruc, credentials.sol_user, credentials.sol_password,
            document_type, series, number,
        )
        root = self._post(envelope, "getStatusCdr")
        return self._decode_cdr(root, "content")
