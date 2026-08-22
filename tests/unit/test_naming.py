"""Nombres de archivo SUNAT. Si no coinciden exactamente, SUNAT rechaza el envío."""

from datetime import date

import pytest

from app.domain.naming import (
    cdr_filename,
    document_filename,
    document_id,
    summary_filename,
    summary_identifier,
    voided_filename,
    voided_identifier,
    xml_filename,
    zip_filename,
)

RUC = "20123456789"


class TestComprobantes:
    def test_nombre_de_factura(self) -> None:
        assert document_filename(RUC, "01", "F001", 1) == "20123456789-01-F001-00000001"

    def test_correlativo_a_ocho_digitos(self) -> None:
        assert document_filename(RUC, "03", "B001", 99_999_999).endswith("-99999999")

    @pytest.mark.parametrize("doc_type", ["01", "03", "07", "08"])
    def test_todos_los_tipos(self, doc_type: str) -> None:
        assert document_filename(RUC, doc_type, "F001", 5) == f"{RUC}-{doc_type}-F001-00000005"

    def test_id_interno_del_xml_no_lleva_ruc(self) -> None:
        assert document_id("F001", 42) == "F001-00000042"


class TestResumenesYBajas:
    def test_nombre_de_resumen_diario(self) -> None:
        assert summary_filename(RUC, date(2024, 1, 15), 1) == "20123456789-RC-20240115-001"

    def test_nombre_de_comunicacion_de_baja(self) -> None:
        assert voided_filename(RUC, date(2024, 1, 15), 1) == "20123456789-RA-20240115-001"

    def test_identificadores_sin_ruc(self) -> None:
        assert summary_identifier(date(2024, 1, 15), 3) == "RC-20240115-003"
        assert voided_identifier(date(2024, 12, 31), 12) == "RA-20241231-012"


class TestExtensiones:
    def test_zip_y_xml_comparten_base(self) -> None:
        base = document_filename(RUC, "01", "F001", 1)
        assert zip_filename(base) == f"{base}.zip"
        assert xml_filename(base) == f"{base}.xml"

    def test_cdr_lleva_prefijo_r(self) -> None:
        base = document_filename(RUC, "01", "F001", 1)
        assert cdr_filename(base) == f"R-{base}.xml"
