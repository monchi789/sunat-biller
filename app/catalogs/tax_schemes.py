"""Mapa afectación IGV (Catálogo 07) → esquema de tributo en el XML UBL.

Esta es la tabla que más rechazos 2xxx provoca cuando está mal: SUNAT valida que
`cac:TaxCategory/cbc:ID`, `cac:TaxScheme/cbc:ID`, `cbc:Name` y `cbc:TaxTypeCode`
sean coherentes entre sí y con el tipo de afectación declarado.

Códigos de tributo (Catálogo 05):
    1000 IGV    · 1016 IVAP  · 2000 ISC   · 7152 ICBPER
    9995 EXP    · 9996 GRA   · 9997 EXO   · 9998 INA   · 9999 OTROS

Categorías (UN/ECE 5305): ``S`` gravado · ``E`` exonerado · ``O`` inafecto ·
``Z`` exportación (tasa cero).
"""

from __future__ import annotations

from typing import NamedTuple


class TaxSchemeInfo(NamedTuple):
    """Los cuatro valores que el builder XML necesita para un `TaxSubtotal`."""

    category_id: str
    """`cac:TaxCategory/cbc:ID` — S | E | O | Z."""

    scheme_id: str
    """`cac:TaxScheme/cbc:ID` — código del Catálogo 05."""

    scheme_name: str
    """`cac:TaxScheme/cbc:Name` — IGV, EXO, INA, GRA, EXP, IVAP."""

    tax_type_code: str
    """`cac:TaxScheme/cbc:TaxTypeCode` — VAT | FRE | EXC | OTH."""


#: Afectación → esquema. Las operaciones "gratuitas" (retiros, bonificaciones,
#: muestras) usan siempre 9996/GRA/FRE: llevan IGV calculado pero no cobrado, y
#: su importe va a `free_total`, no a la base imponible.
TAX_SCHEME_BY_AFFECTATION: dict[str, TaxSchemeInfo] = {
    # Gravadas onerosas
    "10": TaxSchemeInfo("S", "1000", "IGV", "VAT"),
    # Gravadas gratuitas (retiros y bonificaciones)
    "11": TaxSchemeInfo("S", "9996", "GRA", "FRE"),
    "12": TaxSchemeInfo("S", "9996", "GRA", "FRE"),
    "13": TaxSchemeInfo("S", "9996", "GRA", "FRE"),
    "14": TaxSchemeInfo("S", "9996", "GRA", "FRE"),
    "15": TaxSchemeInfo("S", "9996", "GRA", "FRE"),
    "16": TaxSchemeInfo("S", "9996", "GRA", "FRE"),
    # Gravada IVAP (venta de arroz pilado)
    "17": TaxSchemeInfo("S", "1016", "IVAP", "VAT"),
    # Exoneradas
    "20": TaxSchemeInfo("E", "9997", "EXO", "VAT"),
    "21": TaxSchemeInfo("E", "9996", "GRA", "FRE"),
    # Inafectas
    "30": TaxSchemeInfo("O", "9998", "INA", "FRE"),
    "31": TaxSchemeInfo("O", "9996", "GRA", "FRE"),
    "32": TaxSchemeInfo("O", "9996", "GRA", "FRE"),
    "33": TaxSchemeInfo("O", "9996", "GRA", "FRE"),
    "34": TaxSchemeInfo("O", "9996", "GRA", "FRE"),
    "35": TaxSchemeInfo("O", "9996", "GRA", "FRE"),
    "36": TaxSchemeInfo("O", "9996", "GRA", "FRE"),
    # Exportación
    "40": TaxSchemeInfo("Z", "9995", "EXP", "FRE"),
}

#: Afectaciones cuyo importe es **gratuito**: no suman a la base imponible ni al
#: total a pagar, pero sí se declaran con su IGV calculado.
FREE_AFFECTATIONS: frozenset[str] = frozenset(
    {"11", "12", "13", "14", "15", "16", "21", "31", "32", "33", "34", "35", "36"}
)

#: Afectaciones que generan IGV cobrable (base imponible real).
TAXABLE_AFFECTATIONS: frozenset[str] = frozenset({"10", "17"})

#: Exoneradas onerosas.
EXEMPT_AFFECTATIONS: frozenset[str] = frozenset({"20"})

#: Inafectas onerosas.
UNAFFECTED_AFFECTATIONS: frozenset[str] = frozenset({"30"})

#: Exportación.
EXPORT_AFFECTATIONS: frozenset[str] = frozenset({"40"})

# Esquemas de tributos no-IGV, usados en sus propios `TaxSubtotal`.
ISC_SCHEME = TaxSchemeInfo("S", "2000", "ISC", "EXC")
ICBPER_SCHEME = TaxSchemeInfo("S", "7152", "ICBPER", "OTH")
OTHER_TAX_SCHEME = TaxSchemeInfo("S", "9999", "OTROS", "OTH")


def tax_scheme_for(affectation: str) -> TaxSchemeInfo:
    """Devuelve el esquema de tributo de una afectación del Catálogo 07."""
    try:
        return TAX_SCHEME_BY_AFFECTATION[affectation]
    except KeyError:
        raise ValueError(f"Afectación IGV desconocida (Catálogo 07): {affectation!r}") from None


def is_free(affectation: str) -> bool:
    """`True` si la operación es gratuita (retiro, bonificación, muestra)."""
    return affectation in FREE_AFFECTATIONS
