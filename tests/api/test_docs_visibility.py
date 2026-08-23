"""La documentación interactiva no se publica en producción."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppEnvironment, Settings


@contextmanager
def app_with_env(app_env: str) -> Iterator[TestClient]:
    """Levanta la app con otra configuración, y la deja como estaba al salir.

    `docs_url` se fija al construir `FastAPI`, así que no basta con tocar
    `settings` en caliente: hay que recargar el módulo. Y la configuración debe
    seguir parcheada mientras el test corre, porque `/health` la lee en cada
    petición.
    """
    import app.core.config as config_module

    original = config_module.settings
    config_module.settings = Settings(
        APP_ENV=app_env,
        ENCRYPTION_KEY=original.ENCRYPTION_KEY or "x" * 44,
        SECRET_KEY="clave-de-prueba-no-por-defecto",
        ADMIN_TOKEN="token-de-prueba",
    )
    import app.main as main_module

    try:
        reloaded = importlib.reload(main_module)
        with TestClient(reloaded.app) as client:
            yield client
    finally:
        config_module.settings = original
        importlib.reload(main_module)


class TestDesarrollo:
    def test_publica_docs_y_esquema(self) -> None:
        with app_with_env("development") as client:
            assert client.get("/docs").status_code == 200
            assert client.get("/redoc").status_code == 200
            assert client.get("/api/v1/openapi.json").status_code == 200


class TestProduccion:
    @pytest.mark.parametrize("path", ["/docs", "/redoc", "/api/v1/openapi.json"])
    def test_oculta_la_documentacion(self, path: str) -> None:
        with app_with_env("production") as client:
            assert client.get(path).status_code == 404

    def test_health_sigue_disponible(self) -> None:
        """El orquestador de contenedores lo necesita también en producción."""
        with app_with_env("production") as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["app_env"] == "production"

    def test_los_endpoints_siguen_funcionando(self) -> None:
        """Ocultar los docs no puede apagar la API."""
        with app_with_env("production") as client:
            # Sin credenciales devuelve 401, no 404: la ruta existe.
            assert client.get("/api/v1/documents").status_code == 401


class TestConfiguracion:
    def test_app_env_es_independiente_del_ambiente_sunat(self) -> None:
        """En homologación se opera en producción contra el SUNAT de pruebas."""
        settings = Settings(
            APP_ENV="production",
            SUNAT_ENVIRONMENT="BETA",
            ENCRYPTION_KEY="x" * 44,
            SECRET_KEY="propia",
            ADMIN_TOKEN="t",
        )
        assert settings.is_production is True
        assert settings.sunat_is_production is False
        assert settings.docs_enabled is False
        assert "e-beta" in settings.sunat_url

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"ENCRYPTION_KEY": ""}, "ENCRYPTION_KEY"),
            ({"SECRET_KEY": "change-me-in-production"}, "SECRET_KEY"),
            ({"ADMIN_TOKEN": ""}, "ADMIN_TOKEN"),
        ],
    )
    def test_produccion_exige_secretos_reales(self, kwargs: dict, expected: str) -> None:
        base = {
            "APP_ENV": "production",
            "ENCRYPTION_KEY": "x" * 44,
            "SECRET_KEY": "propia",
            "ADMIN_TOKEN": "t",
        }
        with pytest.raises(ValueError, match=expected):
            Settings(**{**base, **kwargs})

    def test_desarrollo_arranca_con_los_defaults(self) -> None:
        assert Settings(APP_ENV="development").APP_ENV is AppEnvironment.DEVELOPMENT
