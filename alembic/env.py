"""Entorno de Alembic.

La URL y los metadatos salen de la aplicación, no del `alembic.ini`: así hay un
solo lugar donde se configura la base de datos y las migraciones se comportan
igual en desarrollo, en el contenedor y en los tests.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base

config = context.config

# La URL por defecto sale de la configuración de la app, pero se respeta la que
# venga ya puesta: así los tests pueden apuntar a `TEST_DATABASE_URL` y se puede
# migrar otra base con `alembic -x` sin tocar el entorno.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
