"""API Keys: emisión, autenticación y revocación (RF-04).

La clave se genera aleatoria, se devuelve **una sola vez** en claro y solo se
persiste su SHA-256. Si la base de datos se filtra, las claves no son
reutilizables.

SHA-256 sin sal ni KDF es lo correcto aquí, a diferencia de una contraseña: la
clave tiene 256 bits de entropía real, así que no hay diccionario que atacar, y
el hash rápido permite autenticar en cada request sin coste.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnauthorizedError
from app.models.api_key import APIKey
from app.models.company import Company
from app.schemas.api_key import APIKeyCreate

#: 32 bytes → 64 caracteres hexadecimales.
KEY_BYTES = 32

#: Prefijo visible para que se reconozca la clave en logs y configuraciones ajenas.
KEY_PREFIX = "sk_"


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def create_api_key(db: Session, company_id: UUID, data: APIKeyCreate) -> tuple[APIKey, str]:
    """Crea una API key. Devuelve el modelo y el valor en claro.

    El valor en claro **no se puede recuperar después**: quien lo pierda debe
    emitir una clave nueva.
    """
    raw_key = f"{KEY_PREFIX}{secrets.token_hex(KEY_BYTES)}"

    api_key = APIKey(
        company_id=company_id,
        name=data.name,
        key_hash=hash_key(raw_key),
        active=True,
        expires_at=data.expires_at,
    )
    db.add(api_key)
    db.flush()
    return api_key, raw_key


def authenticate(db: Session, raw_key: str) -> Company:
    """Resuelve la empresa dueña de la clave y actualiza `last_used_at`.

    Todos los fallos devuelven el mismo mensaje: distinguir "no existe" de
    "expirada" le diría a un atacante si acertó una clave.
    """
    api_key = db.execute(
        select(APIKey).where(
            APIKey.key_hash == hash_key(raw_key),
            APIKey.active.is_(True),
            APIKey.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if api_key is None:
        raise UnauthorizedError("API key inválida o expirada.")

    if api_key.expires_at is not None and api_key.expires_at <= datetime.now(tz=UTC):
        raise UnauthorizedError("API key inválida o expirada.")

    company = db.execute(
        select(Company).where(Company.id == api_key.company_id, Company.deleted_at.is_(None))
    ).scalar_one_or_none()

    if company is None or not company.active:
        raise UnauthorizedError("API key inválida o expirada.")

    api_key.last_used_at = datetime.now(tz=UTC)
    db.commit()
    return company


def list_api_keys(db: Session, company_id: UUID) -> list[APIKey]:
    return list(
        db.execute(
            select(APIKey)
            .where(APIKey.company_id == company_id, APIKey.deleted_at.is_(None))
            .order_by(APIKey.created_at.desc())
        ).scalars()
    )


def revoke_api_key(db: Session, company_id: UUID, key_id: UUID) -> None:
    api_key = db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.company_id == company_id,
            APIKey.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if api_key is None:
        raise NotFoundError("La API key no existe o no pertenece a la empresa.")

    api_key.active = False
    api_key.soft_delete()
    db.flush()
