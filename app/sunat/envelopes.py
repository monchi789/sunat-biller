"""Envelopes SOAP para las cuatro operaciones del billService.

Se construyen a mano en lugar de usar `zeep`: son cuatro operaciones triviales y
el WSDL de SUNAT es lento e intermitente, así que descargarlo en runtime
convertiría una caída de SUNAT en un fallo de arranque del servicio.

**El escapado XML de las credenciales no es opcional.** Las claves SOL contienen
`&` y `<` con frecuencia; sin escapar se genera un envelope malformado y SUNAT
responde con un fault genérico imposible de diagnosticar.
"""

from __future__ import annotations

import base64
from xml.sax.saxutils import escape

WSSE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-secext-1.0.xsd"
)
PASSWORD_TYPE = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-username-token-profile-1.0#PasswordText"
)


def _security_header(ruc: str, sol_user: str, sol_password: str) -> str:
    """Cabecera WS-Security. El `Username` es `{RUC}{sol_user}` sin separador."""
    username = escape(f"{ruc}{sol_user}")
    password = escape(sol_password)
    return (
        f'<wsse:Security xmlns:wsse="{WSSE}">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{username}</wsse:Username>"
        f'<wsse:Password Type="{PASSWORD_TYPE}">{password}</wsse:Password>'
        "</wsse:UsernameToken>"
        "</wsse:Security>"
    )


def _envelope(body: str, ruc: str, sol_user: str, sol_password: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:ser="http://service.sunat.gob.pe">'
        f"<soapenv:Header>{_security_header(ruc, sol_user, sol_password)}</soapenv:Header>"
        f"<soapenv:Body>{body}</soapenv:Body>"
        "</soapenv:Envelope>"
    ).encode()


def build_send_bill(
    ruc: str, sol_user: str, sol_password: str, filename: str, zip_content: bytes
) -> bytes:
    """`sendBill` — envío síncrono de factura, nota de crédito o de débito."""
    body = (
        "<ser:sendBill>"
        f"<fileName>{escape(filename)}</fileName>"
        f"<contentFile>{base64.b64encode(zip_content).decode('ascii')}</contentFile>"
        "</ser:sendBill>"
    )
    return _envelope(body, ruc, sol_user, sol_password)


def build_send_summary(
    ruc: str, sol_user: str, sol_password: str, filename: str, zip_content: bytes
) -> bytes:
    """`sendSummary` — envío asíncrono de resumen diario o comunicación de baja."""
    body = (
        "<ser:sendSummary>"
        f"<fileName>{escape(filename)}</fileName>"
        f"<contentFile>{base64.b64encode(zip_content).decode('ascii')}</contentFile>"
        "</ser:sendSummary>"
    )
    return _envelope(body, ruc, sol_user, sol_password)


def build_get_status(ruc: str, sol_user: str, sol_password: str, ticket: str) -> bytes:
    """`getStatus` — consulta el ticket devuelto por `sendSummary`."""
    body = f"<ser:getStatus><ticket>{escape(ticket)}</ticket></ser:getStatus>"
    return _envelope(body, ruc, sol_user, sol_password)


def build_get_status_cdr(
    ruc: str, sol_user: str, sol_password: str,
    document_type: str, series: str, number: int,
) -> bytes:
    """`getStatusCdr` — recupera el CDR de un comprobante ya enviado.

    Es la vía de **reconciliación**: si un envío se perdió sin respuesta, esto
    dice si SUNAT lo recibió, en lugar de reenviarlo y arriesgar un duplicado.
    """
    body = (
        "<ser:getStatusCdr>"
        f"<rucComprobante>{escape(ruc)}</rucComprobante>"
        f"<tipoComprobante>{escape(document_type)}</tipoComprobante>"
        f"<serieComprobante>{escape(series)}</serieComprobante>"
        f"<numeroComprobante>{number}</numeroComprobante>"
        "</ser:getStatusCdr>"
    )
    return _envelope(body, ruc, sol_user, sol_password)


#: Mapa de operación → constructor, para tests y despacho genérico.
BUILDERS = {
    "sendBill": build_send_bill,
    "sendSummary": build_send_summary,
    "getStatus": build_get_status,
    "getStatusCdr": build_get_status_cdr,
}


def build_envelope(operation: str, *args: object, **kwargs: object) -> bytes:
    try:
        builder = BUILDERS[operation]
    except KeyError:
        raise ValueError(f"Operación SOAP desconocida: {operation!r}") from None
    return builder(*args, **kwargs)  # type: ignore[arg-type]
