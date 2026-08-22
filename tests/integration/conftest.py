"""Tests que necesitan un PostgreSQL de verdad.

Se usa la base indicada por `TEST_DATABASE_URL` en lugar de testcontainers: en
un entorno Podman rootless, testcontainers exige exportar `DOCKER_HOST` y
desactivar Ryuk, que es fricción sin contrapartida. Si la base no está, los
tests se saltan en vez de fallar.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _database_available(url: str) -> bool:
    try:
        engine = sa.create_engine(url, connect_args={"connect_timeout": 2})
        with engine.connect():
            return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _database_available(settings.TEST_DATABASE_URL),
    reason=f"no hay PostgreSQL en TEST_DATABASE_URL ({settings.TEST_DATABASE_URL})",
)


@pytest.fixture(scope="session")
def engine() -> Generator[sa.Engine]:
    """Motor apuntando a la base de test, con el esquema aplicado por Alembic.

    Se migra en vez de usar `create_all` a propósito: así cada corrida valida
    también que las migraciones estén al día.
    """
    from alembic.config import Config

    from alembic import command

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.TEST_DATABASE_URL)

    engine = sa.create_engine(
        settings.TEST_DATABASE_URL,
        pool_size=25,
        max_overflow=10,
        # Red de seguridad: un test mal escrito puede provocar espera de bloqueo.
        # Sin esto, la suite entera se cuelga sin decir por qué.
        connect_args={"options": "-c lock_timeout=5s -c statement_timeout=30s"},
    )
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: sa.Engine) -> sessionmaker[Session]:
    """Sesiones que **sí** hacen commit.

    Los tests que combinan datos comprometidos con concurrencia no pueden usar
    el `db` transaccional: su transacción abierta bloquea al teardown que intenta
    borrar esos mismos datos, y el resultado es un deadlock que cuelga la suite.
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def db(engine: sa.Engine) -> Generator[Session]:
    """Sesión envuelta en una transacción que se revierte al terminar el test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
