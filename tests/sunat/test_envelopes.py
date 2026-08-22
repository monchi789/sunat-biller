"""Construcción de los envelopes SOAP."""

from __future__ import annotations

import base64

import pytest
from lxml import etree

from app.sunat import envelopes


class TestSeguridad:
    def test_username_es_ruc_mas_usuario_sin_separador(self) -> None:
        envelope = envelopes.build_send_bill("20000000001", "MODDATOS", "x", "f.zip", b"z")
        assert b"<wsse:Username>20000000001MODDATOS</wsse:Username>" in envelope

    @pytest.mark.parametrize("password", ["mi&clave", "a<b>c", 'com"illas', "j&j<k>"])
    def test_escapa_caracteres_peligrosos_en_la_clave(self, password: str) -> None:
        """Sin escapar, el envelope sale malformado y SUNAT devuelve un fault ilegible."""
        envelope = envelopes.build_send_bill("20000000001", "USER", password, "f.zip", b"z")
        etree.fromstring(envelope)  # no debe lanzar
        assert password.encode() not in envelope or "&" not in password

    def test_escapa_tambien_el_usuario(self) -> None:
        envelope = envelopes.build_send_bill("20000000001", "US&ER", "x", "f.zip", b"z")
        etree.fromstring(envelope)
        assert b"US&amp;ER" in envelope

    def test_password_type_es_texto_plano(self) -> None:
        envelope = envelopes.build_send_bill("20000000001", "U", "p", "f.zip", b"z")
        assert b"#PasswordText" in envelope


class TestSendBill:
    def test_contenido_va_en_base64(self) -> None:
        envelope = envelopes.build_send_bill("20000000001", "U", "p", "f.zip", b"CONTENIDO")
        root = etree.fromstring(envelope)
        content = root.xpath("//*[local-name()='contentFile']")[0].text
        assert base64.b64decode(content) == b"CONTENIDO"

    def test_lleva_el_nombre_del_archivo(self) -> None:
        envelope = envelopes.build_send_bill("20000000001", "U", "p", "doc.zip", b"z")
        root = etree.fromstring(envelope)
        assert root.xpath("//*[local-name()='fileName']")[0].text == "doc.zip"


class TestOtrasOperaciones:
    def test_send_summary(self) -> None:
        envelope = envelopes.build_send_summary("20000000001", "U", "p", "rc.zip", b"z")
        assert etree.fromstring(envelope).xpath("//*[local-name()='sendSummary']")

    def test_get_status(self) -> None:
        envelope = envelopes.build_get_status("20000000001", "U", "p", "TICKET123")
        root = etree.fromstring(envelope)
        assert root.xpath("//*[local-name()='ticket']")[0].text == "TICKET123"

    def test_get_status_cdr(self) -> None:
        envelope = envelopes.build_get_status_cdr("20000000001", "U", "p", "01", "F001", 42)
        root = etree.fromstring(envelope)
        assert root.xpath("//*[local-name()='numeroComprobante']")[0].text == "42"
        assert root.xpath("//*[local-name()='serieComprobante']")[0].text == "F001"


class TestDespacho:
    def test_operacion_desconocida_falla(self) -> None:
        with pytest.raises(ValueError, match="desconocida"):
            envelopes.build_envelope("sendNukes", "20000000001", "U", "p", "f", b"z")
