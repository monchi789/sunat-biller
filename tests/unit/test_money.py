"""Aritmética monetaria: redondeo comercial y serialización estable."""

from decimal import Decimal

import pytest

from app.domain.money import fmt2, fmt6, is_close, round2, round6


class TestRound2:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2.675", "2.68"),  # HALF_UP; el default bancario de Python daría 2.67
            ("2.665", "2.67"),
            ("2.664", "2.66"),
            ("0.005", "0.01"),
            ("0.004", "0.00"),
            ("100", "100.00"),
            ("-2.675", "-2.68"),
        ],
    )
    def test_redondea_half_up(self, value: str, expected: str) -> None:
        assert round2(Decimal(value)) == Decimal(expected)

    def test_no_usa_redondeo_bancario(self) -> None:
        """Si esto falla, alguien cambió el modo de redondeo y las facturas
        empezarán a descuadrar un céntimo contra el ERP del cliente."""
        assert round2(Decimal("0.125")) == Decimal("0.13")
        assert round2(Decimal("0.135")) == Decimal("0.14")


class TestRound6:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("1.0000005", "1.000001"), ("1.0000004", "1.000000"), ("33.333333333", "33.333333")],
    )
    def test_redondea_a_seis_decimales(self, value: str, expected: str) -> None:
        assert round6(Decimal(value)) == Decimal(expected)


class TestFormato:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("100", "100.00"), ("1E+2", "100.00"), ("0", "0.00"), ("118.5", "118.50")],
    )
    def test_fmt2_siempre_dos_decimales_sin_notacion_cientifica(self, value: str, expected: str) -> None:
        assert fmt2(Decimal(value)) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("1E+2", "100"), ("3", "3"), ("2.5", "2.5"), ("0.000001", "0.000001"), ("2.500000", "2.5")],
    )
    def test_fmt6_notacion_posicional(self, value: str, expected: str) -> None:
        assert fmt6(Decimal(value)) == expected

    def test_ningun_formato_emite_notacion_cientifica(self) -> None:
        """La notación científica en el XML rompe la firma y el parseo de SUNAT."""
        for exp in ("1E+2", "1E-6", "1E+10"):
            assert "E" not in fmt2(Decimal(exp)).upper()
            assert "E" not in fmt6(Decimal(exp)).upper()


class TestIsClose:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [("118.00", "118.00", True), ("118.00", "118.01", True), ("118.00", "117.99", True),
         ("118.00", "118.02", False), ("118.00", "117.98", False)],
    )
    def test_tolerancia_sunat_de_un_centimo(self, a: str, b: str, expected: bool) -> None:
        assert is_close(Decimal(a), Decimal(b)) is expected
