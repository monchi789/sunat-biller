"""Emisión de facturas electrónicas (RF-05).

Orquesta piezas ya construidas y probadas: motor fiscal, generador UBL, firmador
y cliente SOAP. Aquí solo vive la secuencia y el manejo de estados.

**Reparto en tres transacciones.** La guía pide una sola, pero eso mantendría una
transacción abierta durante los segundos que tarda la llamada SOAP, bloqueando la
fila de la serie y una conexión del pool. Se parte así:

1. Correlativo, snapshots, documento, ítems y cuotas → `PENDING`. *Commit.*
2. XML generado, firmado y guardado → `SIGNED`. *Commit.*
3. Respuesta de SUNAT, archivos y estado final. *Commit.*

Si algo falla después de la primera, el documento queda en un estado recuperable
en lugar de perderse. El correlativo consumido deja un hueco trazable, que es
preferible a emitir dos comprobantes con el mismo número.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalogs.cdr_codes import CdrOutcome
from app.core.config import settings
from app.core.errors import ConflictError, SunatError
from app.core.logging import document_id_var, get_logger
from app.domain.naming import document_filename
from app.domain.naming import document_id as build_document_id
from app.domain.number_to_words import amount_to_words
from app.domain.tax_engine import DocumentTotals
from app.models.company import Company
from app.models.document import ElectronicDocument
from app.models.document_file import DocumentFile
from app.models.idempotency import IdempotencyKey
from app.models.sunat_submission import SunatSubmission
from app.schemas.common import DocumentStatus, FileType, SubmissionType, SunatStatus
from app.schemas.invoice import InvoiceCreate
from app.services import (
    audit_service,
    certificate_service,
    company_service,
    document_service,
    file_storage_service,
    series_service,
)
from app.services.audit_service import AuditAction, AuditStatus
from app.sunat.client import SunatClient, SunatCredentials
from app.xml.cdr_parser import CdrResult
from app.xml.context import DocumentContext, InstallmentContext, ItemContext, PartyContext
from app.xml.ubl_invoice import build_invoice
from app.xml.xml_signer import extract_digest_value, sign_xml
from app.xml.zip_helper import zip_document

logger = get_logger(__name__)

INVOICE_TYPE = "01"


# ────────────────────────────────────────────────────────────── idempotencia


def find_idempotent_response(db: Session, company_id: UUID, key: str) -> tuple[int, dict] | None:
    """Devuelve la respuesta guardada para una clave ya usada, si existe."""
    record = db.query(IdempotencyKey).filter_by(company_id=company_id, key=key).one_or_none()
    if record is None:
        return None
    if record.expires_at is not None and record.expires_at <= datetime.now(tz=UTC):
        db.delete(record)
        db.commit()
        return None
    return record.response_status, json.loads(record.response_body)


def _store_idempotent_response(
    db: Session, company_id: UUID, key: str, document_id: UUID, status_code: int, body: dict
) -> None:
    db.add(
        IdempotencyKey(
            company_id=company_id,
            document_id=document_id,
            key=key,
            response_status=status_code,
            response_body=json.dumps(body, default=str),
            expires_at=datetime.now(tz=UTC) + timedelta(hours=settings.IDEMPOTENCY_TTL_HOURS),
        )
    )


# ────────────────────────────────────────────────────────────── construcción


def _build_context(
    document: ElectronicDocument, data: InvoiceCreate, totals: DocumentTotals
) -> DocumentContext:
    company_snapshot = document.company_snapshot
    customer_snapshot = document.customer_snapshot

    supplier = PartyContext(
        document_type="6",
        document_number=company_snapshot.ruc,
        legal_name=company_snapshot.business_name,
        commercial_name=company_snapshot.commercial_name,
        address=company_snapshot.address,
        ubigeo=company_snapshot.ubigeo,
        country_code=company_snapshot.country_code,
    )

    customer = None
    if customer_snapshot is not None:
        customer = PartyContext(
            document_type=customer_snapshot.document_type,
            document_number=customer_snapshot.document_number,
            legal_name=customer_snapshot.name,
            address=customer_snapshot.address,
            ubigeo=customer_snapshot.ubigeo,
            country_code=customer_snapshot.country_code,
        )

    return DocumentContext(
        document_type=INVOICE_TYPE,
        document_id=build_document_id(document.series, document.number),
        issue_date=document.issue_date,
        issue_time=document.issue_time,
        currency=document.currency,
        operation_type=document.operation_type,
        payment_terms=document.payment_terms,
        supplier=supplier,
        customer=customer,
        totals=totals,
        items=[
            ItemContext(
                line_number=item.line_number,
                description=item.description,
                unit_code=item.unit_code.value,
                quantity=item.quantity,
                product_code=item.product_code,
            )
            for item in data.items
        ],
        installments=[
            InstallmentContext(
                number=installment.installment_number,
                due_date=installment.due_date,
                amount=installment.amount,
            )
            for installment in (data.installments or [])
        ],
        amount_in_words=amount_to_words(totals.total, document.currency),
    )


# ─────────────────────────────────────────────────────────────────── emisión


def emit_invoice(
    db: Session,
    company: Company,
    data: InvoiceCreate,
    *,
    idempotency_key: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ElectronicDocument:
    """Emite una factura de principio a fin y devuelve el documento persistido."""
    document_service.validate_issue_date(data.issue_date)

    totals = document_service.compute_totals(data.items)
    document_service.verify_client_totals(data.items, totals)
    document_service.validate_installments(data, totals.total)

    series = series_service.resolve_series(db, company.id, INVOICE_TYPE, data.series)

    # Se validan las credenciales y el certificado ANTES de consumir correlativo:
    # fallar después dejaría un hueco en la numeración por un error de configuración.
    sol_password = company_service.get_sol_password(company)
    certificate_record = certificate_service.get_active_certificate(db, company.id)

    # ── Transacción 1 ────────────────────────────────────────────────────────
    number = series_service.next_number(db, series.id)

    company_snapshot = document_service.create_company_snapshot(db, company)
    customer_snapshot = document_service.create_customer_snapshot(db, data.customer)

    document = document_service.persist_document(
        db,
        company=company,
        series_id=series.id,
        series=series.series,
        number=number,
        document_type=INVOICE_TYPE,
        data=data,
        totals=totals,
        company_snapshot=company_snapshot,
        customer_snapshot=customer_snapshot,
    )

    filename = document_filename(company_snapshot.ruc, INVOICE_TYPE, series.series, number)
    document.filename = filename

    if idempotency_key:
        try:
            # Se guarda el id ya en la reserva: es lo que permite responder al
            # reintento releyendo el documento. Con el cuerpo vacío, el segundo
            # intento no encontraba nada que devolver y chocaba con la
            # restricción única.
            _store_idempotent_response(
                db, company.id, idempotency_key, document.id, 200, {"id": str(document.id)}
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(
                "Ya hay una emisión en curso con esa X-Idempotency-Key.",
                {"idempotency_key": idempotency_key},
            ) from exc
    else:
        db.commit()

    document_id_var.set(str(document.id))
    audit_service.log(
        company.id,
        AuditAction.DOCUMENT_ISSUED,
        document_id=document.id,
        message=f"{filename} generado con total {totals.total}",
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # ── Fuera de transacción: firma ──────────────────────────────────────────
    loaded = certificate_service.load(certificate_record)
    context = _build_context(document, data, totals)
    signed_xml = sign_xml(
        build_invoice(context, igv_rate=settings.IGV_RATE),
        private_key=loaded.private_key,
        certificate=loaded.certificate,
    )
    zip_content = zip_document(filename, signed_xml)

    stored_xml = file_storage_service.save(
        company.id, f"{filename}.xml", signed_xml, reference=document.issue_date
    )

    # ── Transacción 2 ────────────────────────────────────────────────────────
    document.xml_hash = extract_digest_value(signed_xml)
    document.status = DocumentStatus.SIGNED.value
    db.add(
        DocumentFile(
            document_id=document.id,
            file_type=FileType.XML.value,
            storage_path=stored_xml.path,
            filename=stored_xml.filename,
            mime_type=stored_xml.mime_type,
            file_size=stored_xml.size,
            sha256=stored_xml.sha256,
        )
    )
    db.commit()

    audit_service.log(
        company.id,
        AuditAction.DOCUMENT_SIGNED,
        document_id=document.id,
        message=f"XML firmado, digest {document.xml_hash}",
    )

    # ── Fuera de transacción: envío a SUNAT ──────────────────────────────────
    credentials = SunatCredentials(
        ruc=company_snapshot.ruc,
        sol_user=company.sol_user or "",
        sol_password=sol_password,
    )
    submission = SunatSubmission(
        document_id=document.id,
        filename=f"{filename}.zip",
        environment=settings.SUNAT_ENVIRONMENT.value,
        submission_type=SubmissionType.SEND_BILL.value,
        status=SunatStatus.SENT.value,
        sent_at=datetime.now(tz=UTC),
    )

    cdr: CdrResult | None = None
    sunat_error: SunatError | None = None
    try:
        with SunatClient(settings.sunat_url, timeout=settings.SUNAT_TIMEOUT_SECONDS) as client:
            cdr = client.send_bill(credentials, f"{filename}.zip", zip_content)
    except SunatError as exc:
        sunat_error = exc

    # ── Transacción 3 ────────────────────────────────────────────────────────
    document.sent_at = submission.sent_at

    if cdr is not None:
        _apply_cdr(db, document, submission, cdr, company, filename)
        _store_cdr(db, document, cdr, company.id, filename)
    else:
        _apply_failure(document, submission, sunat_error)

    db.add(submission)
    db.commit()
    db.refresh(document)
    return document


def _store_cdr(
    db: Session,
    document: ElectronicDocument,
    cdr: CdrResult,
    company_id: UUID,
    filename: str,
) -> None:
    """Archiva el CDR: es el respaldo de que SUNAT recibió el comprobante.

    Si el guardado falla no se tumba la emisión —el comprobante ya está aceptado
    y ese hecho no se revierte—, pero queda constancia en el log.
    """
    if cdr.raw_xml is None:
        return
    try:
        stored = file_storage_service.save(
            company_id, f"R-{filename}.xml", cdr.raw_xml, reference=document.issue_date
        )
    except Exception:
        logger.exception("no se pudo archivar el CDR", extra={"document_id": str(document.id)})
        return

    db.add(
        DocumentFile(
            document_id=document.id,
            file_type=FileType.CDR.value,
            storage_path=stored.path,
            filename=stored.filename,
            mime_type=stored.mime_type,
            file_size=stored.size,
            sha256=stored.sha256,
        )
    )


def _apply_cdr(
    db: Session,
    document: ElectronicDocument,
    submission: SunatSubmission,
    cdr: CdrResult,
    company: Company,
    filename: str,
) -> None:
    """Traslada la respuesta de SUNAT al documento."""
    document.sunat_code = cdr.response_code
    document.sunat_description = cdr.description[:2000] if cdr.description else None
    submission.sunat_code = cdr.response_code
    submission.sunat_description = document.sunat_description
    submission.responded_at = datetime.now(tz=UTC)

    if cdr.outcome is CdrOutcome.ACCEPTED:
        document.status = DocumentStatus.ACCEPTED.value
        document.sunat_status = SunatStatus.ACCEPTED.value
        document.accepted_at = datetime.now(tz=UTC)
        submission.status = SunatStatus.ACCEPTED.value
        action, audit_status = AuditAction.DOCUMENT_ACCEPTED, AuditStatus.SUCCESS
    elif cdr.outcome is CdrOutcome.ACCEPTED_WITH_OBSERVATION:
        document.status = DocumentStatus.ACCEPTED_WITH_OBSERVATION.value
        document.sunat_status = SunatStatus.ACCEPTED_WITH_OBSERVATION.value
        document.accepted_at = datetime.now(tz=UTC)
        submission.status = SunatStatus.ACCEPTED_WITH_OBSERVATION.value
        action, audit_status = AuditAction.DOCUMENT_ACCEPTED, AuditStatus.WARNING
    else:
        # Rechazo y error del contribuyente son terminales: reenviar el mismo
        # correlativo no arreglaría nada.
        document.status = DocumentStatus.REJECTED.value
        document.sunat_status = SunatStatus.REJECTED.value
        submission.status = SunatStatus.REJECTED.value
        action, audit_status = AuditAction.DOCUMENT_REJECTED, AuditStatus.FAILURE

    audit_service.log(
        company.id,
        action,
        status=audit_status,
        document_id=document.id,
        message=f"{filename}: {cdr.response_code} {cdr.description}",
    )
    logger.info(
        "respuesta de SUNAT aplicada",
        extra={
            "document_id": str(document.id),
            "sunat_code": cdr.response_code,
            "status": document.status,
        },
    )


def _apply_failure(
    document: ElectronicDocument, submission: SunatSubmission, error: SunatError | None
) -> None:
    """SUNAT no respondió o rechazó el transporte.

    El comprobante queda en `SENT` si el fallo es reintentable — ya está firmado
    y puede reenviarse tal cual. Si no lo es, pasa a `ERROR`.
    """
    message = error.message if error else "SUNAT no devolvió una respuesta interpretable."
    retryable = error.retryable if error else True

    submission.last_error = message[:2000]
    submission.sunat_code = error.sunat_code if error else None
    submission.attempts = 1

    if retryable:
        document.status = DocumentStatus.SENT.value
        document.sunat_status = SunatStatus.SENT.value
        submission.status = SunatStatus.SENT.value
        submission.next_attempt_at = datetime.now(tz=UTC) + timedelta(minutes=1)
    else:
        document.status = DocumentStatus.ERROR.value
        document.sunat_status = SunatStatus.ERROR.value
        submission.status = SunatStatus.ERROR.value

    document.sunat_description = message[:2000]
    logger.warning(
        "envío a SUNAT sin respuesta definitiva",
        extra={
            "document_id": str(document.id),
            "retryable": retryable,
            "status": document.status,
        },
    )
