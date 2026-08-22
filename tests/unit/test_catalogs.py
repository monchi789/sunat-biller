"""Coherencia entre los Enums de `app.schemas.common` y los catálogos SUNAT.

Si un Enum admite un código que ningún catálogo describe, el builder XML emitirá
un nodo vacío o reventará en producción. Si un catálogo tiene un código que
ningún Enum admite, es código muerto o una validación que falta. Este test es
barato y ataja la clase de error que más rechazos SUNAT provoca.
"""

import pytest

from app.catalogs import (
    CAT01_DOCUMENT_TYPES,
    CAT03_UNIT_CODES,
    CAT06_IDENTITY_DOCS,
    CAT07_TAX_AFFECTATION,
    CAT09_CREDIT_NOTE_REASONS,
    CAT10_DEBIT_NOTE_REASONS,
    CAT16_PRICE_TYPES,
    CAT51_OPERATION_TYPES,
)
from app.catalogs.tax_schemes import TAX_SCHEME_BY_AFFECTATION, tax_scheme_for
from app.schemas.common import (
    CreditNoteReasonType,
    DebitNoteReasonType,
    DocumentType,
    IdentityDocumentType,
    OperationType,
    PriceType,
    TaxAffectationType,
    UnitCode,
)

PAIRS = [
    ("Catálogo 01 tipo de documento", DocumentType, CAT01_DOCUMENT_TYPES),
    ("Catálogo 03 unidad de medida", UnitCode, CAT03_UNIT_CODES),
    ("Catálogo 06 documento de identidad", IdentityDocumentType, CAT06_IDENTITY_DOCS),
    ("Catálogo 07 afectación IGV", TaxAffectationType, CAT07_TAX_AFFECTATION),
    ("Catálogo 09 motivo nota de crédito", CreditNoteReasonType, CAT09_CREDIT_NOTE_REASONS),
    ("Catálogo 10 motivo nota de débito", DebitNoteReasonType, CAT10_DEBIT_NOTE_REASONS),
    ("Catálogo 16 tipo de precio", PriceType, CAT16_PRICE_TYPES),
    ("Catálogo 51 tipo de operación", OperationType, CAT51_OPERATION_TYPES),
]


@pytest.mark.parametrize(("label", "enum", "catalog"), PAIRS, ids=[p[0] for p in PAIRS])
def test_todo_valor_del_enum_tiene_descripcion(label: str, enum: type, catalog: dict[str, str]) -> None:
    missing = sorted({member.value for member in enum} - set(catalog))
    assert not missing, f"{label}: códigos sin descripción en el catálogo → {missing}"


@pytest.mark.parametrize(("label", "enum", "catalog"), PAIRS, ids=[p[0] for p in PAIRS])
def test_las_descripciones_no_estan_vacias(label: str, enum: type, catalog: dict[str, str]) -> None:
    blank = sorted(code for code in {m.value for m in enum} if not catalog.get(code, "").strip())
    assert not blank, f"{label}: descripciones vacías → {blank}"


def test_catalogo_06_es_el_completo_de_sunat() -> None:
    """El Catálogo 06 es cerrado: el Enum debe cubrirlo entero, no un subset."""
    assert {m.value for m in IdentityDocumentType} == set(CAT06_IDENTITY_DOCS)


def test_catalogo_07_es_el_completo_de_sunat() -> None:
    assert {m.value for m in TaxAffectationType} == set(CAT07_TAX_AFFECTATION)


def test_toda_afectacion_tiene_esquema_de_tributo() -> None:
    """Sin esquema, el `cac:TaxSubtotal` sale inválido y SUNAT rechaza con 2xxx."""
    missing = sorted({m.value for m in TaxAffectationType} - set(TAX_SCHEME_BY_AFFECTATION))
    assert not missing, f"afectaciones sin esquema de tributo → {missing}"


@pytest.mark.parametrize("affectation", sorted(TAX_SCHEME_BY_AFFECTATION))
def test_los_esquemas_son_coherentes(affectation: str) -> None:
    scheme = tax_scheme_for(affectation)
    assert scheme.category_id in {"S", "E", "O", "Z"}
    assert scheme.tax_type_code in {"VAT", "FRE", "EXC", "OTH"}
    assert scheme.scheme_id.isdigit() and len(scheme.scheme_id) == 4
    assert scheme.scheme_name


def test_el_prefijo_de_afectacion_predice_la_categoria() -> None:
    """Gravadas empiezan por 1, exoneradas por 2, inafectas por 3, exportación 40."""
    expected = {"1": "S", "2": "E", "3": "O", "4": "Z"}
    for code, scheme in TAX_SCHEME_BY_AFFECTATION.items():
        assert scheme.category_id == expected[code[0]], f"afectación {code}"
