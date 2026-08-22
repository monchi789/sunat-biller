"""Cifrado de secretos en reposo: credenciales SOL y contraseñas de certificados.

Usa una `ENCRYPTION_KEY` dedicada en lugar de derivarla de `SECRET_KEY`. La
receta de la guía (`SECRET_KEY[:32].ljust(32)`) no es una función de derivación:
con un `SECRET_KEY` corto o poco entrópico produce una llave débil, y además
acopla la rotación de la clave de firma con la de cifrado, que tienen ciclos de
vida distintos.

Rotar `ENCRYPTION_KEY` invalida todo lo ya cifrado. Está documentado en
`docs/DESPLIEGUE.md`.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import DomainError


class DecryptionError(DomainError):
    error_code = "DECRYPTION_FAILED"
    status_code = 500


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise DomainError(
            "ENCRYPTION_KEY no está configurada. Genera una con "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"`.'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise DomainError(
            "ENCRYPTION_KEY no es una clave Fernet válida (32 bytes en base64 urlsafe)."
        ) from exc


def encrypt(plaintext: str) -> str:
    """Cifra un secreto. El resultado es texto seguro para almacenar."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Descifra un secreto previamente cifrado con `encrypt`."""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "No se pudo descifrar el secreto. ¿Se rotó ENCRYPTION_KEY sin "
            "reingresar las credenciales?"
        ) from exc


def reset_cache() -> None:
    """Limpia la llave cacheada. Solo para tests que cambian la configuración."""
    _fernet.cache_clear()
