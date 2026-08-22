"""Importe en letras. Función densa en casos borde del español."""

from decimal import Decimal

import pytest

from app.domain.number_to_words import amount_to_words


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0.00", "SON CERO CON 00/100 SOLES"),
        ("0.50", "SON CERO CON 50/100 SOLES"),
        ("1.00", "SON UNO CON 00/100 SOLES"),
        ("15.00", "SON QUINCE CON 00/100 SOLES"),
        ("16.16", "SON DIECISEIS CON 16/100 SOLES"),
        ("21.00", "SON VEINTIUNO CON 00/100 SOLES"),
        ("28.00", "SON VEINTIOCHO CON 00/100 SOLES"),
        ("31.00", "SON TREINTA Y UNO CON 00/100 SOLES"),
        ("100.00", "SON CIEN CON 00/100 SOLES"),
        ("101.05", "SON CIENTO UNO CON 05/100 SOLES"),
        ("118.00", "SON CIENTO DIECIOCHO CON 00/100 SOLES"),
        ("500.00", "SON QUINIENTOS CON 00/100 SOLES"),
        ("1000.00", "SON MIL CON 00/100 SOLES"),
        ("21000.00", "SON VEINTIUN MIL CON 00/100 SOLES"),
        ("31000.00", "SON TREINTA Y UN MIL CON 00/100 SOLES"),
        ("1000000.00", "SON UN MILLON CON 00/100 SOLES"),
        ("2000000.00", "SON DOS MILLONES CON 00/100 SOLES"),
        ("999999.99", "SON NOVECIENTOS NOVENTA Y NUEVE MIL NOVECIENTOS NOVENTA Y NUEVE CON 99/100 SOLES"),
    ],
)
def test_literales_en_soles(amount: str, expected: str) -> None:
    assert amount_to_words(Decimal(amount)) == expected


class TestCasosBorde:
    def test_cien_exacto_no_lleva_ciento(self) -> None:
        assert "CIEN CON" in amount_to_words(Decimal("100.00"))
        assert "CIENTO" in amount_to_words(Decimal("101.00"))

    def test_apocope_ante_mil(self) -> None:
        """*veintiún mil*, no *veintiuno mil*."""
        assert amount_to_words(Decimal("21000.00")).startswith("SON VEINTIUN MIL")
        assert amount_to_words(Decimal("41000.00")).startswith("SON CUARENTA Y UN MIL")

    def test_apocope_ante_millon(self) -> None:
        assert amount_to_words(Decimal("21000000.00")).startswith("SON VEINTIUN MILLONES")

    def test_singular_y_plural_de_millon(self) -> None:
        assert "UN MILLON " in amount_to_words(Decimal("1000000.00"))
        assert "DOS MILLONES " in amount_to_words(Decimal("2000000.00"))


class TestMonedas:
    @pytest.mark.parametrize(
        ("currency", "word"),
        [("PEN", "SOLES"), ("USD", "DOLARES AMERICANOS"), ("EUR", "EUROS")],
    )
    def test_literal_de_moneda(self, currency: str, word: str) -> None:
        assert amount_to_words(Decimal("1.00"), currency).endswith(word)


class TestValidacion:
    def test_redondea_antes_de_convertir(self) -> None:
        assert amount_to_words(Decimal("1.005")) == "SON UNO CON 01/100 SOLES"

    def test_rechaza_negativos(self) -> None:
        with pytest.raises(ValueError, match="negativos"):
            amount_to_words(Decimal("-1.00"))
