"""Contextos de documento reutilizables por los tests de XML."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from app.domain.number_to_words import amount_to_words
from app.domain.tax_engine import DocumentTotals, ItemInput, calculate_totals
from app.xml.context import DocumentContext, ItemContext, PartyContext
from tests.conftest import ICBPER_RATE, IGV_RATE

SUPPLIER = PartyContext(
    document_type="6",
    document_number="20000000001",
    legal_name="EMPRESA DE PRUEBA SAC",
    commercial_name="PRUEBA",
    address="AV. SIEMPRE VIVA 742",
    ubigeo="150101",
    district="LIMA",
    province="LIMA",
    department="LIMA",
)

CUSTOMER = PartyContext(
    document_type="6",
    document_number="20512345678",
    legal_name="CLIENTE EMPRESARIAL SAC",
    address="JR. LOS OLIVOS 123",
    ubigeo="150102",
)


def make_totals(*items: ItemInput) -> DocumentTotals:
    return calculate_totals(items, igv_rate=IGV_RATE, icbper_rate=ICBPER_RATE)


def make_context(
    totals: DocumentTotals,
    items: list[ItemContext],
    **overrides: object,
) -> DocumentContext:
    defaults: dict[str, object] = {
        "document_type": "01",
        "document_id": "F001-00000001",
        "issue_date": date(2024, 1, 15),
        "issue_time": time(12, 0, 0),
        "currency": "PEN",
        "operation_type": "0101",
        "payment_terms": "Contado",
        "supplier": SUPPLIER,
        "customer": CUSTOMER,
        "totals": totals,
        "items": items,
        "amount_in_words": amount_to_words(totals.total, "PEN"),
    }
    return DocumentContext(**{**defaults, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def simple_invoice() -> DocumentContext:
    """Factura gravada de un ítem: 100.00 + IGV = 118.00."""
    totals = make_totals(
        ItemInput(quantity=Decimal(1), tax_affectation="10", unit_value=Decimal("100.00"))
    )
    items = [
        ItemContext(
            line_number=1,
            description="SERVICIO DE CONSULTORIA",
            unit_code="ZZ",
            quantity=Decimal(1),
            product_code="SRV001",
        )
    ]
    return make_context(totals, items)
