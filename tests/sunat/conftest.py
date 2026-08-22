"""Respuestas SOAP simuladas de SUNAT.

Se usa `httpx.MockTransport` en lugar de `respx`: el cliente es httpx propio, así
que inyectar el transporte es la vía natural y no añade dependencias.
"""

from __future__ import annotations

import base64
import io
import zipfile
from collections.abc import Callable

import httpx
import pytest

from app.sunat.client import SunatClient, SunatCredentials

CREDENTIALS = SunatCredentials(ruc="20000000001", sol_user="MODDATOS", sol_password="moddatos")

CDR_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<ar:ApplicationResponse
    xmlns:ar="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2"
    xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>20000000001-01-F001-00000001</cbc:ID>
  <cac:DocumentResponse>
    <cac:Response>
      <cbc:ReferenceID>F001-00000001</cbc:ReferenceID>
      <cbc:ResponseCode>{code}</cbc:ResponseCode>
      <cbc:Description>{description}</cbc:Description>
    </cac:Response>
  </cac:DocumentResponse>
</ar:ApplicationResponse>"""


def cdr_zip_base64(code: str = "0", description: str = "La Factura ha sido aceptada") -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "R-20000000001-01-F001-00000001.xml",
            CDR_TEMPLATE.format(code=code, description=description).encode("utf-8"),
        )
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def soap_response(inner: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soapenv:Body>{inner}</soapenv:Body></soapenv:Envelope>"
    ).encode()


def send_bill_response(code: str = "0", description: str = "aceptada") -> bytes:
    return soap_response(
        '<ns2:sendBillResponse xmlns:ns2="http://service.sunat.gob.pe">'
        f"<applicationResponse>{cdr_zip_base64(code, description)}</applicationResponse>"
        "</ns2:sendBillResponse>"
    )


def send_summary_response(ticket: str = "1234567890123") -> bytes:
    return soap_response(
        '<ns2:sendSummaryResponse xmlns:ns2="http://service.sunat.gob.pe">'
        f"<ticket>{ticket}</ticket></ns2:sendSummaryResponse>"
    )


def get_status_response(status_code: str, *, cdr_code: str = "0") -> bytes:
    content = (
        f"<content>{cdr_zip_base64(cdr_code)}</content>" if status_code != "98" else ""
    )
    return soap_response(
        '<ns2:getStatusResponse xmlns:ns2="http://service.sunat.gob.pe"><status>'
        f"<statusCode>{status_code}</statusCode>{content}"
        "</status></ns2:getStatusResponse>"
    )


def soap_fault(code: str, message: str) -> bytes:
    return soap_response(
        f"<soapenv:Fault><faultcode>soap-env:Client.{code}</faultcode>"
        f"<faultstring>{message}</faultstring></soapenv:Fault>"
    )


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> SunatClient:
    return SunatClient("https://sunat.test/billService", transport=httpx.MockTransport(handler))


def responds(content: bytes, status_code: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content)

    return handler


@pytest.fixture
def credentials() -> SunatCredentials:
    return CREDENTIALS
