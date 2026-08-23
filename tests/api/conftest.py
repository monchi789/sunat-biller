"""Cliente de API sobre PostgreSQL real, con SUNAT simulado."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.services import certificate_service
from tests.integration.conftest import requires_db  # noqa: F401  (re-export)

ADMIN_TOKEN = "token-de-prueba"


@pytest.fixture(scope="session")
def api_engine() -> Generator[sa.Engine]:
    from alembic.config import Config

    from alembic import command

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL)
    command.upgrade(config, "head")

    engine = sa.create_engine(
        settings.TEST_DATABASE_URL,
        connect_args={"options": "-c lock_timeout=5s -c statement_timeout=30s"},
    )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada test escribe XML y certificados en su propio directorio temporal."""
    monkeypatch.setattr(settings, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(settings, "CERTIFICATE_ROOT", tmp_path / "certificates")
    monkeypatch.setattr(settings, "ADMIN_TOKEN", ADMIN_TOKEN)
    certificate_service.clear_cache()


@pytest.fixture
def db_session(api_engine: sa.Engine) -> Generator[Session]:
    """Sesión con rollback al final, compartida con la app vía override."""
    connection = api_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        # Los servicios hacen commit; con savepoints eso no cierra la transacción
        # externa, así que el rollback final sigue limpiando todo el test.
        join_transaction_mode="create_savepoint",
    )()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN}


# ── SUNAT simulado ──────────────────────────────────────────────────────────


@pytest.fixture
def sunat_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sunat(monkeypatch, _responder("0", "La Factura ha sido aceptada"))


@pytest.fixture
def sunat_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sunat(monkeypatch, _responder("2335", "El documento no cumple con el formato"))


@pytest.fixture
def sunat_observed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sunat(monkeypatch, _responder("4000", "Aceptada con observaciones"))


@pytest.fixture
def sunat_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("SUNAT no responde", request=request)

    _patch_sunat(monkeypatch, handler)


def _responder(code: str, description: str):
    from tests.sunat.conftest import send_bill_response

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=send_bill_response(code, description))

    return handler


def _patch_sunat(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Inyecta un transporte simulado en el cliente que crea `invoice_service`."""
    from app.sunat.client import SunatClient

    original_init = SunatClient.__init__

    def patched_init(self, url, *, timeout=25.0, transport=None):
        original_init(self, url, timeout=timeout, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(SunatClient, "__init__", patched_init)
