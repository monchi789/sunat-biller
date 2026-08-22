"""Aritmética monetaria con `Decimal`.

**Nunca usar `float` en el pipeline fiscal.** Un `float` rompe la validación de
cuadre (±0.01) y, peor, hace que la serialización del XML no sea reproducible:
como el `ds:DigestValue` de la firma se calcula sobre los dígitos serializados,
un monto formateado desde `float` puede firmar distinto entre corridas.

Redondeo: ``ROUND_HALF_UP``, no el ``ROUND_HALF_EVEN`` (bancario) que Python trae
por defecto. ``Decimal("2.675").quantize(...)`` da 2.67 con HALF_EVEN y 2.68 con
HALF_UP; la contabilidad peruana y el recálculo de SUNAT usan HALF_UP. Dejar el
default produce desviaciones esporádicas de un céntimo contra el ERP del cliente.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

#: Precisión de los importes monetarios (`cbc:*Amount`).
Q2 = Decimal("0.01")

#: Precisión de cantidades y valores unitarios (`cbc:InvoicedQuantity`, `cbc:PriceAmount`).
Q6 = Decimal("0.000001")

ZERO = Decimal("0.00")


def round2(value: Decimal) -> Decimal:
    """Cuantiza a 2 decimales con redondeo comercial."""
    return value.quantize(Q2, rounding=ROUND_HALF_UP)


def round6(value: Decimal) -> Decimal:
    """Cuantiza a 6 decimales con redondeo comercial."""
    return value.quantize(Q6, rounding=ROUND_HALF_UP)


def fmt2(value: Decimal) -> str:
    """Serializa un importe para el XML: exactamente 2 decimales, sin notación
    científica."""
    return f"{round2(value):.2f}"


def fmt6(value: Decimal) -> str:
    """Serializa una cantidad o valor unitario: hasta 6 decimales, sin ceros de
    relleno innecesarios pero siempre en notación posicional."""
    quantized = round6(value).normalize()
    # `normalize()` puede producir exponente positivo ("1E+2"); `quantize` a
    # entero lo devuelve a notación plana.
    if quantized == quantized.to_integral_value():
        quantized = quantized.quantize(Decimal(1))
    return f"{quantized:f}"


def fmt_price(value: Decimal) -> str:
    """Serializa un valor o precio unitario (`cbc:PriceAmount`).

    A diferencia de `fmt6`, garantiza **un mínimo de 2 decimales**: SUNAT rechaza
    un importe escrito como `59` en lugar de `59.00`. Admite hasta 6 decimales
    para no perder precisión en valores unitarios largos, sin ceros de relleno
    más allá del segundo.
    """
    quantized = round6(value)
    text = f"{quantized:f}"
    if "." not in text:
        return f"{text}.00"
    integer, decimals = text.split(".")
    decimals = decimals.rstrip("0")
    if len(decimals) < 2:
        decimals = decimals.ljust(2, "0")
    return f"{integer}.{decimals}"


def is_close(left: Decimal, right: Decimal, tolerance: Decimal = Q2) -> bool:
    """`True` si dos importes cuadran dentro de la tolerancia de SUNAT (±0.01)."""
    return abs(left - right) <= tolerance
