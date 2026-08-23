"""Alta de empresa, credenciales, certificado, serie y API key."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.tools.test_certificate import build_certificate, write_pfx
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.db, requires_db]

RUC = "10123456781"  # persona natural, con dígito verificador válido


def company_payload(**overrides: object) -> dict:
    return {
        "ruc": RUC,
        "business_name": "MI NEGOCIO EIRL",
        "address": "AV. SIEMPRE VIVA 742",
        "ubigeo": "150101",
        "country_code": "PE",
        **overrides,
    }


class TestAltaDeEmpresa:
    def test_crea_la_empresa(self, client: TestClient, admin_headers: dict) -> None:
        response = client.post("/api/v1/companies", json=company_payload(), headers=admin_headers)
        assert response.status_code == 201
        body = response.json()
        assert body["ruc"] == RUC
        assert body["active"] is True

    def test_nunca_expone_las_credenciales_sol(
        self, client: TestClient, admin_headers: dict
    ) -> None:
        body = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()
        assert "sol_password_secret" not in body
        assert "sol_user" not in body

    def test_rechaza_ruc_con_digito_verificador_invalido(
        self, client: TestClient, admin_headers: dict
    ) -> None:
        response = client.post(
            "/api/v1/companies", json=company_payload(ruc="10123456789"), headers=admin_headers
        )
        assert response.status_code == 422
        assert response.json()["error_code"] == "VALIDATION_ERROR"

    def test_rechaza_ruc_duplicado(self, client: TestClient, admin_headers: dict) -> None:
        client.post("/api/v1/companies", json=company_payload(), headers=admin_headers)
        response = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "CONFLICT"

    def test_exige_token_de_administracion(self, client: TestClient) -> None:
        """Sin esto cualquiera podría darse de alta como emisor."""
        response = client.post("/api/v1/companies", json=company_payload())
        assert response.status_code == 401


class TestCredencialesSol:
    def test_guarda_las_credenciales_cifradas(
        self, client: TestClient, admin_headers: dict, db_session
    ) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]

        response = client.patch(
            f"/api/v1/companies/{company_id}/sunat-credentials",
            json={"sol_user": "MODDATOS", "sol_password": "moddatos"},
            headers=admin_headers,
        )
        assert response.status_code == 200

        from uuid import UUID

        from app.models.company import Company

        company = db_session.get(Company, UUID(company_id))
        assert company.sol_user == "MODDATOS"
        assert company.sol_password_secret is not None
        assert "moddatos" not in company.sol_password_secret


class TestCertificados:
    @pytest.fixture
    def pfx(self, tmp_path: Path) -> tuple[Path, str]:
        key, certificate = build_certificate(RUC, "MI NEGOCIO EIRL")
        path = tmp_path / "test.pfx"
        write_pfx(key, certificate, "clave123", path)
        return path, "clave123"

    def test_sube_un_certificado(
        self, client: TestClient, admin_headers: dict, pfx: tuple[Path, str]
    ) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]
        path, password = pfx

        with path.open("rb") as handle:
            response = client.post(
                f"/api/v1/companies/{company_id}/certificates",
                files={"file": ("test.pfx", handle, "application/x-pkcs12")},
                data={"password": password},
                headers=admin_headers,
            )

        assert response.status_code == 201
        body = response.json()
        assert body["active"] is True
        assert body["serial_number"]
        assert "certificate_path" not in body  # nunca se expone la ruta

    def test_rechaza_contrasena_incorrecta(
        self, client: TestClient, admin_headers: dict, pfx: tuple[Path, str]
    ) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]
        path, _ = pfx

        with path.open("rb") as handle:
            response = client.post(
                f"/api/v1/companies/{company_id}/certificates",
                files={"file": ("test.pfx", handle, "application/x-pkcs12")},
                data={"password": "incorrecta"},
                headers=admin_headers,
            )
        assert response.status_code == 422
        assert response.json()["error_code"] == "CERTIFICATE_ERROR"

    def test_rechaza_extension_no_valida(self, client: TestClient, admin_headers: dict) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]
        response = client.post(
            f"/api/v1/companies/{company_id}/certificates",
            files={"file": ("cert.txt", b"no soy un pfx", "text/plain")},
            data={"password": "x"},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestSeries:
    def test_crea_una_serie(self, client: TestClient, admin_headers: dict) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]
        response = client.post(
            f"/api/v1/companies/{company_id}/series",
            json={"document_type": "01", "series": "F001"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["current_number"] == 0

    def test_rechaza_formato_invalido(self, client: TestClient, admin_headers: dict) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]
        response = client.post(
            f"/api/v1/companies/{company_id}/series",
            json={"document_type": "01", "series": "FF01"},
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestApiKeys:
    def test_devuelve_la_clave_una_sola_vez(self, client: TestClient, admin_headers: dict) -> None:
        company_id = client.post(
            "/api/v1/companies", json=company_payload(), headers=admin_headers
        ).json()["id"]

        created = client.post(
            f"/api/v1/companies/{company_id}/api-keys",
            json={"name": "integración POS"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        raw_key = created.json()["key"]
        assert raw_key.startswith("sk_")

        listed = client.get(
            f"/api/v1/companies/{company_id}/api-keys", headers=admin_headers
        ).json()
        assert len(listed) == 1
        assert "key" not in listed[0]
        assert raw_key not in str(listed)
