"""Clasificación de los códigos de respuesta de SUNAT (CDR y SOAP Fault).

Esta tabla gobierna **la política de reintentos**: decide si un fallo se vuelve a
intentar, si el documento queda en un estado terminal, o si hay que reconciliar
consultando el estado en SUNAT. La guía funcional no la cubría.

Rangos oficiales:

===============  ==========================================  =================
Rango            Significado                                 Acción
===============  ==========================================  =================
``0``            Aceptado                                    terminal, OK
``100``–``999``  Excepción del **sistema SUNAT**             reintentable
``1000``–``1999``Excepción del **contribuyente**             terminal (salvo 1033)
``2000``–``3999``Rechazo por contenido del comprobante       terminal, NO reintentar
``4000``+        Observación (el comprobante SÍ se acepta)   terminal, OK con obs.
===============  ==========================================  =================

Reintentar un rechazo ``2xxx`` reenviando el mismo correlativo es incorrecto: el
comprobante está mal formado y hay que corregirlo y emitir uno nuevo.
"""

from __future__ import annotations

from enum import Enum


class CdrOutcome(str, Enum):
    """Desenlace de una respuesta de SUNAT, ya interpretada."""

    ACCEPTED = "ACCEPTED"
    """Código 0 — comprobante aceptado sin observaciones."""

    ACCEPTED_WITH_OBSERVATION = "ACCEPTED_WITH_OBSERVATION"
    """Código 4000+ — aceptado, con observaciones a corregir a futuro."""

    REJECTED = "REJECTED"
    """Código 2000–3999 — rechazado por contenido. Terminal, no reintentar."""

    TAXPAYER_ERROR = "TAXPAYER_ERROR"
    """Código 1000–1999 — error atribuible al emisor. Terminal."""

    RETRYABLE = "RETRYABLE"
    """Código 100–999 — falla interna de SUNAT. Reintentable con backoff."""

    ALREADY_REGISTERED = "ALREADY_REGISTERED"
    """Código 1033 — el comprobante ya fue informado.

    No es un fallo: significa que un envío anterior sí llegó aunque no viéramos
    la respuesta. Se resuelve consultando ``getStatusCdr``, nunca reenviando.
    """


#: Código de excepción que indica que el comprobante ya existe en SUNAT.
ALREADY_REGISTERED_CODE = 1033

#: Estados de ticket devueltos por ``getStatus`` tras un ``sendSummary``.
TICKET_IN_PROCESS = "98"
TICKET_ACCEPTED = "0"
TICKET_REJECTED = "99"


def parse_code(raw: str | int | None) -> int | None:
    """Normaliza un código de SUNAT a entero. Devuelve ``None`` si no es numérico.

    SUNAT devuelve los códigos con ceros a la izquierda (``"0100"``) y a veces
    prefijados en el ``faultcode`` (``"soap-env:Client.0100"``).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # "soap-env:Client.0100" → "0100"
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    try:
        return int(text)
    except ValueError:
        return None


def classify_cdr_code(raw: str | int | None) -> CdrOutcome:
    """Traduce un código de respuesta de SUNAT a su desenlace."""
    code = parse_code(raw)

    if code is None:
        # Sin código interpretable tratamos el envío como reintentable: es más
        # seguro reconsultar que dar por terminal algo que no entendimos.
        return CdrOutcome.RETRYABLE

    if code == 0:
        return CdrOutcome.ACCEPTED
    if code == ALREADY_REGISTERED_CODE:
        return CdrOutcome.ALREADY_REGISTERED
    if 100 <= code <= 999:
        return CdrOutcome.RETRYABLE
    if 1000 <= code <= 1999:
        return CdrOutcome.TAXPAYER_ERROR
    if 2000 <= code <= 3999:
        return CdrOutcome.REJECTED
    if code >= 4000:
        return CdrOutcome.ACCEPTED_WITH_OBSERVATION

    return CdrOutcome.RETRYABLE


def is_retryable(raw: str | int | None) -> bool:
    """`True` si vale la pena reintentar el envío con el mismo comprobante."""
    return classify_cdr_code(raw) is CdrOutcome.RETRYABLE


def is_terminal(raw: str | int | None) -> bool:
    """`True` si la respuesta cierra el ciclo de vida del comprobante."""
    return classify_cdr_code(raw) not in (CdrOutcome.RETRYABLE, CdrOutcome.ALREADY_REGISTERED)
