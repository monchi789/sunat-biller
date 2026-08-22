"""Motor tributario: la batería más densa del proyecto.

Cada rechazo de SUNAT por descuadre numérico debería poder reproducirse aquí.
"""

from decimal import Decimal

import pytest

from app.domain.tax_engine import (
    DocumentTotals,
    ItemInput,
    TaxCalculationError,
    calculate_item,
    calculate_totals,
)

IGV = Decimal("0.18")
ICBPER = Decimal("0.50")


def totals(*items: ItemInput) -> DocumentTotals:
    return calculate_totals(items, igv_rate=IGV, icbper_rate=ICBPER)


def item(**kwargs: object) -> ItemInput:
    defaults: dict[str, object] = {"quantity": Decimal(1), "tax_affectation": "10"}
    return ItemInput(**{**defaults, **kwargs})  # type: ignore[arg-type]


class TestFacturaGravadaSimple:
    def test_cien_mas_igv(self) -> None:
        t = totals(item(unit_value=Decimal("100.00")))
        assert t.subtotal == Decimal("100.00")
        assert t.taxable_total == Decimal("100.00")
        assert t.igv_total == Decimal("18.00")
        assert t.total == Decimal("118.00")

    def test_cantidad_multiple(self) -> None:
        t = totals(item(quantity=Decimal(3), unit_value=Decimal("50.00")))
        assert t.subtotal == Decimal("150.00")
        assert t.igv_total == Decimal("27.00")
        assert t.total == Decimal("177.00")


class TestDerivacionDePrecios:
    """El integrador puede pensar en valor sin IGV (ERP) o precio con IGV (POS)."""

    def test_desde_precio_con_igv(self) -> None:
        t = totals(item(unit_price=Decimal("118.00")))
        assert t.items[0].unit_value == Decimal("100.000000")
        assert t.total == Decimal("118.00")

    def test_desde_valor_sin_igv_deriva_el_precio(self) -> None:
        t = totals(item(unit_value=Decimal("100.00")))
        assert t.items[0].unit_price == Decimal("118.000000")

    def test_no_deriva_igv_en_operacion_exonerada(self) -> None:
        t = totals(item(tax_affectation="20", unit_price=Decimal("100.00")))
        assert t.items[0].unit_value == Decimal("100.000000")
        assert t.igv_total == Decimal("0.00")

    def test_exige_al_menos_uno(self) -> None:
        with pytest.raises(TaxCalculationError, match="unit_value"):
            totals(item())


class TestAfectaciones:
    @pytest.mark.parametrize(
        ("affectation", "bucket"),
        [("10", "taxable_total"), ("20", "exempt_total"), ("30", "unaffected_total"),
         ("40", "export_total")],
    )
    def test_cada_afectacion_cae_en_su_total(self, affectation: str, bucket: str) -> None:
        t = totals(item(tax_affectation=affectation, unit_value=Decimal("100.00")))
        assert getattr(t, bucket) == Decimal("100.00")

    def test_comprobante_mixto(self) -> None:
        t = totals(
            item(quantity=Decimal(2), tax_affectation="10", unit_value=Decimal("50.00")),
            item(tax_affectation="20", unit_value=Decimal("30.00")),
            item(tax_affectation="30", unit_value=Decimal("20.00")),
            item(tax_affectation="40", unit_value=Decimal("40.00")),
        )
        assert t.taxable_total == Decimal("100.00")
        assert t.exempt_total == Decimal("30.00")
        assert t.unaffected_total == Decimal("20.00")
        assert t.export_total == Decimal("40.00")
        assert t.igv_total == Decimal("18.00")  # solo la gravada tributa
        assert t.total == Decimal("208.00")

    def test_afectacion_desconocida_falla(self) -> None:
        with pytest.raises(ValueError, match="Catálogo 07"):
            totals(item(tax_affectation="99", unit_value=Decimal("10.00")))


class TestOperacionesGratuitas:
    """Bonificaciones y retiros: se declaran pero no se cobran."""

    def test_linea_gratuita_no_aporta_valor_de_venta(self) -> None:
        t = totals(item(tax_affectation="15", unit_value=Decimal("10.00")))
        assert t.items[0].line_extension_amount == Decimal("0.00")
        assert t.items[0].total == Decimal("0.00")
        assert t.subtotal == Decimal("0.00")

    def test_usa_price_type_02(self) -> None:
        """Catálogo 16: las gratuitas llevan valor referencial, no precio de venta."""
        assert totals(item(tax_affectation="15", unit_value=Decimal("10.00"))).items[0].price_type == "02"
        assert totals(item(tax_affectation="10", unit_value=Decimal("10.00"))).items[0].price_type == "01"

    def test_igv_gratuito_se_declara_pero_no_se_cobra(self) -> None:
        t = totals(
            item(quantity=Decimal(10), tax_affectation="10", unit_value=Decimal("10.00")),
            item(tax_affectation="15", unit_value=Decimal("10.00")),
        )
        assert t.igv_total == Decimal("18.00")
        assert t.igv_free_total == Decimal("1.80")
        assert t.free_total == Decimal("10.00")
        assert t.total == Decimal("118.00")

    def test_el_comprobante_cuadra_con_gratuitas(self) -> None:
        """Si el IGV gratuito entrara en TaxAmount, SUNAT rechazaría por descuadre."""
        t = totals(
            item(quantity=Decimal(10), tax_affectation="10", unit_value=Decimal("10.00")),
            item(tax_affectation="21", unit_value=Decimal("7.00")),
        )
        assert t.tax_inclusive_amount == t.total
        assert t.tax_inclusive_amount == t.tax_exclusive_amount + t.tax_amount_total


class TestIcbper:
    def test_impuesto_por_bolsa(self) -> None:
        t = totals(item(quantity=Decimal(3), unit_value=Decimal("1.00"), icbper_applies=True))
        assert t.icbper_total == Decimal("1.50")
        assert t.total == Decimal("5.04")  # 3.00 + 0.54 IGV + 1.50 ICBPER

    def test_no_aplica_por_defecto(self) -> None:
        assert totals(item(unit_value=Decimal("1.00"))).icbper_total == Decimal("0.00")


class TestDescuentos:
    def test_descuento_de_linea(self) -> None:
        t = totals(item(unit_value=Decimal("100.00"), discount=Decimal("10.00")))
        assert t.subtotal == Decimal("90.00")
        assert t.discount_total == Decimal("10.00")
        assert t.igv_total == Decimal("16.20")
        assert t.total == Decimal("106.20")

    def test_descuento_mayor_al_valor_falla(self) -> None:
        with pytest.raises(TaxCalculationError, match="descuento"):
            totals(item(unit_value=Decimal("10.00"), discount=Decimal("20.00")))


class TestCuadreDeTotales:
    """La regla estructural: la cabecera es la suma de líneas ya redondeadas."""

    def test_cabecera_es_suma_exacta_de_lineas(self) -> None:
        t = totals(*[item(quantity=Decimal(3), unit_value=Decimal("33.333333")) for _ in range(10)])
        assert t.total == sum(i.total for i in t.items)
        assert t.subtotal == sum(i.line_extension_amount for i in t.items)

    @pytest.mark.parametrize("n", [1, 2, 5, 17, 50])
    def test_invariante_de_cuadre(self, n: int) -> None:
        t = totals(*[item(quantity=Decimal(1), unit_value=Decimal("7.77")) for _ in range(n)])
        assert t.tax_inclusive_amount == t.total

    def test_valores_con_muchos_decimales(self) -> None:
        t = totals(item(quantity=Decimal("2.5"), unit_value=Decimal("13.579246")))
        assert t.subtotal == Decimal("33.95")
        assert t.igv_total == Decimal("6.11")
        assert t.total == Decimal("40.06")


class TestSubtotalesTributarios:
    def test_agrupa_por_esquema(self) -> None:
        t = totals(
            item(quantity=Decimal(2), tax_affectation="10", unit_value=Decimal("50.00")),
            item(tax_affectation="20", unit_value=Decimal("30.00")),
        )
        by_scheme = {s.scheme.scheme_id: s for s in t.tax_subtotals}
        assert by_scheme["1000"].taxable_amount == Decimal("100.00")
        assert by_scheme["1000"].tax_amount == Decimal("18.00")
        assert by_scheme["1000"].scheme.category_id == "S"
        assert by_scheme["9997"].taxable_amount == Decimal("30.00")
        assert by_scheme["9997"].tax_amount == Decimal("0.00")
        assert by_scheme["9997"].scheme.category_id == "E"

    def test_icbper_tiene_su_propio_subtotal(self) -> None:
        t = totals(item(quantity=Decimal(2), unit_value=Decimal("1.00"), icbper_applies=True))
        assert any(s.scheme.scheme_id == "7152" for s in t.tax_subtotals)


class TestValidaciones:
    def test_cantidad_cero_falla(self) -> None:
        with pytest.raises(TaxCalculationError, match="cantidad"):
            calculate_item(
                ItemInput(quantity=Decimal(0), tax_affectation="10", unit_value=Decimal("10.00")),
                igv_rate=IGV, icbper_rate=ICBPER,
            )

    def test_sin_items_falla(self) -> None:
        with pytest.raises(TaxCalculationError, match="al menos un ítem"):
            calculate_totals([], igv_rate=IGV, icbper_rate=ICBPER)
