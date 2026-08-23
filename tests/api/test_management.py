"""Actualización, baja y consulta de los recursos de configuración."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tools.test_certificate import build_certificate, write_pfx
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.db, requires_db]

RUC = "10123456781"


@pytest.fixture
def company_id(client: TestClient, admin_headers: dict) -> str:
    return client.post(
        "/api/v1/companies",
        json={
            "ruc": RUC,
            "business_name": "MI NEGOCIO",
            "address": "AV. TEST 1",
            "ubigeo": "150101",
            "country_code": "PE",
        },
        headers=admin_headers,
    ).json()["id"]


class TestEmpresas:
    def test_obtener(self, client: TestClient, admin_headers: dict, company_id: str) -> None:
        response = client.get(f"/api/v1/companies/{company_id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["ruc"] == RUC

    def test_actualizar(self, client: TestClient, admin_headers: dict, company_id: str) -> None:
        response = client.patch(
            f"/api/v1/companies/{company_id}",
            json={"commercial_name": "MI TIENDA", "address": "NUEVA DIRECCION 99"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["commercial_name"] == "MI TIENDA"
        assert response.json()["address"] == "NUEVA DIRECCION 99"

    def test_no_permite_cambiar_el_ruc(
        self, client: TestClient, admin_headers: dict, company_id: str
    ) -> None:
        """El RUC identifica al emisor en todo lo ya emitido."""
        client.patch(
            f"/api/v1/companies/{company_id}", json={"ruc": "20000000001"}, headers=admin_headers
        )
        assert client.get(
            f"/api/v1/companies/{company_id}", headers=admin_headers
        ).json()["ruc"] == RUC

    def test_baja_logica(self, client: TestClient, admin_headers: dict, company_id: str) -> None:
        assert client.delete(
            f"/api/v1/companies/{company_id}", headers=admin_headers
        ).status_code == 204
        assert client.get(
            f"/api/v1/companies/{company_id}", headers=admin_headers
        ).status_code == 404

    def test_listado_paginado(self, client: TestClient, admin_headers: dict, company_id: str) -> None:
        response = client.get("/api/v1/companies?page=1&page_size=10", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert body["page"] == 1

    def test_empresa_inexistente(self, client: TestClient, admin_headers: dict) -> None:
        from uuid import uuid4

        assert client.get(
            f"/api/v1/companies/{uuid4()}", headers=admin_headers
        ).status_code == 404


class TestSeries:
    def test_listar(self, client: TestClient, admin_headers: dict, company_id: str) -> None:
        client.post(
            f"/api/v1/companies/{company_id}/series",
            json={"document_type": "01", "series": "F001"},
            headers=admin_headers,
        )
        response = client.get(f"/api/v1/companies/{company_id}/series", headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_desactivar(self, client: TestClient, admin_headers: dict, company_id: str) -> None:
        series_id = client.post(
            f"/api/v1/companies/{company_id}/series",
            json={"document_type": "01", "series": "F001"},
            headers=admin_headers,
        ).json()["id"]

        response = client.patch(
            f"/api/v1/companies/{company_id}/series/{series_id}",
            json={"active": False},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["active"] is False

    def test_rechaza_serie_duplicada(
        self, client: TestClient, admin_headers: dict, company_id: str
    ) -> None:
        payload = {"document_type": "01", "series": "F001"}
        client.post(
            f"/api/v1/companies/{company_id}/series", json=payload, headers=admin_headers
        )
        response = client.post(
            f"/api/v1/companies/{company_id}/series", json=payload, headers=admin_headers
        )
        assert response.status_code == 409


class TestCertificados:
    @pytest.fixture
    def pfx(self, tmp_path: Path) -> tuple[Path, str]:
        key, certificate = build_certificate(RUC, "MI NEGOCIO")
        path = tmp_path / "c.pfx"
        write_pfx(key, certificate, "clave", path)
        return path, "clave"

    def _upload(self, client: TestClient, headers: dict, company_id: str, pfx: tuple[Path, str]):
        path, password = pfx
        with path.open("rb") as handle:
            return client.post(
                f"/api/v1/companies/{company_id}/certificates",
                files={"file": ("c.pfx", handle, "application/x-pkcs12")},
                data={"password": password},
                headers=headers,
            )

    def test_listar(
        self, client: TestClient, admin_headers: dict, company_id: str, pfx: tuple[Path, str]
    ) -> None:
        self._upload(client, admin_headers, company_id, pfx)
        response = client.get(
            f"/api/v1/companies/{company_id}/certificates", headers=admin_headers
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_subir_uno_nuevo_desactiva_el_anterior(
        self, client: TestClient, admin_headers: dict, company_id: str, pfx: tuple[Path, str]
    ) -> None:
        """RF-02.2: solo puede haber un certificado activo por empresa."""
        self._upload(client, admin_headers, company_id, pfx)
        self._upload(client, admin_headers, company_id, pfx)

        certificados = client.get(
            f"/api/v1/companies/{company_id}/certificates", headers=admin_headers
        ).json()
        assert len(certificados) == 2
        assert sum(1 for c in certificados if c["active"]) == 1

    def test_dar_de_baja(
        self, client: TestClient, admin_headers: dict, company_id: str, pfx: tuple[Path, str]
    ) -> None:
        certificate_id = self._upload(client, admin_headers, company_id, pfx).json()["id"]
        assert client.delete(
            f"/api/v1/companies/{company_id}/certificates/{certificate_id}", headers=admin_headers
        ).status_code == 204
        assert client.get(
            f"/api/v1/companies/{company_id}/certificates", headers=admin_headers
        ).json() == []
