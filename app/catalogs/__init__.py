"""Catálogos oficiales de SUNAT.

Diccionarios puros `{código: descripción}`, sin lógica ni imports pesados. Los
schemas restringen los valores vía los Enums de `app.schemas.common`; estos
mapas existen para que los builders XML puedan escribir la *descripción* que
SUNAT espera en los nodos de texto.
"""

from app.catalogs.cat01_document_types import CAT01_DOCUMENT_TYPES
from app.catalogs.cat03_unit_codes import CAT03_UNIT_CODES
from app.catalogs.cat06_identity_docs import CAT06_IDENTITY_DOCS
from app.catalogs.cat07_tax_affectation import CAT07_TAX_AFFECTATION
from app.catalogs.cat09_credit_note_reasons import CAT09_CREDIT_NOTE_REASONS
from app.catalogs.cat10_debit_note_reasons import CAT10_DEBIT_NOTE_REASONS
from app.catalogs.cat16_price_types import CAT16_PRICE_TYPES
from app.catalogs.cat51_operation_types import CAT51_OPERATION_TYPES
from app.catalogs.cdr_codes import CdrOutcome, classify_cdr_code
from app.catalogs.tax_schemes import TaxSchemeInfo, tax_scheme_for

__all__ = [
    "CAT01_DOCUMENT_TYPES",
    "CAT03_UNIT_CODES",
    "CAT06_IDENTITY_DOCS",
    "CAT07_TAX_AFFECTATION",
    "CAT09_CREDIT_NOTE_REASONS",
    "CAT10_DEBIT_NOTE_REASONS",
    "CAT16_PRICE_TYPES",
    "CAT51_OPERATION_TYPES",
    "CdrOutcome",
    "TaxSchemeInfo",
    "classify_cdr_code",
    "tax_scheme_for",
]
