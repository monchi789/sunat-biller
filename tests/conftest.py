"""Fixtures compartidas."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

IGV_RATE = Decimal("0.18")
ICBPER_RATE = Decimal("0.50")


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    """Clave RSA-2048 generada una sola vez por sesión (generar cuesta ~100 ms)."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def certificate(rsa_key: rsa.RSAPrivateKey) -> x509.Certificate:
    """Certificado autofirmado en memoria.

    **Nunca** se versiona un `.pfx` real en el repositorio. El ambiente BETA de
    SUNAT acepta certificados autofirmados, así que esto basta incluso para E2E.
    """
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "PE"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EMPRESA DE PRUEBA SAC"),
        x509.NameAttribute(NameOID.COMMON_NAME, "20000000001"),
    ])
    now = datetime.datetime.now(datetime.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(rsa_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(rsa_key, hashes.SHA256())
    )
