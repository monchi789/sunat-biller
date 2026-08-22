"""Empaquetado ZIP hacia SUNAT y desempaquetado del CDR de vuelta.

SUNAT exige que el XML vaya en la **raíz** del ZIP con el mismo nombre base que
el ZIP y que el `fileName` del envelope SOAP. Cualquier discrepancia se responde
con un fault genérico difícil de diagnosticar.
"""

from __future__ import annotations

import io
import zipfile

from app.core.errors import SunatError

#: Guardas anti zip-bomb al abrir la respuesta de SUNAT.
MAX_ENTRIES = 4
MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024


def zip_document(filename_base: str, xml_content: bytes) -> bytes:
    """Empaqueta el XML firmado. `filename_base` va **sin** extensión."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{filename_base}.xml", xml_content)
    return buffer.getvalue()


def extract_cdr(zip_content: bytes) -> bytes:
    """Extrae el XML del CDR del ZIP que devuelve SUNAT.

    El CDR viene como `R-{nombre}.xml`, a veces dentro de una carpeta `dummy/`.
    Se busca por sufijo en lugar de por nombre exacto para tolerar ambas formas.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_content))
    except zipfile.BadZipFile as exc:
        raise SunatError("La respuesta de SUNAT no es un ZIP válido.", retryable=False) from exc

    with archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]

        if len(entries) > MAX_ENTRIES:
            raise SunatError(
                f"El ZIP del CDR tiene {len(entries)} entradas; el máximo aceptado es {MAX_ENTRIES}.",
                retryable=False,
            )

        total = sum(info.file_size for info in entries)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise SunatError(
                f"El ZIP del CDR se descomprime a {total} bytes, por encima del límite.",
                retryable=False,
            )

        for info in entries:
            name = info.filename.rsplit("/", 1)[-1]
            if name.upper().startswith("R-") and name.lower().endswith(".xml"):
                return archive.read(info)

        # Algunos entornos devuelven el CDR sin el prefijo R-.
        for info in entries:
            if info.filename.lower().endswith(".xml"):
                return archive.read(info)

    raise SunatError("El ZIP de respuesta no contiene ningún XML de CDR.", retryable=False)
