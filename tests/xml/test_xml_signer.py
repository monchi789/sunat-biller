"""Firma XMLDSig: estructura exigida por SUNAT, validez criptográfica y tamper.

Estos tests fijan cada parámetro de `app/xml/xml_signer.py`. Si alguno se cambia
sin querer, aquí se ve antes de que SUNAT lo rechace en producción.
"""

from __future__ import annotations

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from lxml import etree

from app.core.errors import SigningError
from app.xml.context import DocumentContext
from app.xml.namespaces import DS, cac, cbc, ds, ext
from app.xml.ubl_invoice import build_invoice
from app.xml.xml_signer import (
    DEFAULT_SIGNATURE_ID,
    extract_digest_value,
    sign_xml,
    verify_signature,
)
from tests.conftest import IGV_RATE


@pytest.fixture
def signed_invoice(
    simple_invoice: DocumentContext, rsa_key: rsa.RSAPrivateKey, certificate: x509.Certificate
) -> bytes:
    root = build_invoice(simple_invoice, igv_rate=IGV_RATE)
    return sign_xml(root, private_key=rsa_key, certificate=certificate)


@pytest.fixture
def signature_node(signed_invoice: bytes) -> etree._Element:
    node = etree.fromstring(signed_invoice).find(f".//{ext('ExtensionContent')}/{ds('Signature')}")
    assert node is not None
    return node


class TestUbicacionDeLaFirma:
    def test_la_firma_queda_dentro_de_extension_content(self, signature_node: etree._Element) -> None:
        """Fuera de `ext:ExtensionContent` SUNAT rechaza el comprobante."""
        assert signature_node is not None

    def test_no_hay_firma_suelta_en_la_raiz(self, signed_invoice: bytes) -> None:
        root = etree.fromstring(signed_invoice)
        assert all(child.tag != ds("Signature") for child in root)

    def test_usa_el_prefijo_ds(self, signed_invoice: bytes) -> None:
        """Con prefijo autogenerado (`ns0:`) algunos validadores de SUNAT fallan."""
        assert b"<ds:Signature" in signed_invoice
        assert b"ns0:Signature" not in signed_invoice

    def test_hay_exactamente_una_firma(self, signed_invoice: bytes) -> None:
        assert len(etree.fromstring(signed_invoice).findall(f".//{ds('Signature')}")) == 1


class TestParametrosDeFirma:
    def test_reference_uri_vacia(self, signature_node: etree._Element) -> None:
        references = signature_node.findall(f".//{ds('Reference')}")
        assert len(references) == 1
        assert references[0].get("URI") == ""

    def test_una_sola_transform_enveloped(self, signature_node: etree._Element) -> None:
        """SUNAT espera únicamente `enveloped-signature`."""
        transforms = signature_node.findall(f".//{ds('Transform')}")
        assert len(transforms) == 1
        assert transforms[0].get("Algorithm") == f"{DS}enveloped-signature"

    def test_canonicalizacion_inclusiva(self, signature_node: etree._Element) -> None:
        """Inclusiva C14N 1.0: al omitir la transform, es el default de XMLDSig.

        Con exc-c14n el XML se genera igual pero **no verifica**.
        """
        method = signature_node.find(f".//{ds('CanonicalizationMethod')}")
        assert method.get("Algorithm") == "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"

    def test_rsa_sha256(self, signature_node: etree._Element) -> None:
        method = signature_node.find(f".//{ds('SignatureMethod')}")
        assert method.get("Algorithm") == "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"

    def test_digest_sha256(self, signature_node: etree._Element) -> None:
        method = signature_node.find(f".//{ds('DigestMethod')}")
        assert method.get("Algorithm") == "http://www.w3.org/2001/04/xmlenc#sha256"


class TestKeyInfo:
    def test_lleva_el_certificado_x509(
        self, signature_node: etree._Element, certificate: x509.Certificate
    ) -> None:
        certificates = signature_node.findall(f".//{ds('X509Certificate')}")
        assert len(certificates) == 1
        der = certificate.public_bytes(serialization.Encoding.DER)
        import base64
        assert base64.b64decode(certificates[0].text) == der

    def test_no_expone_la_clave_publica_cruda(self, signature_node: etree._Element) -> None:
        """`RSAKeyValue` es innecesario y amplía la superficie de rechazo por XSD."""
        assert signature_node.find(f".//{ds('KeyValue')}") is None


class TestIdentificadorDeFirma:
    def test_el_id_coincide_con_cac_signature(self, signed_invoice: bytes) -> None:
        root = etree.fromstring(signed_invoice)
        signature = root.find(f".//{ext('ExtensionContent')}/{ds('Signature')}")
        declared = root.find(f"./{cac('Signature')}/{cbc('ID')}")
        assert signature.get("Id") == DEFAULT_SIGNATURE_ID == declared.text

    def test_el_placeholder_desaparece(self, signed_invoice: bytes) -> None:
        assert b'Id="placeholder"' not in signed_invoice


class TestValidezCriptografica:
    def test_la_firma_verifica(self, signed_invoice: bytes, certificate: x509.Certificate) -> None:
        verify_signature(signed_invoice, certificate)

    def test_un_xml_manipulado_no_verifica(
        self, signed_invoice: bytes, certificate: x509.Certificate
    ) -> None:
        """El test que demuestra que el digest cubre de verdad el contenido.

        Es el fallo silencioso nº1 de los firmadores caseros: firman algo que no
        es el documento, y cualquiera puede alterar el importe sin romper nada.
        """
        tampered = signed_invoice.replace(b">118.00<", b">999.00<")
        assert tampered != signed_invoice
        with pytest.raises(SigningError, match="no es válida"):
            verify_signature(tampered, certificate)

    def test_otro_certificado_no_verifica(
        self, signed_invoice: bytes, rsa_key: rsa.RSAPrivateKey
    ) -> None:
        import datetime

        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID

        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IMPOSTOR")])
        now = datetime.datetime.now(datetime.UTC)
        other = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(other_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(other_key, hashes.SHA256())
        )
        with pytest.raises(SigningError):
            verify_signature(signed_invoice, other)


class TestDigestValue:
    def test_es_base64_de_44_caracteres(self, signed_invoice: bytes) -> None:
        """Cabe en `ElectronicDocument.xml_hash` (VARCHAR 64) y alimenta el QR."""
        digest = extract_digest_value(signed_invoice)
        assert len(digest) == 44
        assert digest.endswith("=") or digest[-1].isalnum()

    def test_es_reproducible(
        self, simple_invoice: DocumentContext, rsa_key: rsa.RSAPrivateKey,
        certificate: x509.Certificate,
    ) -> None:
        """Mismo documento ⇒ mismo digest. Si falla, algo no es determinista."""
        first = extract_digest_value(
            sign_xml(build_invoice(simple_invoice, igv_rate=IGV_RATE),
                     private_key=rsa_key, certificate=certificate)
        )
        second = extract_digest_value(
            sign_xml(build_invoice(simple_invoice, igv_rate=IGV_RATE),
                     private_key=rsa_key, certificate=certificate)
        )
        assert first == second
