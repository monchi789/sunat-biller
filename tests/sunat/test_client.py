"""Cliente SUNAT: cada respuesta posible mapea al estado correcto.

Esta es la tabla que gobierna el comportamiento híbrido — qué se reintenta y qué
es terminal. Si cambia, el worker empezará a reenviar comprobantes rechazados.
"""

from __future__ import annotations

import httpx
import pytest

from app.catalogs.cdr_codes import CdrOutcome
from app.core.errors import SunatError
from app.sunat.client import SunatCredentials, TicketStatus
from tests.sunat.conftest import (
    get_status_response,
    make_client,
    responds,
    send_bill_response,
    send_summary_response,
    soap_fault,
)


class TestSendBill:
    def test_comprobante_aceptado(self, credentials: SunatCredentials) -> None:
        with make_client(responds(send_bill_response("0"))) as client:
            result = client.send_bill(credentials, "f.zip", b"zip")
        assert result.outcome is CdrOutcome.ACCEPTED
        assert result.is_accepted
        assert result.response_code == "0"
        assert result.reference_id == "F001-00000001"

    def test_comprobante_rechazado_no_es_excepcion(self, credentials: SunatCredentials) -> None:
        """Un rechazo es una respuesta válida: se devuelve, no se lanza."""
        with make_client(responds(send_bill_response("2335", "El documento no cumple"))) as client:
            result = client.send_bill(credentials, "f.zip", b"zip")
        assert result.outcome is CdrOutcome.REJECTED
        assert not result.is_accepted

    def test_comprobante_observado(self, credentials: SunatCredentials) -> None:
        with make_client(responds(send_bill_response("4000", "Observado"))) as client:
            result = client.send_bill(credentials, "f.zip", b"zip")
        assert result.outcome is CdrOutcome.ACCEPTED_WITH_OBSERVATION
        assert result.is_accepted
        assert result.has_observations


class TestFallosDeRed:
    def test_timeout_es_reintentable(self, credentials: SunatCredentials) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        with make_client(handler) as client, pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is True
        assert "no respondió a tiempo" in excinfo.value.message

    def test_error_de_conexion_es_reintentable(self, credentials: SunatCredentials) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sin ruta", request=request)

        with make_client(handler) as client, pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is True

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_http_5xx_es_reintentable(self, credentials: SunatCredentials, status: int) -> None:
        with make_client(responds(b"<html>error</html>", status)) as client, \
                pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is True

    def test_respuesta_no_xml_no_es_reintentable_si_fue_4xx(
        self, credentials: SunatCredentials
    ) -> None:
        with make_client(responds(b"no soy xml", 400)) as client, pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is False


class TestSoapFaults:
    def test_fault_0xxx_del_sistema_sunat_es_reintentable(
        self, credentials: SunatCredentials
    ) -> None:
        with make_client(responds(soap_fault("0111", "Servicio no disponible"))) as client, \
                pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is True
        assert excinfo.value.sunat_code == "soap-env:Client.0111"

    def test_fault_1xxx_del_contribuyente_no_es_reintentable(
        self, credentials: SunatCredentials
    ) -> None:
        """Reintentar un error de datos propios solo quema cuota."""
        with make_client(responds(soap_fault("1032", "RUC no válido"))) as client, \
                pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is False

    def test_fault_1033_ya_registrado_no_se_reintenta(
        self, credentials: SunatCredentials
    ) -> None:
        """Se resuelve consultando getStatusCdr, nunca reenviando."""
        with make_client(responds(soap_fault("1033", "El comprobante ya fue informado"))) as client, \
                pytest.raises(SunatError) as excinfo:
            client.send_bill(credentials, "f.zip", b"zip")
        assert excinfo.value.retryable is False
        assert "1033" in str(excinfo.value.sunat_code)


class TestSendSummary:
    def test_devuelve_ticket(self, credentials: SunatCredentials) -> None:
        with make_client(responds(send_summary_response("9876543210"))) as client:
            assert client.send_summary(credentials, "rc.zip", b"zip") == "9876543210"

    def test_sin_ticket_es_reintentable(self, credentials: SunatCredentials) -> None:
        empty = b'<?xml version="1.0"?><Envelope><Body><sendSummaryResponse/></Body></Envelope>'
        with make_client(responds(empty)) as client, pytest.raises(SunatError) as excinfo:
            client.send_summary(credentials, "rc.zip", b"zip")
        assert excinfo.value.retryable is True


class TestGetStatus:
    def test_ticket_en_proceso(self, credentials: SunatCredentials) -> None:
        with make_client(responds(get_status_response("98"))) as client:
            result = client.get_status(credentials, "TICKET")
        assert result.status is TicketStatus.IN_PROCESS
        assert result.cdr is None

    def test_ticket_aceptado_trae_el_cdr(self, credentials: SunatCredentials) -> None:
        with make_client(responds(get_status_response("0", cdr_code="0"))) as client:
            result = client.get_status(credentials, "TICKET")
        assert result.status is TicketStatus.ACCEPTED
        assert result.cdr is not None
        assert result.cdr.is_accepted

    def test_ticket_rechazado(self, credentials: SunatCredentials) -> None:
        with make_client(responds(get_status_response("99", cdr_code="2335"))) as client:
            result = client.get_status(credentials, "TICKET")
        assert result.status is TicketStatus.REJECTED
        assert result.cdr is not None
        assert not result.cdr.is_accepted


class TestGetStatusCdr:
    def test_recupera_el_cdr_de_un_envio_previo(self, credentials: SunatCredentials) -> None:
        """La vía de reconciliación: preguntar en vez de reenviar."""
        from tests.sunat.conftest import cdr_zip_base64, soap_response

        response = soap_response(
            "<getStatusCdrResponse><statusCdr>"
            f"<content>{cdr_zip_base64('0')}</content>"
            "</statusCdr></getStatusCdrResponse>"
        )
        with make_client(responds(response)) as client:
            result = client.get_status_cdr(credentials, "01", "F001", 1)
        assert result.is_accepted


class TestCredencialesEnLaPeticion:
    def test_el_envelope_enviado_lleva_las_credenciales(
        self, credentials: SunatCredentials
    ) -> None:
        captured: dict[str, bytes] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.content
            return httpx.Response(200, content=send_bill_response("0"))

        with make_client(handler) as client:
            client.send_bill(credentials, "f.zip", b"zip")

        assert b"20000000001MODDATOS" in captured["body"]
        assert b"moddatos" in captured["body"]

    def test_usa_los_headers_soap_correctos(self, credentials: SunatCredentials) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(request.headers)
            return httpx.Response(200, content=send_bill_response("0"))

        with make_client(handler) as client:
            client.send_bill(credentials, "f.zip", b"zip")

        assert captured["content-type"] == "text/xml;charset=UTF-8"
        assert captured["soapaction"] == ""
