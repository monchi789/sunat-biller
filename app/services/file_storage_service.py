"""Almacenamiento de XML firmados, CDR y PDF en el sistema de archivos.

Layout: ``{STORAGE_ROOT}/{company_id}/{YYYY}/{MM}/{filename}``.

La escritura es atómica (archivo temporal + `rename` en el mismo directorio):
sin eso, un proceso que muere a mitad de escritura deja un XML truncado que
luego se reenvía a SUNAT como si fuera válido.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.errors import NotFoundError, StorageError


@dataclass(frozen=True, slots=True)
class StoredFile:
    """Resultado de guardar un archivo. Alimenta directamente a `DocumentFile`."""

    path: str
    filename: str
    size: int
    sha256: str
    mime_type: str


MIME_TYPES = {
    ".xml": "application/xml",
    ".zip": "application/zip",
    ".pdf": "application/pdf",
}


def _relative_dir(company_id: UUID, reference: date) -> Path:
    return Path(str(company_id)) / f"{reference:%Y}" / f"{reference:%m}"


def _resolve(relative: str | Path) -> Path:
    """Resuelve una ruta relativa dentro del storage, bloqueando el escape.

    Un `..` en el nombre permitiría leer o escribir fuera del árbol de storage.
    """
    root = Path(settings.STORAGE_ROOT).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise StorageError("Ruta de almacenamiento fuera del árbol permitido.")
    return target


def save(company_id: UUID, filename: str, content: bytes, *, reference: date) -> StoredFile:
    """Guarda un archivo y devuelve sus metadatos."""
    relative = _relative_dir(company_id, reference) / filename
    target = _resolve(relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Temporal en el mismo directorio para que `rename` sea atómico (mismo
    # sistema de archivos).
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        Path(temporary).unlink(missing_ok=True)
        raise StorageError(f"No se pudo guardar {filename}: {exc}") from exc

    return StoredFile(
        path=str(relative),
        filename=filename,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        mime_type=MIME_TYPES.get(target.suffix.lower(), "application/octet-stream"),
    )


def read(relative_path: str) -> bytes:
    """Lee un archivo previamente almacenado."""
    target = _resolve(relative_path)
    if not target.is_file():
        raise NotFoundError(f"El archivo {relative_path} no existe en el almacenamiento.")
    return target.read_bytes()


def exists(relative_path: str) -> bool:
    return _resolve(relative_path).is_file()
