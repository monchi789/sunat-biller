"""Series de comprobantes y asignación de correlativos.

El correlativo es el punto de mayor riesgo de concurrencia del sistema: dos
emisiones simultáneas sobre la misma serie no pueden recibir el mismo número, o
SUNAT rechaza la segunda con "comprobante ya informado".
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.document_series import DocumentSeries

SERIES_PATTERN = re.compile(r"^[A-Z]\d{3}$")

#: Correlativo máximo que admite SUNAT (8 dígitos).
MAX_NUMBER = 99_999_999


def get_series(db: Session, company_id: UUID, series_id: UUID) -> DocumentSeries:
    series = db.execute(
        select(DocumentSeries).where(
            DocumentSeries.id == series_id, DocumentSeries.company_id == company_id
        )
    ).scalar_one_or_none()
    if series is None:
        raise NotFoundError("La serie no existe o no pertenece a la empresa.")
    return series


def find_series(
    db: Session, company_id: UUID, document_type: str, series: str
) -> DocumentSeries:
    found = db.execute(
        select(DocumentSeries).where(
            DocumentSeries.company_id == company_id,
            DocumentSeries.document_type == document_type,
            DocumentSeries.series == series,
        )
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError(
            f"La empresa no tiene la serie {series} para el tipo {document_type}.",
            {"document_type": document_type, "series": series},
        )
    return found


def resolve_series(
    db: Session, company_id: UUID, document_type: str, series: str | None
) -> DocumentSeries:
    """Elige la serie a usar para una emisión.

    Si el cliente no indica serie y la empresa tiene exactamente una activa para
    ese tipo, se usa esa. Con varias, se exige elegir: adivinar aquí produciría
    comprobantes en la serie equivocada de forma silenciosa.
    """
    if series is not None:
        resolved = find_series(db, company_id, document_type, series)
        if not resolved.active:
            raise ConflictError(f"La serie {series} está desactivada.")
        return resolved

    active = list(
        db.execute(
            select(DocumentSeries).where(
                DocumentSeries.company_id == company_id,
                DocumentSeries.document_type == document_type,
                DocumentSeries.active.is_(True),
            )
        ).scalars()
    )

    if not active:
        raise NotFoundError(
            f"La empresa no tiene ninguna serie activa para el tipo {document_type}.",
            {"document_type": document_type},
        )
    if len(active) > 1:
        raise ConflictError(
            f"La empresa tiene {len(active)} series activas para el tipo {document_type}; "
            "indica cuál usar en el campo `series`.",
            {"available": sorted(s.series for s in active)},
        )
    return active[0]


def next_number(db: Session, series_id: UUID) -> int:
    """Reserva el siguiente correlativo de forma atómica.

    **Única excepción a la regla de que los servicios no hacen commit.** El
    `UPDATE ... RETURNING` incrementa y devuelve en una sola sentencia, y el
    commit inmediato libera el bloqueo de fila cuanto antes: mantenerlo hasta el
    final de la emisión serializaría toda la facturación de la serie durante la
    llamada a SUNAT.

    Efecto secundario aceptado: si la emisión falla después, el correlativo queda
    consumido y aparece un hueco. SUNAT no exige continuidad estricta y el hueco
    queda trazado; es preferible a emitir dos comprobantes con el mismo número.
    """
    row = db.execute(
        update(DocumentSeries)
        .where(DocumentSeries.id == series_id, DocumentSeries.active.is_(True))
        .values(current_number=DocumentSeries.current_number + 1)
        .returning(DocumentSeries.current_number)
    ).scalar_one_or_none()

    if row is None:
        db.rollback()
        raise NotFoundError("La serie no existe o está desactivada.")

    if row > MAX_NUMBER:
        db.rollback()
        raise ConflictError(
            f"La serie agotó su rango de numeración (máximo {MAX_NUMBER}).",
            {"series_id": str(series_id)},
        )

    db.commit()
    return int(row)


def create_series(
    db: Session, company_id: UUID, document_type: str, series: str, start_at: int = 0
) -> DocumentSeries:
    if not SERIES_PATTERN.match(series):
        raise ConflictError(
            f"La serie {series!r} no cumple el formato de SUNAT (una letra y tres dígitos).",
        )

    existing = db.execute(
        select(DocumentSeries).where(
            DocumentSeries.company_id == company_id,
            DocumentSeries.document_type == document_type,
            DocumentSeries.series == series,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"La serie {series} ya existe para el tipo {document_type}.")

    created = DocumentSeries(
        company_id=company_id,
        document_type=document_type,
        series=series,
        current_number=start_at,
        active=True,
    )
    db.add(created)
    db.flush()
    return created


def list_series(db: Session, company_id: UUID) -> list[DocumentSeries]:
    return list(
        db.execute(
            select(DocumentSeries)
            .where(DocumentSeries.company_id == company_id)
            .order_by(DocumentSeries.document_type, DocumentSeries.series)
        ).scalars()
    )


def set_active(db: Session, company_id: UUID, series_id: UUID, active: bool) -> DocumentSeries:
    series = get_series(db, company_id, series_id)
    series.active = active
    db.flush()
    return series
