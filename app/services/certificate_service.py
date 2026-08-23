"""Certificados digitales: carga, validación y uso para firmar (RF-02).

Dos cuidados que no son obvios:

**PFX con cifrado antiguo.** Muchos `.pfx` emitidos en Perú usan RC2-40-CBC o
3DES con MAC SHA-1. OpenSSL 3 movió esos algoritmos al *legacy provider*, así
que `pkcs12.load_key_and_certificates` falla con "Invalid password or PKCS12
data" **aunque la contraseña sea correcta** — un mensaje que hace perder horas.
Al subirlo se reintenta por la vía legacy y se **re-serializa con AES-256**, una
sola vez; a partir de ahí el archivo almacenado se abre siempre por la vía normal.

**Caché en memoria.** Descifrar la contraseña y derivar la clave PKCS#12 en cada
emisión es latencia regalada contra el presupuesto de menos de 3 s por factura.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509 import Certificate
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import CertificateError, NotFoundError
from app.core.logging import get_logger
from app.models.certificate import DigitalCertificate
from app.services import crypto_service

logger = get_logger(__name__)

#: SUNAT no acepta claves menores; además, por debajo de esto la firma no es seria.
MIN_KEY_SIZE = 2048

ALLOWED_SUFFIXES = {".pfx", ".p12"}


@dataclass(frozen=True, slots=True)
class LoadedCertificate:
    private_key: rsa.RSAPrivateKey
    certificate: Certificate


#: Caché por `(certificate_id, updated_at)`. Se invalida sola al cambiar el
#: certificado activo, porque la clave del caché incluye el identificador.
_CACHE: dict[UUID, LoadedCertificate] = {}


def _parse_pkcs12(content: bytes, password: str) -> tuple[rsa.RSAPrivateKey, Certificate]:
    """Abre el PFX, con reintento por la vía legacy de OpenSSL."""
    try:
        private_key, certificate, _ = pkcs12.load_key_and_certificates(
            content, password.encode("utf-8")
        )
    except (ValueError, TypeError):
        private_key, certificate = _parse_pkcs12_legacy(content, password)
    else:
        if private_key is None or certificate is None:
            raise CertificateError("El archivo no contiene clave privada y certificado.")

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise CertificateError("SUNAT exige una clave RSA; el certificado usa otro algoritmo.")
    if private_key.key_size < MIN_KEY_SIZE:
        raise CertificateError(
            f"La clave es de {private_key.key_size} bits; el mínimo aceptado es {MIN_KEY_SIZE}."
        )

    return private_key, certificate


def _parse_pkcs12_legacy(content: bytes, password: str) -> tuple[rsa.RSAPrivateKey, Certificate]:
    """Convierte un PFX con cifrado antiguo usando `openssl -legacy`."""
    with tempfile.TemporaryDirectory() as workdir:
        source = Path(workdir) / "cert.pfx"
        source.write_bytes(content)

        try:
            result = subprocess.run(
                [
                    "openssl", "pkcs12", "-legacy", "-in", str(source),
                    "-nodes", "-passin", f"pass:{password}",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise CertificateError(
                "No se pudo abrir el certificado. Si usa cifrado antiguo (RC2/3DES) "
                "se necesita el binario `openssl` disponible en el sistema."
            ) from exc

        if result.returncode != 0:
            raise CertificateError(
                "No se pudo abrir el certificado: contraseña incorrecta o archivo inválido."
            )

        pem = result.stdout

    try:
        private_key = serialization.load_pem_private_key(pem, password=None)
        certificate = _first_certificate(pem)
    except ValueError as exc:
        raise CertificateError("El certificado convertido no es legible.") from exc

    return private_key, certificate  # type: ignore[return-value]


def _first_certificate(pem: bytes) -> Certificate:
    from cryptography.x509 import load_pem_x509_certificate

    marker = b"-----BEGIN CERTIFICATE-----"
    start = pem.find(marker)
    if start == -1:
        raise CertificateError("El archivo no contiene ningún certificado X.509.")
    end = pem.find(b"-----END CERTIFICATE-----", start) + len(b"-----END CERTIFICATE-----")
    return load_pem_x509_certificate(pem[start:end])


def _normalize(private_key: rsa.RSAPrivateKey, certificate: Certificate, password: str) -> bytes:
    """Re-serializa el PFX con AES-256, para no depender del cifrado de origen."""
    return pkcs12.serialize_key_and_certificates(
        name=b"sunat-biller",
        key=private_key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )


def upload_certificate(
    db: Session, company_id: UUID, filename: str, content: bytes, password: str
) -> DigitalCertificate:
    """Valida el PFX, lo normaliza y lo deja como único certificado activo."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise CertificateError(
            f"Extensión no admitida: {suffix or '(ninguna)'}. Se espera .pfx o .p12."
        )

    max_bytes = settings.MAX_CERTIFICATE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise CertificateError(
            f"El certificado pesa más de {settings.MAX_CERTIFICATE_SIZE_MB} MB."
        )
    if not content:
        raise CertificateError("El archivo del certificado está vacío.")

    private_key, certificate = _parse_pkcs12(content, password)

    valid_from = certificate.not_valid_before_utc
    valid_until = certificate.not_valid_after_utc
    now = datetime.now(tz=UTC)
    if valid_until <= now:
        raise CertificateError(
            f"El certificado venció el {valid_until:%Y-%m-%d}. SUNAT rechazará las firmas.",
            {"valid_until": valid_until.isoformat()},
        )

    # Un solo certificado activo por empresa: lo garantiza un índice único
    # parcial, así que hay que desactivar el anterior en esta misma transacción.
    for previous in db.execute(
        select(DigitalCertificate).where(
            DigitalCertificate.company_id == company_id,
            DigitalCertificate.active.is_(True),
            DigitalCertificate.deleted_at.is_(None),
        )
    ).scalars():
        previous.active = False
        _CACHE.pop(previous.id, None)
    db.flush()

    root = Path(settings.CERTIFICATE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    stored_name = f"{company_id}-{uuid4().hex}.pfx"
    stored_path = root / stored_name
    stored_path.write_bytes(_normalize(private_key, certificate, password))
    stored_path.chmod(0o600)

    record = DigitalCertificate(
        company_id=company_id,
        certificate_path=str(stored_path),
        password_secret=crypto_service.encrypt(password),
        serial_number=str(certificate.serial_number),
        valid_from=valid_from,
        valid_until=valid_until,
        active=True,
    )
    db.add(record)
    db.flush()

    logger.info(
        "certificado cargado",
        extra={
            "company_id": str(company_id),
            "serial_number": record.serial_number,
            "valid_until": valid_until.isoformat(),
        },
    )
    return record


def get_active_certificate(db: Session, company_id: UUID) -> DigitalCertificate:
    certificate = db.execute(
        select(DigitalCertificate).where(
            DigitalCertificate.company_id == company_id,
            DigitalCertificate.active.is_(True),
            DigitalCertificate.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if certificate is None:
        raise NotFoundError(
            "La empresa no tiene un certificado digital activo. "
            "Súbelo en POST /companies/{id}/certificates antes de emitir."
        )
    return certificate


def load(certificate: DigitalCertificate) -> LoadedCertificate:
    """Devuelve la clave y el certificado listos para firmar, con caché."""
    cached = _CACHE.get(certificate.id)
    if cached is not None:
        return cached

    path = Path(certificate.certificate_path)
    if not path.is_file():
        raise CertificateError(
            "El archivo del certificado no está en el almacenamiento. "
            "¿Se perdió el volumen de datos?",
            {"certificate_id": str(certificate.id)},
        )

    password = crypto_service.decrypt(certificate.password_secret)
    private_key, x509 = _parse_pkcs12(path.read_bytes(), password)

    loaded = LoadedCertificate(private_key=private_key, certificate=x509)
    _CACHE[certificate.id] = loaded
    return loaded


def list_certificates(db: Session, company_id: UUID) -> list[DigitalCertificate]:
    return list(
        db.execute(
            select(DigitalCertificate)
            .where(
                DigitalCertificate.company_id == company_id,
                DigitalCertificate.deleted_at.is_(None),
            )
            .order_by(DigitalCertificate.created_at.desc())
        ).scalars()
    )


def delete_certificate(db: Session, company_id: UUID, certificate_id: UUID) -> None:
    certificate = db.execute(
        select(DigitalCertificate).where(
            DigitalCertificate.id == certificate_id,
            DigitalCertificate.company_id == company_id,
            DigitalCertificate.deleted_at.is_(None),
        )
    ).scalar_one_or_none()

    if certificate is None:
        raise NotFoundError("El certificado no existe o no pertenece a la empresa.")

    certificate.active = False
    certificate.soft_delete()
    _CACHE.pop(certificate.id, None)
    db.flush()


def clear_cache() -> None:
    """Vacía la caché de certificados. Para tests."""
    _CACHE.clear()
