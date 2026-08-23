"""Genera un certificado digital de prueba autofirmado.

El ambiente BETA de SUNAT **no valida el certificado** —su propia documentación
dice que no hace falta tener uno registrado—, así que uno autofirmado recorre el
flujo completo de emisión. Para producción hace falta uno emitido por una entidad
de certificación acreditada y registrado en SUNAT.

    python -m app.tools.test_certificate --ruc 10123456789 --name "MI NEGOCIO"

El archivo generado **no debe versionarse**: el `.gitignore` ya excluye `*.pfx`.
"""

from __future__ import annotations

import argparse
import datetime
import re
import secrets
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

KEY_SIZE = 2048
DEFAULT_DAYS = 730
RUC_PATTERN = re.compile(r"^\d{11}$")


def build_certificate(
    ruc: str, name: str, *, days: int = DEFAULT_DAYS
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "PE"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, name),
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            # SUNAT identifica al firmante por el RUC en el serialNumber.
            x509.NameAttribute(NameOID.SERIAL_NUMBER, ruc),
        ]
    )

    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def write_pfx(
    key: rsa.RSAPrivateKey, certificate: x509.Certificate, password: str, destination: Path
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        pkcs12.serialize_key_and_certificates(
            name=b"sunat-biller-test",
            key=key,
            cert=certificate,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
        )
    )
    destination.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera un certificado .pfx autofirmado para probar contra SUNAT BETA.",
    )
    parser.add_argument("--ruc", required=True, help="RUC del emisor (11 dígitos).")
    parser.add_argument("--name", required=True, help="Razón social o nombre del emisor.")
    parser.add_argument(
        "--password", default=None, help="Contraseña del .pfx. Si se omite, se genera una."
    )
    parser.add_argument(
        "--out", default=None, help="Ruta de salida. Por defecto `data/certificates/test-{RUC}.pfx`."
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Días de vigencia.")
    args = parser.parse_args()

    if not RUC_PATTERN.match(args.ruc):
        parser.error("El RUC debe tener exactamente 11 dígitos.")

    password = args.password or secrets.token_urlsafe(12)
    destination = Path(args.out) if args.out else Path(f"data/certificates/test-{args.ruc}.pfx")

    key, certificate = build_certificate(args.ruc, args.name, days=args.days)
    write_pfx(key, certificate, password, destination)

    print("Certificado de prueba generado.\n")
    print(f"  Archivo     : {destination}")
    print(f"  Contraseña  : {password}")
    print(f"  RUC         : {args.ruc}")
    print(f"  Titular     : {args.name}")
    print(f"  Vigencia    : hasta {certificate.not_valid_after_utc:%Y-%m-%d}")
    print(f"  Nº de serie : {certificate.serial_number}")
    print("\nSúbelo con:")
    print(
        f'  curl -X POST "$API/companies/$COMPANY_ID/certificates" \\\n'
        f'    -H "X-Admin-Token: $ADMIN_TOKEN" \\\n'
        f'    -F "file=@{destination}" \\\n'
        f'    -F "password={password}"'
    )
    print("\nSolo sirve para el ambiente BETA. En producción hace falta un")
    print("certificado de una entidad acreditada, registrado en SUNAT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
