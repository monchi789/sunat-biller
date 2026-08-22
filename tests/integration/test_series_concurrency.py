"""Concurrencia del correlativo — el test de integración más valioso de la suite.

RF-03.4 y RNF-02.2. Dos emisiones simultáneas sobre la misma serie no pueden
recibir el mismo número: SUNAT rechazaría la segunda con "ya fue informado" y el
comprobante quedaría emitido sin poder declararse.

Estos tests trabajan con datos **comprometidos**, no con el `db` transaccional:
los hilos abren sus propias sesiones y necesitan ver la serie realmente escrita.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ConflictError, NotFoundError
from app.models.company import Company
from app.models.document_series import DocumentSeries
from app.services import series_service
from tests.integration.conftest import requires_db

pytestmark = [pytest.mark.db, requires_db]

THREADS = 20
PER_THREAD = 5


@pytest.fixture
def company_id(session_factory: sessionmaker[Session]) -> Generator[uuid.UUID]:
    """Empresa persistida. Devuelve solo el id: mantener una sesión abierta
    durante el test bloquearía la limpieza posterior."""
    with session_factory() as session:
        company = Company(
            ruc=f"20{uuid.uuid4().int % 1_000_000_000:09d}",
            business_name="EMPRESA CONCURRENTE SAC",
            address="AV. TEST 100",
            ubigeo="150101",
            country_code="PE",
        )
        session.add(company)
        session.commit()
        created = company.id

    yield created

    with session_factory() as session:
        session.execute(sa.delete(DocumentSeries).where(DocumentSeries.company_id == created))
        session.execute(sa.delete(Company).where(Company.id == created))
        session.commit()


@pytest.fixture
def series_id(session_factory: sessionmaker[Session], company_id: uuid.UUID) -> uuid.UUID:
    with session_factory() as session:
        series = series_service.create_series(session, company_id, "01", "F001")
        session.commit()
        return series.id


class TestCorrelativoAtomico:
    def test_incrementa_de_uno_en_uno(
        self, session_factory: sessionmaker[Session], series_id: uuid.UUID
    ) -> None:
        with session_factory() as session:
            numbers = [series_service.next_number(session, series_id) for _ in range(5)]
        assert numbers == [1, 2, 3, 4, 5]

    def test_sin_duplicados_bajo_concurrencia(
        self, session_factory: sessionmaker[Session], series_id: uuid.UUID
    ) -> None:
        """20 hilos × 5 emisiones = 100 correlativos distintos, sin huecos."""

        def reserve(_: int) -> list[int]:
            with session_factory() as session:
                return [series_service.next_number(session, series_id) for _ in range(PER_THREAD)]

        with ThreadPoolExecutor(max_workers=THREADS) as pool:
            results = [n for batch in pool.map(reserve, range(THREADS)) for n in batch]

        total = THREADS * PER_THREAD
        assert len(results) == total
        assert len(set(results)) == total, "se repitió algún correlativo"
        assert sorted(results) == list(range(1, total + 1)), "quedaron huecos en la numeración"

    def test_la_serie_queda_consistente(
        self, session_factory: sessionmaker[Session], series_id: uuid.UUID
    ) -> None:
        def reserve(_: int) -> None:
            with session_factory() as session:
                series_service.next_number(session, series_id)

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(reserve, range(50)))

        with session_factory() as session:
            assert session.get(DocumentSeries, series_id).current_number == 50


class TestValidaciones:
    def test_serie_desactivada_no_entrega_numero(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        """Evita seguir numerando sobre una serie dada de baja."""
        with session_factory() as session:
            series_service.set_active(session, company_id, series_id, active=False)
            session.commit()

        with session_factory() as session, pytest.raises(NotFoundError):
            series_service.next_number(session, series_id)

    def test_serie_inexistente(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session, pytest.raises(NotFoundError):
            series_service.next_number(session, uuid.uuid4())


class TestResolucionDeSerie:
    def test_usa_la_unica_serie_activa(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        with session_factory() as session:
            assert series_service.resolve_series(session, company_id, "01", None).id == series_id

    def test_exige_elegir_si_hay_varias(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        """Adivinar aquí emitiría en la serie equivocada sin avisar."""
        with session_factory() as session:
            series_service.create_series(session, company_id, "01", "F002")
            session.commit()

        with session_factory() as session, pytest.raises(ConflictError, match="indica cuál usar"):
            series_service.resolve_series(session, company_id, "01", None)

    def test_usa_la_serie_indicada(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        with session_factory() as session:
            assert series_service.resolve_series(session, company_id, "01", "F001").id == series_id

    def test_serie_desactivada_no_se_puede_elegir(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        with session_factory() as session:
            series_service.set_active(session, company_id, series_id, active=False)
            session.commit()

        with session_factory() as session, pytest.raises(ConflictError, match="desactivada"):
            series_service.resolve_series(session, company_id, "01", "F001")

    def test_sin_series_activas(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID
    ) -> None:
        with session_factory() as session, pytest.raises(NotFoundError, match="ninguna serie activa"):
            series_service.resolve_series(session, company_id, "07", None)


class TestCreacion:
    def test_formato_de_serie_invalido(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID
    ) -> None:
        with session_factory() as session, pytest.raises(ConflictError, match="formato"):
            series_service.create_series(session, company_id, "01", "FF01")

    def test_no_admite_series_duplicadas(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        with session_factory() as session, pytest.raises(ConflictError, match="ya existe"):
            series_service.create_series(session, company_id, "01", "F001")

    def test_misma_serie_distinto_tipo_es_valido(
        self, session_factory: sessionmaker[Session], company_id: uuid.UUID, series_id: uuid.UUID
    ) -> None:
        """`F001` de factura y `F001` de nota de crédito son series distintas."""
        with session_factory() as session:
            created = series_service.create_series(session, company_id, "07", "F001")
            session.commit()
            assert created.id != series_id
