"""Nombres de archivo según la norma SUNAT.

El nombre no es cosmético: SUNAT rechaza el envío si el `fileName` del SOAP, el
nombre del ZIP y el del XML dentro del ZIP no coinciden exactamente.
"""

from __future__ import annotations

from datetime import date

#: Longitud del correlativo en el nombre de archivo (8 dígitos con ceros).
NUMBER_WIDTH = 8

#: Longitud del correlativo diario de resúmenes y bajas (3 dígitos).
SEQUENCE_WIDTH = 3


def document_filename(ruc: str, document_type: str, series: str, number: int) -> str:
    """`20123456789-01-F001-00000001` — facturas, boletas y notas."""
    return f"{ruc}-{document_type}-{series}-{number:0{NUMBER_WIDTH}d}"


def summary_filename(ruc: str, reference_date: date, sequence: int) -> str:
    """`20123456789-RC-20240115-001` — resumen diario de boletas."""
    return f"{ruc}-RC-{reference_date:%Y%m%d}-{sequence:0{SEQUENCE_WIDTH}d}"


def voided_filename(ruc: str, reference_date: date, sequence: int) -> str:
    """`20123456789-RA-20240115-001` — comunicación de baja."""
    return f"{ruc}-RA-{reference_date:%Y%m%d}-{sequence:0{SEQUENCE_WIDTH}d}"


def summary_identifier(reference_date: date, sequence: int) -> str:
    """`RC-20240115-001` — el `cbc:ID` del resumen, sin el RUC."""
    return f"RC-{reference_date:%Y%m%d}-{sequence:0{SEQUENCE_WIDTH}d}"


def voided_identifier(reference_date: date, sequence: int) -> str:
    """`RA-20240115-001` — el `cbc:ID` de la comunicación de baja."""
    return f"RA-{reference_date:%Y%m%d}-{sequence:0{SEQUENCE_WIDTH}d}"


def document_id(series: str, number: int) -> str:
    """`F001-00000001` — el `cbc:ID` que va dentro del XML del comprobante."""
    return f"{series}-{number:0{NUMBER_WIDTH}d}"


def zip_filename(base: str) -> str:
    return f"{base}.zip"


def xml_filename(base: str) -> str:
    return f"{base}.xml"


def cdr_filename(base: str) -> str:
    """El CDR que devuelve SUNAT viene como `R-{nombre}.xml` dentro del ZIP."""
    return f"R-{base}.xml"
