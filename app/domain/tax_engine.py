"""Motor de cálculo tributario: importes de línea y totales de comprobante.

Es el corazón fiscal del sistema. Todo lo que SUNAT valida numéricamente sale de
aquí, y la regla que gobierna el diseño es una sola:

    **Los totales de cabecera son la suma de los importes de línea YA redondeados.**

SUNAT recomputa los totales sumando los montos que el emisor declaró por línea.
Si se calcula la cabecera desde valores sin redondear ("redondear al final"), en
comprobantes de muchos ítems aparecen desviaciones de céntimos y SUNAT observa el
comprobante. Por eso `round2` se aplica por línea, y la cabecera solo suma.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from app.catalogs.tax_schemes import (
    EXEMPT_AFFECTATIONS,
    EXPORT_AFFECTATIONS,
    ICBPER_SCHEME,
    ISC_SCHEME,
    OTHER_TAX_SCHEME,
    TAXABLE_AFFECTATIONS,
    UNAFFECTED_AFFECTATIONS,
    TaxSchemeInfo,
    is_free,
    tax_scheme_for,
)
from app.domain.money import ZERO, round2, round6


class TaxCalculationError(ValueError):
    """El ítem no aporta datos suficientes o coherentes para calcularse."""


@dataclass(frozen=True, slots=True)
class ItemInput:
    """Entrada mínima para calcular una línea.

    Deliberadamente desacoplada de `DocumentItemCreate`: el motor no depende de
    Pydantic ni de la capa HTTP, lo que lo hace trivial de testear.
    """

    quantity: Decimal
    tax_affectation: str
    unit_value: Decimal | None = None
    """Valor unitario **sin** IGV."""
    unit_price: Decimal | None = None
    """Precio unitario **con** IGV. Alternativa a `unit_value`."""
    discount: Decimal = ZERO
    """Descuento del ítem, sobre el valor de venta (sin IGV)."""
    isc_amount: Decimal = ZERO
    """ISC del ítem. El sistema no lo calcula: se declara."""
    icbper_applies: bool = False
    """Si la línea está afecta al impuesto a las bolsas plásticas."""
    other_tax_amount: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class ItemComputation:
    """Importes calculados de una línea, ya redondeados y listos para el XML."""

    line_extension_amount: Decimal
    """`cbc:LineExtensionAmount` — valor de venta. **0.00 en operaciones gratuitas.**"""
    unit_value: Decimal
    """`cac:Price/cbc:PriceAmount` — valor unitario sin IGV."""
    unit_price: Decimal
    """`cac:PricingReference/.../cbc:PriceAmount` — precio unitario con IGV."""
    price_type: str
    """Catálogo 16: `01` precio de venta, `02` valor referencial (gratuitas)."""
    discount: Decimal
    taxable_amount: Decimal
    """Base sobre la que se calculó el IGV (también en gratuitas)."""
    igv_amount: Decimal
    isc_amount: Decimal
    icbper_amount: Decimal
    other_tax_amount: Decimal
    total: Decimal
    """Importe total de la línea. **0.00 en operaciones gratuitas** (no se cobra)."""
    tax_affectation: str
    scheme: TaxSchemeInfo
    is_free: bool


@dataclass(frozen=True, slots=True)
class TaxSubtotal:
    """Un `cac:TaxSubtotal` de la cabecera, agregado por esquema de tributo."""

    taxable_amount: Decimal
    tax_amount: Decimal
    scheme: TaxSchemeInfo
    percent: Decimal | None = None


@dataclass(slots=True)
class DocumentTotals:
    """Totales de cabecera. Cada campo mapea a una columna de `ElectronicDocument`."""

    subtotal: Decimal = ZERO
    """Suma de `LineExtensionAmount` de las líneas onerosas."""
    discount_total: Decimal = ZERO
    taxable_total: Decimal = ZERO
    exempt_total: Decimal = ZERO
    unaffected_total: Decimal = ZERO
    export_total: Decimal = ZERO
    free_total: Decimal = ZERO
    """Valor de las operaciones gratuitas. No suma al total a pagar."""
    igv_total: Decimal = ZERO
    """IGV **cobrado**. Excluye el de las operaciones gratuitas."""
    igv_free_total: Decimal = ZERO
    """IGV **declarado** de las operaciones gratuitas.

    Se informa en su propio `cac:TaxSubtotal` (esquema 9996 GRA) pero **no** entra
    en `cac:TaxTotal/cbc:TaxAmount` de cabecera ni en `PayableAmount`: si entrara,
    `TaxInclusiveAmount` dejaría de cuadrar con `TaxExclusiveAmount + TaxAmount` y
    SUNAT rechazaría el comprobante. Es el descuadre clásico de las bonificaciones.
    """
    isc_total: Decimal = ZERO
    icbper_total: Decimal = ZERO
    other_tax_total: Decimal = ZERO
    total: Decimal = ZERO
    """`cbc:PayableAmount` — lo que efectivamente se cobra."""
    items: list[ItemComputation] = field(default_factory=list)
    tax_subtotals: list[TaxSubtotal] = field(default_factory=list)

    @property
    def tax_amount_total(self) -> Decimal:
        """`cac:TaxTotal/cbc:TaxAmount` de cabecera: IGV + ISC + ICBPER + otros."""
        return round2(self.igv_total + self.isc_total + self.icbper_total + self.other_tax_total)

    @property
    def tax_exclusive_amount(self) -> Decimal:
        """`cbc:TaxExclusiveAmount` — total de operaciones gravadas."""
        return self.taxable_total

    @property
    def tax_inclusive_amount(self) -> Decimal:
        """`cbc:TaxInclusiveAmount` — valor de venta más impuestos."""
        return round2(self.subtotal + self.tax_amount_total)


# ────────────────────────────────────────────────────────────────── cálculo


def _resolve_unit_amounts(item: ItemInput, igv_rate: Decimal) -> tuple[Decimal, Decimal]:
    """Deriva `(unit_value, unit_price)` a partir de lo que haya enviado el cliente.

    Acepta cualquiera de los dos: un POS piensa en precio con IGV, un ERP en valor
    sin IGV. Se exige al menos uno.
    """
    affects_igv = item.tax_affectation in TAXABLE_AFFECTATIONS
    factor = (Decimal(1) + igv_rate) if affects_igv else Decimal(1)

    if item.unit_value is not None:
        unit_value = item.unit_value
        unit_price = item.unit_price if item.unit_price is not None else unit_value * factor
    elif item.unit_price is not None:
        unit_price = item.unit_price
        unit_value = unit_price / factor
    else:
        raise TaxCalculationError("El ítem debe declarar `unit_value` o `unit_price`.")

    return round6(unit_value), round6(unit_price)


def calculate_item(item: ItemInput, *, igv_rate: Decimal, icbper_rate: Decimal) -> ItemComputation:
    """Calcula los importes de una línea. Todos los resultados salen redondeados."""
    if item.quantity <= 0:
        raise TaxCalculationError("La cantidad debe ser mayor que cero.")

    scheme = tax_scheme_for(item.tax_affectation)
    free = is_free(item.tax_affectation)
    unit_value, unit_price = _resolve_unit_amounts(item, igv_rate)

    # Paso 1-2: bruto a precisión plena, neto redondeado una sola vez.
    gross = item.quantity * unit_value
    net = round2(gross - item.discount)
    if net < 0:
        raise TaxCalculationError("El descuento no puede superar el valor de venta de la línea.")

    # Paso 3: el IGV se calcula sobre el neto también en gratuitas (se declara,
    # no se cobra), pero solo en afectaciones gravadas o gratuitas de origen
    # gravado; exoneradas, inafectas y exportación no generan IGV.
    charges_igv = item.tax_affectation in TAXABLE_AFFECTATIONS
    igv_base = net if (charges_igv or free) else ZERO
    igv = round2(igv_base * igv_rate) if (charges_igv or free) else ZERO

    icbper = round2(item.quantity * icbper_rate) if item.icbper_applies else ZERO
    isc = round2(item.isc_amount)
    other = round2(item.other_tax_amount)

    if free:
        # Gratuitas: no aportan valor de venta ni total a cobrar, pero su valor
        # referencial viaja en `PriceAmount` con `PriceTypeCode = "02"`.
        line_extension = ZERO
        total = ZERO
        price_type = "02"
    else:
        line_extension = net
        total = round2(net + igv + isc + icbper + other)
        price_type = "01"

    return ItemComputation(
        line_extension_amount=line_extension,
        unit_value=unit_value,
        unit_price=unit_price,
        price_type=price_type,
        discount=round2(item.discount),
        taxable_amount=round2(igv_base) if (charges_igv or free) else net,
        igv_amount=igv,
        isc_amount=isc,
        icbper_amount=icbper,
        other_tax_amount=other,
        total=total,
        tax_affectation=item.tax_affectation,
        scheme=scheme,
        is_free=free,
    )


def _aggregate_subtotals(
    computations: Sequence[ItemComputation], igv_rate: Decimal
) -> list[TaxSubtotal]:
    """Agrupa las líneas en los `cac:TaxSubtotal` de la cabecera, por esquema."""
    buckets: dict[str, list[Decimal]] = {}
    schemes: dict[str, TaxSchemeInfo] = {}

    for comp in computations:
        key = comp.scheme.scheme_id
        schemes.setdefault(key, comp.scheme)
        base, tax = buckets.setdefault(key, [ZERO, ZERO])
        buckets[key] = [base + comp.taxable_amount, tax + comp.igv_amount]

    subtotals = [
        TaxSubtotal(
            taxable_amount=round2(base),
            tax_amount=round2(tax),
            scheme=schemes[key],
            percent=igv_rate * 100 if schemes[key].tax_type_code == "VAT" else None,
        )
        for key, (base, tax) in buckets.items()
    ]

    # ISC, ICBPER y otros van en su propio subtotal, no agrupados con el IGV.
    for scheme, amount in (
        (ISC_SCHEME, sum((c.isc_amount for c in computations), ZERO)),
        (ICBPER_SCHEME, sum((c.icbper_amount for c in computations), ZERO)),
        (OTHER_TAX_SCHEME, sum((c.other_tax_amount for c in computations), ZERO)),
    ):
        if amount > 0:
            base = sum((c.line_extension_amount for c in computations), ZERO)
            subtotals.append(
                TaxSubtotal(taxable_amount=round2(base), tax_amount=round2(amount), scheme=scheme)
            )

    return subtotals


def calculate_totals(
    items: Iterable[ItemInput], *, igv_rate: Decimal, icbper_rate: Decimal
) -> DocumentTotals:
    """Calcula todos los importes del comprobante a partir de sus ítems.

    Los totales son la suma de importes de línea **ya redondeados** (ver el
    docstring del módulo).
    """
    computations = [calculate_item(item, igv_rate=igv_rate, icbper_rate=icbper_rate) for item in items]
    if not computations:
        raise TaxCalculationError("El comprobante debe tener al menos un ítem.")

    totals = DocumentTotals(items=computations)

    for comp in computations:
        totals.discount_total += comp.discount
        if comp.is_free:
            totals.igv_free_total += comp.igv_amount
        else:
            totals.igv_total += comp.igv_amount
        totals.isc_total += comp.isc_amount
        totals.icbper_total += comp.icbper_amount
        totals.other_tax_total += comp.other_tax_amount

        if comp.is_free:
            # El valor de las gratuitas se contabiliza aparte: ni suma al valor
            # de venta ni al importe a pagar.
            totals.free_total += comp.taxable_amount
            continue

        totals.subtotal += comp.line_extension_amount
        totals.total += comp.total

        affectation = comp.tax_affectation
        if affectation in TAXABLE_AFFECTATIONS:
            totals.taxable_total += comp.line_extension_amount
        elif affectation in EXEMPT_AFFECTATIONS:
            totals.exempt_total += comp.line_extension_amount
        elif affectation in UNAFFECTED_AFFECTATIONS:
            totals.unaffected_total += comp.line_extension_amount
        elif affectation in EXPORT_AFFECTATIONS:
            totals.export_total += comp.line_extension_amount

    for name in (
        "subtotal", "discount_total", "taxable_total", "exempt_total", "unaffected_total",
        "export_total", "free_total", "igv_total", "igv_free_total", "isc_total", "icbper_total",
        "other_tax_total", "total",
    ):
        setattr(totals, name, round2(getattr(totals, name)))

    totals.tax_subtotals = _aggregate_subtotals(computations, igv_rate)
    return totals
