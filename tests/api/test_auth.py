"""Autenticación y aislamiento entre empresas (RNF-01.1 y RNF-01.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.db, requires_db]


def create_company(client: TestClient, admin_headers: dict, ruc: str) -> str:
    return client.post(
        "/api/v1/companies",
        json={
            "ruc": ruc,
            "business_name": f"EMPRESA {ruc}",
            "address": "AV. TEST 1",
            "ubigeo": "150101",
            "country_code": "PE",
        },
        headers=admin_headers,
    ).json()["id"]


def issue_key(client: TestClient, admin_headers: dict, company_id: str, **payload: object) -> str:
    return client.post(
        f"/api/v1/companies/{company_id}/api-keys",
        json={"name": "test", **payload},
        headers=admin_headers,
    ).json()["key"]


class TestApiKey:
    def test_sin_cabecera_devuelve_401(self, client: TestClient) -> None:
        assert client.get("/api/v1/documents").status_code == 401

    def test_clave_inexistente_devuelve_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/documents", headers={"X-API-Key": "sk_" + "0" * 64})
        assert response.status_code == 401
        assert response.json()["error_code"] == "UNAUTHORIZED"

    def test_clave_valida_da_acceso(self, client: TestClient, admin_headers: dict) -> None:
        company_id = create_company(client, admin_headers, "10123456781")
        key = issue_key(client, admin_headers, company_id)
        assert client.get("/api/v1/documents", headers={"X-API-Key": key}).status_code == 200

    def test_clave_expirada_devuelve_401(self, client: TestClient, admin_headers: dict) -> None:
        company_id = create_company(client, admin_headers, "10123456781")
        key = issue_key(client, admin_headers, company_id)

        response = client.get("/api/v1/documents", headers={"X-API-Key": key})
        assert response.status_code == 200  # todavía válida

        _expire_key(client, key)
        assert client.get("/api/v1/documents", headers={"X-API-Key": key}).status_code == 401

    def test_clave_revocada_devuelve_401(self, client: TestClient, admin_headers: dict) -> None:
        company_id = create_company(client, admin_headers, "10123456781")
        key = issue_key(client, admin_headers, company_id)
        key_id = client.get(
            f"/api/v1/companies/{company_id}/api-keys", headers=admin_headers
        ).json()[0]["id"]

        client.delete(
            f"/api/v1/companies/{company_id}/api-keys/{key_id}", headers=admin_headers
        )
        assert client.get("/api/v1/documents", headers={"X-API-Key": key}).status_code == 401

    def test_el_mensaje_no_distingue_entre_causas(
        self, client: TestClient, admin_headers: dict
    ) -> None:
        """Decir «expirada» en vez de «inválida» confirmaría que la clave existe."""
        inexistente = client.get(
            "/api/v1/documents", headers={"X-API-Key": "sk_" + "1" * 64}
        ).json()

        company_id = create_company(client, admin_headers, "10123456781")
        key = issue_key(client, admin_headers, company_id)
        _expire_key(client, key)
        expirada = client.get("/api/v1/documents", headers={"X-API-Key": key}).json()

        assert inexistente["message"] == expirada["message"]


def _expire_key(client: TestClient, raw_key: str) -> None:
    """Vence una clave a mano: el schema solo admite `expires_at` futura."""
    from sqlalchemy import select

    from app.core.database import get_db
    from app.main import app
    from app.models.api_key import APIKey
    from app.services.api_key_service import hash_key

    session = next(app.dependency_overrides[get_db]())
    api_key = session.execute(
        select(APIKey).where(APIKey.key_hash == hash_key(raw_key))
    ).scalar_one()
    api_key.expires_at = datetime.now(tz=UTC) - timedelta(hours=1)
    session.flush()


class TestAislamientoEntreEmpresas:
    def test_una_empresa_no_ve_los_comprobantes_de_otra(
        self, client: TestClient, admin_headers: dict, sunat_accepted: None, tmp_path
    ) -> None:
        """El fallo más grave posible en un facturador multi-empresa."""
        from app.tools.test_certificate import build_certificate, write_pfx
        from tests.api.test_invoices import invoice_payload

        # Empresa A, con todo listo para emitir
        ruc_a = "10123456781"
        company_a = create_company(client, admin_headers, ruc_a)
        client.patch(
            f"/api/v1/companies/{company_a}/sunat-credentials",
            json={"sol_user": "MODDATOS", "sol_password": "moddatos"},
            headers=admin_headers,
        )
        key, certificate = build_certificate(ruc_a, "EMPRESA A")
        pfx = tmp_path / "a.pfx"
        write_pfx(key, certificate, "c", pfx)
        with pfx.open("rb") as handle:
            client.post(
                f"/api/v1/companies/{company_a}/certificates",
                files={"file": ("a.pfx", handle, "application/x-pkcs12")},
                data={"password": "c"},
                headers=admin_headers,
            )
        client.post(
            f"/api/v1/companies/{company_a}/series",
            json={"document_type": "01", "series": "F001"},
            headers=admin_headers,
        )
        key_a = issue_key(client, admin_headers, company_a)

        document_id = client.post(
            "/api/v1/invoices", json=invoice_payload(), headers={"X-API-Key": key_a}
        ).json()["id"]

        # Empresa B intenta leerlo
        company_b = create_company(client, admin_headers, "10445566778")
        key_b = issue_key(client, admin_headers, company_b)

        response = client.get(
            f"/api/v1/documents/{document_id}", headers={"X-API-Key": key_b}
        )
        assert response.status_code == 404, "¡una empresa accedió al comprobante de otra!"

        listado = client.get("/api/v1/documents", headers={"X-API-Key": key_b}).json()
        assert listado["total"] == 0


class TestTokenDeAdministracion:
    def test_los_endpoints_de_alta_lo_exigen(self, client: TestClient) -> None:
        assert client.post("/api/v1/companies", json={}).status_code == 401
        assert client.get("/api/v1/companies").status_code == 401

    def test_token_incorrecto_devuelve_401(self, client: TestClient) -> None:
        response = client.get("/api/v1/companies", headers={"X-Admin-Token": "equivocado"})
        assert response.status_code == 401
