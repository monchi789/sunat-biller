"""Emisión de facturas de punta a punta, con SUNAT simulado.

Recorre el mismo camino que `docs/PRUEBAS.md`: empresa, credenciales,
certificado, serie, API key y emisión.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tools.test_certificate import build_certificate, write_pfx
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.db, requires_db]

RUC = "10123456781"
CUSTOMER_RUC = "20000000001"


def invoice_payload(**overrides: object) -> dict:
    from datetime import date

    return {
        "issue_date": date.today().isoformat(),
        "currency": "PEN",
        "customer": {
            "document_type": "6",
            "document_number": CUSTOMER_RUC,
            "name": "CLIENTE DE PRUEBA SAC",
        },
        "items": [
            {
                "line_number": 1,
                "description": "SERVICIO DE CONSULTORIA",
                "quantity": "1",
                "unit_code": "ZZ",
                "unit_value": "100.00",
                "tax_affectation": "10",
            }
        ],
        **overrides,
    }


@pytest.fixture
def emisor(client: TestClient, admin_headers: dict, tmp_path: Path) -> Generator[dict]:
    """Empresa lista para emitir: credenciales, certificado, serie y API key."""
    company_id = client.post(
        "/api/v1/companies",
        json={
            "ruc": RUC,
            "business_name": "MI NEGOCIO EIRL",
            "address": "AV. SIEMPRE VIVA 742",
            "ubigeo": "150101",
            "country_code": "PE",
        },
        headers=admin_headers,
    ).json()["id"]

    client.patch(
        f"/api/v1/companies/{company_id}/sunat-credentials",
        json={"sol_user": "MODDATOS", "sol_password": "moddatos"},
        headers=admin_headers,
    )

    key, certificate = build_certificate(RUC, "MI NEGOCIO EIRL")
    pfx = tmp_path / "emisor.pfx"
    write_pfx(key, certificate, "clave123", pfx)
    with pfx.open("rb") as handle:
        client.post(
            f"/api/v1/companies/{company_id}/certificates",
            files={"file": ("emisor.pfx", handle, "application/x-pkcs12")},
            data={"password": "clave123"},
            headers=admin_headers,
        )

    client.post(
        f"/api/v1/companies/{company_id}/series",
        json={"document_type": "01", "series": "F001"},
        headers=admin_headers,
    )

    api_key = client.post(
        f"/api/v1/companies/{company_id}/api-keys",
        json={"name": "pruebas"},
        headers=admin_headers,
    ).json()["key"]

    yield {"company_id": company_id, "headers": {"X-API-Key": api_key}}


class TestEmisionAceptada:
    def test_emite_y_sunat_acepta(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        response = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ACCEPTED"
        assert body["sunat_code"] == "0"
        assert body["series"] == "F001"
        assert body["number"] == 1
        assert body["filename"] == f"{RUC}-01-F001-00000001"

    def test_calcula_el_igv_sin_que_el_cliente_lo_envie(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        """El JSON de entrada solo trae cantidad, valor y afectación."""
        body = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()
        assert body["subtotal"] == "100.00"
        assert body["igv_total"] == "18.00"
        assert body["total"] == "118.00"
        assert body["items"][0]["igv_amount"] == "18.00"

    def test_guarda_el_digest_de_la_firma(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        body = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()
        assert body["xml_hash"] and len(body["xml_hash"]) == 44

    def test_el_correlativo_avanza(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        numbers = [
            client.post(
                "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
            ).json()["number"]
            for _ in range(3)
        ]
        assert numbers == [1, 2, 3]


class TestRespuestasDeSunat:
    def test_rechazo_llega_como_200(
        self, client: TestClient, emisor: dict, sunat_rejected: None
    ) -> None:
        """Un rechazo es una respuesta válida del servicio, no un error HTTP."""
        response = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        )
        assert response.status_code == 200
        assert response.json()["status"] == "REJECTED"
        assert response.json()["sunat_code"] == "2335"

    def test_observaciones(self, client: TestClient, emisor: dict, sunat_observed: None) -> None:
        body = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()
        assert body["status"] == "ACCEPTED_WITH_OBSERVATION"

    def test_sunat_caido_deja_el_comprobante_para_reintento(
        self, client: TestClient, emisor: dict, sunat_down: None
    ) -> None:
        """El XML ya está firmado; el comprobante queda en SENT, no se pierde."""
        response = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        )
        assert response.status_code == 200
        assert response.json()["status"] == "SENT"


class TestValidaciones:
    def test_exige_cliente_con_ruc(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        payload = invoice_payload()
        payload["customer"]["document_type"] = "1"
        payload["customer"]["document_number"] = "12345678"
        response = client.post("/api/v1/invoices", json=payload, headers=emisor["headers"])
        assert response.status_code == 422

    def test_rechaza_fecha_futura(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        from datetime import date, timedelta

        payload = invoice_payload(issue_date=(date.today() + timedelta(days=1)).isoformat())
        response = client.post("/api/v1/invoices", json=payload, headers=emisor["headers"])
        assert response.status_code == 422
        assert "futura" in response.json()["message"]

    def test_rechaza_importes_que_no_cuadran(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        """Si el ERP del cliente calcula distinto, mejor enterarse antes de emitir."""
        payload = invoice_payload()
        payload["items"][0]["igv_amount"] = "50.00"
        response = client.post("/api/v1/invoices", json=payload, headers=emisor["headers"])
        assert response.status_code == 422
        assert response.json()["error_code"] == "TOTALS_MISMATCH"

    def test_sin_serie_activa(self, client: TestClient, admin_headers: dict) -> None:
        company_id = client.post(
            "/api/v1/companies",
            json={
                "ruc": "10445566778",
                "business_name": "SIN SERIE",
                "address": "X",
                "ubigeo": "150101",
                "country_code": "PE",
            },
            headers=admin_headers,
        ).json()["id"]
        client.patch(
            f"/api/v1/companies/{company_id}/sunat-credentials",
            json={"sol_user": "MODDATOS", "sol_password": "moddatos"},
            headers=admin_headers,
        )
        api_key = client.post(
            f"/api/v1/companies/{company_id}/api-keys",
            json={"name": "k"},
            headers=admin_headers,
        ).json()["key"]

        response = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers={"X-API-Key": api_key}
        )
        assert response.status_code == 404


class TestDescargas:
    def test_descarga_el_xml_firmado(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        document_id = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()["id"]

        response = client.get(f"/api/v1/documents/{document_id}/xml", headers=emisor["headers"])
        assert response.status_code == 200
        assert b"<ds:Signature" in response.content
        assert b"<cbc:ID>F001-00000001</cbc:ID>" in response.content

    def test_descarga_el_cdr(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        """El CDR es el respaldo de que SUNAT recibió el comprobante."""
        document_id = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()["id"]

        response = client.get(f"/api/v1/documents/{document_id}/cdr", headers=emisor["headers"])
        assert response.status_code == 200
        assert b"<cbc:ResponseCode>0</cbc:ResponseCode>" in response.content

    def test_sin_cdr_si_sunat_no_respondio(
        self, client: TestClient, emisor: dict, sunat_down: None
    ) -> None:
        document_id = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()["id"]

        # El XML firmado sí existe; el CDR no, porque nunca llegó.
        assert client.get(
            f"/api/v1/documents/{document_id}/xml", headers=emisor["headers"]
        ).status_code == 200
        assert client.get(
            f"/api/v1/documents/{document_id}/cdr", headers=emisor["headers"]
        ).status_code == 404

    def test_lista_los_comprobantes(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        client.post("/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"])
        response = client.get("/api/v1/documents", headers=emisor["headers"])
        assert response.status_code == 200
        assert response.json()["total"] == 1


class TestIdempotencia:
    def test_la_misma_clave_no_emite_dos_veces(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        """Un reintento de red del cliente no puede duplicar el comprobante."""
        key = "clave-idempotente-1"
        headers = {**emisor["headers"], "X-Idempotency-Key": key}

        first = client.post("/api/v1/invoices", json=invoice_payload(), headers=headers)
        second = client.post("/api/v1/invoices", json=invoice_payload(), headers=headers)

        assert first.status_code == second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["number"] == second.json()["number"]
        assert second.headers.get("X-Idempotent-Replay") == "true"

        listado = client.get("/api/v1/documents", headers=emisor["headers"]).json()
        assert listado["total"] == 1, "se emitió más de una factura con la misma clave"

    def test_claves_distintas_emiten_comprobantes_distintos(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        numbers = set()
        for key in ("a", "b", "c"):
            response = client.post(
                "/api/v1/invoices",
                json=invoice_payload(),
                headers={**emisor["headers"], "X-Idempotency-Key": key},
            )
            numbers.add(response.json()["number"])
        assert numbers == {1, 2, 3}


class TestConsulta:
    def test_obtener_por_id(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        document_id = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"]
        ).json()["id"]

        response = client.get(f"/api/v1/invoices/{document_id}", headers=emisor["headers"])
        assert response.status_code == 200
        assert response.json()["id"] == document_id
        assert response.json()["customer"]["document_number"] == CUSTOMER_RUC

    def test_filtra_por_estado(
        self, client: TestClient, emisor: dict, sunat_accepted: None
    ) -> None:
        client.post("/api/v1/invoices", json=invoice_payload(), headers=emisor["headers"])
        aceptados = client.get(
            "/api/v1/documents?status=ACCEPTED", headers=emisor["headers"]
        ).json()
        rechazados = client.get(
            "/api/v1/documents?status=REJECTED", headers=emisor["headers"]
        ).json()
        assert aceptados["total"] == 1
        assert rechazados["total"] == 0

    def test_comprobante_inexistente(self, client: TestClient, emisor: dict) -> None:
        from uuid import uuid4

        assert client.get(
            f"/api/v1/invoices/{uuid4()}", headers=emisor["headers"]
        ).status_code == 404
