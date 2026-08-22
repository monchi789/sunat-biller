"""Firma XMLDSig enveloped dentro de `ext:ExtensionContent`, como exige SUNAT.

Los parámetros de esta implementación están **verificados empíricamente**: firman,
verifican criptográficamente, y rechazan un XML manipulado. Cambiar cualquiera de
ellos sin volver a correr `tests/xml/test_xml_signer.py` es arriesgado.

Puntos que costaron encontrarse y no deben tocarse a la ligera:

* **Canonicalización inclusiva C14N 1.0**, no exclusive-c14n. Al omitir la
  transform de canonicalización (que SUNAT quiere omitida, para que solo aparezca
  `enveloped-signature`), el verificador asume el algoritmo por defecto de
  XMLDSig, que es el inclusivo. Con exc-c14n el XML *parece* correcto pero falla
  la verificación con `InvalidDigest`.
* **No se pasa `reference_uri`**: signxml lo transforma en `"#"` y aborta con
  `Unable to resolve reference URI`. El default ya produce `URI=""`.
* El hueco de la firma es un `<ds:Signature Id="placeholder"/>` que el *builder*
  coloca dentro de `ext:ExtensionContent`; signxml lo rellena in situ y lo excluye
  del digest. Así no hay que mover el nodo tras firmar, que es donde se invalidan
  las firmas caseras.
"""

from __future__ import annotations

from typing import Final

from cryptography.hazmat.primitives import serialization
from cryptography.x509 import Certificate
from lxml import etree
from signxml import XMLSigner, XMLVerifier, methods
from signxml.algorithms import CanonicalizationMethod, DigestAlgorithm, SignatureMethod

from app.core.errors import SigningError
from app.xml.namespaces import DS, ds, ext

#: Valor del atributo que marca el hueco donde irá la firma. Lo define signxml.
PLACEHOLDER_ID: Final = "placeholder"

#: `Id` que se fija en la firma ya generada. Debe coincidir con `cac:Signature/cbc:ID`.
DEFAULT_SIGNATURE_ID: Final = "SignatureSP"

_SIGNER: Final = XMLSigner(
    method=methods.enveloped,
    signature_algorithm=SignatureMethod.RSA_SHA256,
    digest_algorithm=DigestAlgorithm.SHA256,
    c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
)


def build_signature_placeholder(parent: etree._Element) -> etree._Element:
    """Inserta el hueco de la firma. Lo llama cada builder de documento."""
    return etree.SubElement(parent, ds("Signature"), Id=PLACEHOLDER_ID)


def sign_xml(
    root: etree._Element,
    *,
    private_key: object,
    certificate: Certificate,
    signature_id: str = DEFAULT_SIGNATURE_ID,
) -> bytes:
    """Firma el documento y devuelve los bytes UTF-8 listos para empaquetar.

    :param root: árbol del documento, con el placeholder ya insertado dentro de
        `ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent`.
    :param private_key: clave privada RSA extraída del PFX.
    :param certificate: certificado X.509 del emisor (solo el leaf; SUNAT no
        valida la cadena).
    """
    key_pem = private_key.private_bytes(  # type: ignore[attr-defined]
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

    try:
        signed = _SIGNER.sign(
            root,
            key=key_pem,
            cert=[cert_pem],
            always_add_key_value=False,
            exclude_c14n_transform_element=True,
        )
    except Exception as exc:  # pragma: no cover - depende de la librería
        raise SigningError(f"No se pudo firmar el XML: {exc}") from exc

    signature = signed.find(f".//{ext('ExtensionContent')}/{ds('Signature')}")
    if signature is None:
        raise SigningError(
            "La firma no quedó dentro de ext:ExtensionContent. "
            "¿El builder olvidó insertar el placeholder?"
        )

    # Seguro tras firmar: la transform `enveloped-signature` elimina todo el
    # subárbol ds:Signature, así que su atributo Id nunca entró en el digest.
    signature.set("Id", signature_id)

    return etree.tostring(signed, xml_declaration=True, encoding="UTF-8", standalone=False)


def extract_digest_value(signed_xml: bytes) -> str:
    """Devuelve el `ds:DigestValue` en base64.

    Es el valor que se persiste en `ElectronicDocument.xml_hash` y el que exige
    el código QR de la representación impresa. 44 caracteres.
    """
    document = etree.fromstring(signed_xml)
    digest = document.findtext(f".//{ds('DigestValue')}")
    if not digest:
        raise SigningError("El XML firmado no contiene ds:DigestValue.")
    return digest.strip()


def verify_signature(signed_xml: bytes, certificate: Certificate) -> None:
    """Verifica la firma. Lanza si no es válida. Se usa en tests y diagnóstico."""
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    try:
        XMLVerifier().verify(signed_xml, x509_cert=cert_pem, expect_references=1)
    except Exception as exc:
        raise SigningError(f"La firma del XML no es válida: {exc}") from exc


__all__ = [
    "DEFAULT_SIGNATURE_ID",
    "DS",
    "PLACEHOLDER_ID",
    "build_signature_placeholder",
    "extract_digest_value",
    "sign_xml",
    "verify_signature",
]
