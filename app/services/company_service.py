"""Alta y mantenimiento de empresas emisoras (RF-01)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanySunatCredentialsUpdate, CompanyUpdate
from app.services import crypto_service


def _active(statement):
    """Filtra los borrados lógicos.

    `SoftDeleteMixin` no aplica el filtro por sí solo; centralizarlo aquí evita
    que se olvide en alguna consulta y se expongan empresas dadas de baja.
    """
    return statement.where(Company.deleted_at.is_(None))


def get_company(db: Session, company_id: UUID) -> Company:
    company = db.execute(
        _active(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise NotFoundError("La empresa no existe.")
    return company


def get_by_ruc(db: Session, ruc: str) -> Company | None:
    return db.execute(_active(select(Company).where(Company.ruc == ruc))).scalar_one_or_none()


def create_company(db: Session, data: CompanyCreate) -> Company:
    if get_by_ruc(db, data.ruc) is not None:
        raise ConflictError(f"Ya existe una empresa con RUC {data.ruc}.", {"ruc": data.ruc})

    company = Company(**data.model_dump())
    db.add(company)
    db.flush()
    return company


def update_company(db: Session, company_id: UUID, data: CompanyUpdate) -> Company:
    company = get_company(db, company_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.flush()
    return company


def delete_company(db: Session, company_id: UUID) -> None:
    """Baja lógica: se conserva la trazabilidad de lo ya emitido (RNF-03.4)."""
    get_company(db, company_id).soft_delete()
    db.flush()


def update_sunat_credentials(
    db: Session, company_id: UUID, data: CompanySunatCredentialsUpdate
) -> Company:
    """Guarda las credenciales SOL con la contraseña cifrada (RNF-01.3).

    En el ambiente BETA de SUNAT el usuario es `MODDATOS` con clave `moddatos`,
    y el cliente SOAP concatena el RUC por delante (`{RUC}MODDATOS`).
    """
    company = get_company(db, company_id)
    company.sol_user = data.sol_user
    company.sol_password_secret = crypto_service.encrypt(data.sol_password)
    db.flush()
    return company


def get_sol_password(company: Company) -> str:
    """Descifra la clave SOL para el envío. Nunca sale por la API."""
    if not company.sol_user or not company.sol_password_secret:
        raise ConflictError(
            "La empresa no tiene credenciales SOL configuradas. "
            "Cárgalas en PATCH /companies/{id}/sunat-credentials antes de emitir.",
            {"company_id": str(company.id)},
        )
    return crypto_service.decrypt(company.sol_password_secret)


def list_companies(db: Session, *, offset: int, limit: int) -> tuple[list[Company], int]:
    total = db.execute(_active(select(func.count(Company.id)))).scalar_one()
    companies = list(
        db.execute(
            _active(select(Company)).order_by(Company.created_at.desc()).offset(offset).limit(limit)
        ).scalars()
    )
    return companies, total
