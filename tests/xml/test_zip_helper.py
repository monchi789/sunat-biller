"""Empaquetado hacia SUNAT y guardas al abrir su respuesta."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.errors import SunatError
from app.xml.zip_helper import MAX_ENTRIES, extract_cdr, zip_document


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class TestEmpaquetado:
    def test_el_xml_va_en_la_raiz_con_el_mismo_nombre_base(self) -> None:
        """SUNAT rechaza el envío si el nombre del XML no coincide con el del ZIP."""
        base = "20000000001-01-F001-00000001"
        archive = zipfile.ZipFile(io.BytesIO(zip_document(base, b"<Invoice/>")))
        assert archive.namelist() == [f"{base}.xml"]

    def test_conserva_el_contenido(self) -> None:
        content = b"<Invoice>datos</Invoice>"
        archive = zipfile.ZipFile(io.BytesIO(zip_document("doc", content)))
        assert archive.read("doc.xml") == content


class TestExtraccionDelCdr:
    def test_encuentra_el_cdr_por_prefijo_r(self) -> None:
        data = make_zip({"R-20000000001-01-F001-00000001.xml": b"<ApplicationResponse/>"})
        assert extract_cdr(data) == b"<ApplicationResponse/>"

    def test_tolera_el_cdr_dentro_de_una_carpeta(self) -> None:
        """Algunos ambientes lo devuelven bajo `dummy/`."""
        data = make_zip({"dummy/R-doc.xml": b"<ApplicationResponse/>"})
        assert extract_cdr(data) == b"<ApplicationResponse/>"

    def test_acepta_un_xml_sin_prefijo_r(self) -> None:
        data = make_zip({"respuesta.xml": b"<ApplicationResponse/>"})
        assert extract_cdr(data) == b"<ApplicationResponse/>"

    def test_prefiere_el_que_lleva_prefijo_r(self) -> None:
        data = make_zip({"otro.xml": b"<Otro/>", "R-doc.xml": b"<ApplicationResponse/>"})
        assert extract_cdr(data) == b"<ApplicationResponse/>"


class TestGuardas:
    def test_zip_invalido(self) -> None:
        with pytest.raises(SunatError, match="no es un ZIP válido") as excinfo:
            extract_cdr(b"esto no es un zip")
        assert excinfo.value.retryable is False

    def test_zip_sin_xml(self) -> None:
        with pytest.raises(SunatError, match="no contiene ningún XML"):
            extract_cdr(make_zip({"lee.txt": b"hola"}))

    def test_rechaza_demasiadas_entradas(self) -> None:
        """Guarda anti zip-bomb: la respuesta legítima trae una o dos entradas."""
        data = make_zip({f"f{i}.xml": b"x" for i in range(MAX_ENTRIES + 1)})
        with pytest.raises(SunatError, match="entradas") as excinfo:
            extract_cdr(data)
        assert excinfo.value.retryable is False

    def test_rechaza_contenido_descomprimido_enorme(self) -> None:
        """Un ZIP de pocos KB puede descomprimirse a gigabytes."""
        data = make_zip({"R-bomba.xml": b"\0" * (11 * 1024 * 1024)})
        with pytest.raises(SunatError, match="descomprime"):
            extract_cdr(data)
