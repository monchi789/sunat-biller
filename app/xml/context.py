"""Datos de entrada de los builders XML.

Dataclasses planas, desacopladas del ORM y de Pydantic: los builders son
funciones puras `contexto → bytes`, lo que hace triviales los golden tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal

from app.domain.tax_engine import DocumentTotals


@dataclass(frozen=True, slots=True)
class PartyContext:
    """Emisor o receptor, tal como quedó congelado en el snapshot."""

    document_type: str
    """Catálogo 06. El emisor siempre `6` (RUC)."""
    document_number: str
    legal_name: str
    commercial_name: str | None = None
    address: str | None = None
    ubigeo: str | None = None
    district: str | None = None
    province: str | None = None
    department: str | None = None
    country_code: str = "PE"


@dataclass(frozen=True, slots=True)
class InstallmentContext:
    number: int
    due_date: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ItemContext:
    """Datos descriptivos de una línea. Los importes vienen del motor tributario."""

    line_number: int
    description: str
    unit_code: str
    quantity: Decimal
    product_code: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceContext:
    """Documento afectado por una nota de crédito o débito."""

    document_type: str
    document_id: str
    reason_code: str
    reason_description: str


@dataclass(frozen=True, slots=True)
class DocumentContext:
    """Todo lo que un builder necesita para emitir un comprobante."""

    document_type: str
    document_id: str
    """`F001-00000001`."""
    issue_date: date
    currency: str
    operation_type: str
    payment_terms: str
    supplier: PartyContext
    totals: DocumentTotals
    items: list[ItemContext]
    amount_in_words: str
    issue_time: time | None = None
    customer: PartyContext | None = None
    installments: list[InstallmentContext] = field(default_factory=list)
    reference: ReferenceContext | None = None
    signature_id: str = "SignatureSP"

    @property
    def is_credit(self) -> bool:
        return self.payment_terms.upper() == "CREDITO"
