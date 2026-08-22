"""Importe en letras para `cbc:Note` — «SON CIENTO DIECIOCHO CON 00/100 SOLES».

SUNAT exige el literal del monto total en el comprobante. Es una función
engañosamente densa en casos borde del español: apócope (*veintiún mil*, no
*veintiuno mil*), *cien* frente a *ciento*, y singular/plural de *millón*.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.money import round2

_UNITS = (
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
    "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISEIS",
    "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
)
_TENS = ("", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
_HUNDREDS = (
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
)

#: Literal de moneda según ISO 4217. Debe coincidir con `CurrencyCode`.
CURRENCY_WORDS: dict[str, str] = {
    "PEN": "SOLES",
    "USD": "DOLARES AMERICANOS",
    "EUR": "EUROS",
}


def _under_hundred(n: int) -> str:
    if n <= 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    if tens == 2:  # 21–29 se escriben juntos: VEINTIUNO, VEINTIDOS…
        return f"VEINTI{_UNITS[unit].lower()}".upper()
    if unit == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} Y {_UNITS[unit]}"


def _under_thousand(n: int) -> str:
    if n == 100:
        return "CIEN"  # exactamente cien, no "ciento"
    hundreds, rest = divmod(n, 100)
    parts = [_HUNDREDS[hundreds]] if hundreds else []
    if rest:
        parts.append(_under_hundred(rest))
    return " ".join(parts)


def _apocopate(text: str) -> str:
    """Apócope ante sustantivo: *un* mil, *veintiún* mil, *treinta y un* mil."""
    if text == "UNO":
        return "UN"
    if text.endswith(" UNO"):
        return f"{text[:-4]} UN"
    if text == "VEINTIUNO":
        return "VEINTIUN"
    return text


def _integer_to_words(n: int) -> str:
    if n == 0:
        return "CERO"

    parts: list[str] = []

    millions, rest = divmod(n, 1_000_000)
    if millions:
        if millions == 1:
            parts.append("UN MILLON")
        else:
            parts.append(f"{_apocopate(_integer_to_words(millions))} MILLONES")

    thousands, hundreds = divmod(rest, 1_000)
    if thousands:
        parts.append("MIL" if thousands == 1 else f"{_apocopate(_under_thousand(thousands))} MIL")

    if hundreds:
        parts.append(_under_thousand(hundreds))

    return " ".join(parts)


def amount_to_words(amount: Decimal, currency: str = "PEN") -> str:
    """Convierte un importe al literal que va en `cbc:Note`.

    >>> amount_to_words(Decimal("118.00"))
    'SON CIENTO DIECIOCHO CON 00/100 SOLES'
    """
    if amount < 0:
        raise ValueError("El importe en letras no admite valores negativos.")

    value = round2(amount)
    integer_part = int(value)
    cents = int((value - integer_part) * 100)

    words = _integer_to_words(integer_part)
    currency_word = CURRENCY_WORDS.get(currency.upper(), currency.upper())

    return f"SON {words} CON {cents:02d}/100 {currency_word}"
