"""Cifrado de secretos en reposo (RNF-01.3)."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.errors import DomainError
from app.services import crypto_service
from app.services.crypto_service import DecryptionError


@pytest.fixture(autouse=True)
def _clean_key_cache() -> None:
    crypto_service.reset_cache()


class TestCicloDeCifrado:
    @pytest.mark.parametrize(
        "secret",
        ["moddatos", "clave con espacios", "ñandú-ácido", "a" * 500, "sím&bolos<>\"'", "1234"],
    )
    def test_ida_y_vuelta(self, secret: str) -> None:
        assert crypto_service.decrypt(crypto_service.encrypt(secret)) == secret

    def test_el_cifrado_no_deja_ver_el_secreto(self) -> None:
        assert "moddatos" not in crypto_service.encrypt("moddatos")

    def test_dos_cifrados_del_mismo_secreto_difieren(self) -> None:
        """Fernet incluye IV y timestamp: sin esto, dos claves SOL iguales
        serían distinguibles por su texto cifrado."""
        assert crypto_service.encrypt("misma") != crypto_service.encrypt("misma")


class TestErrores:
    def test_texto_manipulado_no_descifra(self) -> None:
        token = crypto_service.encrypt("secreto")
        with pytest.raises(DecryptionError, match="ENCRYPTION_KEY"):
            crypto_service.decrypt(token[:-4] + "AAAA")

    def test_texto_de_otra_llave_no_descifra(self) -> None:
        """Es el escenario de rotar ENCRYPTION_KEY sin reingresar credenciales."""
        foreign = Fernet(Fernet.generate_key()).encrypt(b"secreto").decode()
        with pytest.raises(DecryptionError):
            crypto_service.decrypt(foreign)

    def test_sin_llave_configurada_falla_claro(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(crypto_service.settings, "ENCRYPTION_KEY", "")
        crypto_service.reset_cache()
        with pytest.raises(DomainError, match="ENCRYPTION_KEY no está configurada"):
            crypto_service.encrypt("x")

    def test_llave_invalida_falla_claro(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(crypto_service.settings, "ENCRYPTION_KEY", "esto-no-es-fernet")
        crypto_service.reset_cache()
        with pytest.raises(DomainError, match="no es una clave Fernet válida"):
            crypto_service.encrypt("x")
