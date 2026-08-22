"""La API arranca y responde. Es lo que consulta el healthcheck del contenedor."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


class TestHealth:
    def test_responde_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_informa_el_ambiente_sunat(self, client: TestClient) -> None:
        """Confundir BETA con PRODUCTION es un incidente fiscal, no un bug."""
        assert client.get("/health").json()["sunat_environment"] in {"BETA", "PRODUCTION"}

    def test_no_requiere_autenticacion(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200


class TestContextoDeRequest:
    def test_devuelve_un_request_id(self, client: TestClient) -> None:
        assert client.get("/health").headers["X-Request-ID"]

    def test_respeta_el_request_id_entrante(self, client: TestClient) -> None:
        """Permite correlacionar con las trazas del sistema que nos llama."""
        response = client.get("/health", headers={"X-Request-ID": "traza-123"})
        assert response.headers["X-Request-ID"] == "traza-123"

    def test_cada_request_tiene_id_distinto(self, client: TestClient) -> None:
        first = client.get("/health").headers["X-Request-ID"]
        second = client.get("/health").headers["X-Request-ID"]
        assert first != second


class TestOpenApi:
    def test_el_esquema_se_publica_bajo_el_prefijo_de_version(self, client: TestClient) -> None:
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        assert response.json()["info"]["title"] == "sunat-biller"

    def test_la_documentacion_es_accesible(self, client: TestClient) -> None:
        assert client.get("/docs").status_code == 200
