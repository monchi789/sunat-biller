"""Almacenamiento de XML, CDR y PDF."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.errors import NotFoundError, StorageError
from app.services import file_storage_service as storage


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(storage.settings, "STORAGE_ROOT", tmp_path)
    return tmp_path


class TestGuardado:
    def test_devuelve_metadatos_completos(self) -> None:
        company = uuid4()
        content = b"<Invoice>contenido</Invoice>"
        result = storage.save(company, "doc.xml", content, reference=date(2024, 1, 15))

        assert result.filename == "doc.xml"
        assert result.size == len(content)
        assert result.sha256 == hashlib.sha256(content).hexdigest()
        assert result.mime_type == "application/xml"

    def test_layout_por_empresa_y_mes(self) -> None:
        """`{company_id}/{YYYY}/{MM}/` mantiene los directorios manejables."""
        company = uuid4()
        result = storage.save(company, "doc.xml", b"x", reference=date(2024, 3, 7))
        assert result.path == f"{company}/2024/03/doc.xml"

    @pytest.mark.parametrize(
        ("filename", "mime"),
        [("a.xml", "application/xml"), ("a.pdf", "application/pdf"),
         ("a.zip", "application/zip"), ("a.bin", "application/octet-stream")],
    )
    def test_mime_por_extension(self, filename: str, mime: str) -> None:
        result = storage.save(uuid4(), filename, b"x", reference=date(2024, 1, 1))
        assert result.mime_type == mime

    def test_sobrescribir_reemplaza_completamente(self) -> None:
        company = uuid4()
        storage.save(company, "doc.xml", b"contenido largo original", reference=date(2024, 1, 1))
        result = storage.save(company, "doc.xml", b"corto", reference=date(2024, 1, 1))
        assert storage.read(result.path) == b"corto"

    def test_no_deja_archivos_temporales(self, storage_root: Path) -> None:
        """La escritura es atómica vía temporal + rename; el temporal no queda."""
        storage.save(uuid4(), "doc.xml", b"x", reference=date(2024, 1, 1))
        assert not list(storage_root.rglob("*.tmp"))


class TestLectura:
    def test_lee_lo_guardado(self) -> None:
        result = storage.save(uuid4(), "doc.xml", b"<Invoice/>", reference=date(2024, 1, 1))
        assert storage.read(result.path) == b"<Invoice/>"

    def test_archivo_inexistente(self) -> None:
        with pytest.raises(NotFoundError):
            storage.read("nope/2024/01/doc.xml")

    def test_exists(self) -> None:
        result = storage.save(uuid4(), "doc.xml", b"x", reference=date(2024, 1, 1))
        assert storage.exists(result.path)
        assert not storage.exists("otro/2024/01/doc.xml")


class TestSeguridadDeRutas:
    @pytest.mark.parametrize(
        "path",
        ["../../../etc/passwd", "../fuera.xml", "a/../../../../tmp/x", "/etc/passwd"],
    )
    def test_bloquea_escape_del_arbol(self, path: str) -> None:
        """Un `..` en la ruta permitiría leer o pisar archivos fuera del storage."""
        with pytest.raises(StorageError, match="fuera del árbol"):
            storage.read(path)
