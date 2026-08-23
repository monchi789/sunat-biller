"""Lógica común a todos los comprobantes: cálculo, snapshots y persistencia.

Aquí se une el contrato HTTP (`app/schemas/`) con el motor fiscal
(`app/domain/tax_engine.py`), que no sabe nada de Pydantic ni de la base de datos.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import BusinessRuleError, NotFoundError, TotalsMismatchError
from app.domain.money import is_close
from app.domain.tax_engine import DocumentTotals, ItemInput, TaxCalculationError, calculate_totals
from app.models.company import Company
from app.models.document import ElectronicDocument
from app.models.document_item import DocumentInstallment, DocumentItem
from app.models.snapshot import CompanySnapshot, CustomerSnapshot
from app.schemas.common import DocumentStatus
from app.schemas.customer import CustomerCreate
from app.schemas.document import DocumentCreateBase
from app.schemas.document_item import DocumentItemCreate


def to_item_inputs(items: Sequence[DocumentItemCreate]) -> list[ItemInput]:
    """Traduce el contrato HTTP a la entrada del motor fiscal."""
    return [
        ItemInput(
            quantity=item.quantity,
            tax_affectation=item.tax_affectation.value,
            unit_value=item.unit_value,
            unit_price=item.unit_price,
            discount=item.discount,
            isc_amount=item.isc_amount,
            icbper_applies=item.icbper_applies,
            other_tax_amount=item.other_tax_amount,
        )
        for item in items
    ]


def compute_totals(items: Sequence[DocumentItemCreate]) -> DocumentTotals:
    try:
        return calculate_totals(
            to_item_inputs(items),
            igv_rate=settings.IGV_RATE,
            icbper_rate=settings.ICBPER_RATE,
        )
    except TaxCalculationError as exc:
        raise BusinessRuleError(str(exc)) from exc


def verify_client_totals(items: Sequence[DocumentItemCreate], totals: DocumentTotals) -> None:
    """Contrasta los importes que envió el cliente con los calculados (RF-05.3).

    Los importes del cliente **nunca** se usan: solo sirven para detectar que su
    sistema calcula distinto y avisarle antes de emitir algo descuadrado.
    """
    for item, computed in zip(items, totals.items, strict=True):
        for field, provided, calculated in (
            ("subtotal", item.subtotal, computed.line_extension_amount),
            ("igv_amount", item.igv_amount, computed.igv_amount),
            ("taxable_amount", item.taxable_amount, computed.taxable_amount),
            ("total", item.total, computed.total),
        ):
            if provided is not None and not is_close(provided, calculated):
                raise TotalsMismatchError(
                    f"El campo `{field}` de la línea {item.line_number} no cuadra: "
                    f"enviaste {provided}, el cálculo da {calculated}.",
                    {
                        "line_number": item.line_number,
                        "field": field,
                        "provided": str(provided),
                        "calculated": str(calculated),
                    },
                )


def validate_issue_date(issue_date: date) -> None:
    """SUNAT rechaza fechas futuras y limita la emisión extemporánea."""
    today = date.today()
    if issue_date > today:
        raise BusinessRuleError(
            "La fecha de emisión no puede ser futura.", {"issue_date": issue_date.isoformat()}
        )
    earliest = today - timedelta(days=settings.MAX_ISSUE_BACKDATE_DAYS)
    if issue_date < earliest:
        raise BusinessRuleError(
            f"La fecha de emisión no puede ser anterior a {earliest.isoformat()} "
            f"({settings.MAX_ISSUE_BACKDATE_DAYS} días de plazo).",
            {"issue_date": issue_date.isoformat(), "earliest": earliest.isoformat()},
        )


def validate_installments(data: DocumentCreateBase, total: Decimal) -> None:
    """Coherencia entre forma de pago y cuotas."""
    is_credit = data.payment_terms.value.upper() == "CREDITO"
    installments = data.installments or []

    if is_credit and not installments:
        raise BusinessRuleError("Una venta al crédito requiere al menos una cuota.")
    if not is_credit and installments:
        raise BusinessRuleError("Una venta al contado no admite cuotas.")

    if not installments:
        return

    for installment in installments:
        if installment.due_date < data.issue_date:
            raise BusinessRuleError(
                f"La cuota {installment.installment_number} vence antes de la fecha de emisión.",
            )

    total_installments = sum((i.amount for i in installments), Decimal(0))
    if not is_close(total_installments, total):
        raise TotalsMismatchError(
            f"Las cuotas suman {total_installments} y el comprobante totaliza {total}.",
            {"installments_total": str(total_installments), "document_total": str(total)},
        )


def create_company_snapshot(db: Session, company: Company) -> CompanySnapshot:
    """Congela los datos del emisor. El comprobante debe seguir siendo fiel
    aunque la empresa cambie de razón social o dirección después."""
    snapshot = CompanySnapshot(
        ruc=company.ruc,
        business_name=company.business_name,
        commercial_name=company.commercial_name,
        address=company.address,
        ubigeo=company.ubigeo,
        country_code=company.country_code,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def create_customer_snapshot(db: Session, customer: CustomerCreate | None) -> CustomerSnapshot | None:
    if customer is None:
        return None
    snapshot = CustomerSnapshot(
        document_type=customer.document_type.value,
        document_number=customer.document_number,
        name=customer.name,
        address=customer.address,
        ubigeo=customer.ubigeo,
        country_code=customer.country_code,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def persist_document(
    db: Session,
    *,
    company: Company,
    series_id: UUID,
    series: str,
    number: int,
    document_type: str,
    data: DocumentCreateBase,
    totals: DocumentTotals,
    company_snapshot: CompanySnapshot,
    customer_snapshot: CustomerSnapshot | None,
) -> ElectronicDocument:
    """Crea el documento con sus líneas y cuotas, en estado `PENDING`."""
    document = ElectronicDocument(
        company_id=company.id,
        series_id=series_id,
        company_snapshot_id=company_snapshot.id,
        customer_snapshot_id=customer_snapshot.id if customer_snapshot else None,
        document_type=document_type,
        series=series,
        number=number,
        issue_date=data.issue_date,
        issue_time=data.issue_time,
        currency=data.currency.value,
        operation_type=data.operation_type.value,
        payment_terms=data.payment_terms.value,
        subtotal=totals.subtotal,
        discount_total=totals.discount_total,
        taxable_total=totals.taxable_total,
        exempt_total=totals.exempt_total,
        unaffected_total=totals.unaffected_total,
        export_total=totals.export_total,
        free_total=totals.free_total,
        igv_total=totals.igv_total,
        isc_total=totals.isc_total,
        icbper_total=totals.icbper_total,
        other_tax_total=totals.other_tax_total,
        total=totals.total,
        status=DocumentStatus.PENDING.value,
    )
    db.add(document)
    db.flush()

    for item, computed in zip(data.items, totals.items, strict=True):
        db.add(
            DocumentItem(
                document_id=document.id,
                line_number=item.line_number,
                product_code=item.product_code,
                description=item.description,
                quantity=item.quantity,
                unit_code=item.unit_code.value,
                unit_value=computed.unit_value,
                unit_price=computed.unit_price,
                discount=computed.discount,
                subtotal=computed.line_extension_amount,
                taxable_amount=computed.taxable_amount,
                igv_amount=computed.igv_amount,
                isc_amount=computed.isc_amount,
                icbper_amount=computed.icbper_amount,
                other_tax_amount=computed.other_tax_amount,
                total=computed.total,
                tax_affectation=computed.tax_affectation,
                price_type=computed.price_type,
            )
        )

    for installment in data.installments or []:
        db.add(
            DocumentInstallment(
                document_id=document.id,
                installment_number=installment.installment_number,
                due_date=installment.due_date,
                amount=installment.amount,
            )
        )

    db.flush()
    return document


def get_document(db: Session, company_id: UUID, document_id: UUID) -> ElectronicDocument:
    """Carga un comprobante con todo su detalle, aislado por empresa (RNF-01.2)."""
    document = db.execute(
        select(ElectronicDocument)
        .where(
            ElectronicDocument.id == document_id,
            ElectronicDocument.company_id == company_id,
            ElectronicDocument.deleted_at.is_(None),
        )
        .options(
            selectinload(ElectronicDocument.items),
            selectinload(ElectronicDocument.installments),
            selectinload(ElectronicDocument.references),
            selectinload(ElectronicDocument.files),
            selectinload(ElectronicDocument.customer_snapshot),
            selectinload(ElectronicDocument.company_snapshot),
        )
    ).scalar_one_or_none()

    if document is None:
        raise NotFoundError("El comprobante no existe o no pertenece a la empresa.")
    return document


def list_documents(
    db: Session,
    company_id: UUID,
    *,
    offset: int,
    limit: int,
    document_type: str | None = None,
    status: str | None = None,
    series: str | None = None,
    issue_date_from: date | None = None,
    issue_date_to: date | None = None,
) -> tuple[list[ElectronicDocument], int]:
    filters = [
        ElectronicDocument.company_id == company_id,
        ElectronicDocument.deleted_at.is_(None),
    ]
    if document_type:
        filters.append(ElectronicDocument.document_type == document_type)
    if status:
        filters.append(ElectronicDocument.status == status)
    if series:
        filters.append(ElectronicDocument.series == series)
    if issue_date_from:
        filters.append(ElectronicDocument.issue_date >= issue_date_from)
    if issue_date_to:
        filters.append(ElectronicDocument.issue_date <= issue_date_to)

    total = db.execute(select(func.count(ElectronicDocument.id)).where(*filters)).scalar_one()
    documents = list(
        db.execute(
            select(ElectronicDocument)
            .where(*filters)
            .options(
                selectinload(ElectronicDocument.items),
                selectinload(ElectronicDocument.installments),
                selectinload(ElectronicDocument.customer_snapshot),
            )
            .order_by(ElectronicDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).scalars()
    )
    return documents, total
