"""Las migraciones son la única vía de crear el esquema (RNF-04.4)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from alembic import command
from app.core.config import settings
from app.models import Base
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.db, requires_db]


@pytest.fixture
def alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL)
    return config


def test_el_esquema_no_tiene_deriva(engine: sa.Engine) -> None:
    """Atrapa el "edité el modelo y olvidé generar la migración"."""
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        differences = compare_metadata(context, Base.metadata)
    assert not differences, f"faltan migraciones para: {differences}"


def test_todas_las_tablas_existen(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names())
    expected = set(Base.metadata.tables)
    assert expected <= existing, f"tablas ausentes: {expected - existing}"


def test_el_ciclo_upgrade_downgrade_upgrade_funciona(
    alembic_config: Config, engine: sa.Engine
) -> None:
    """Una migración sin `downgrade` correcto es una migración irreversible."""
    command.downgrade(alembic_config, "base")
    inspector = sa.inspect(engine)
    inspector.clear_cache()
    assert "electronic_documents" not in inspector.get_table_names()

    command.upgrade(alembic_config, "head")
    inspector.clear_cache()
    assert "electronic_documents" in inspector.get_table_names()


def test_solo_un_certificado_activo_por_empresa(engine: sa.Engine) -> None:
    """RF-02.2 se garantiza en la BD, no solo en la aplicación."""
    inspector = sa.inspect(engine)
    indexes = inspector.get_indexes("digital_certificates")
    partial = next(
        (i for i in indexes if i["name"] == "ix_digital_certificates_company_active"), None
    )
    assert partial is not None, "falta el índice único parcial de certificados"
    assert partial["unique"] is True
    assert partial.get("dialect_options", {}).get("postgresql_where") is not None
