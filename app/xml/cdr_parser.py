"""Parseo del CDR (Constancia de Recepción) que devuelve SUNAT.

El CDR es un `ApplicationResponse` UBL. Se parsea con `local-name()` en lugar de
namespaces fijos porque los prefijos y hasta el namespace del documento raíz
varían entre el ambiente beta, producción y los OSE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from lxml import etree

from app.catalogs.cdr_codes import CdrOutcome, classify_cdr_code
from app.core.errors import SunatError


@dataclass(frozen=True, slots=True)
class CdrResult:
    """Respuesta de SUNAT ya interpretada."""

    response_code: str
    description: str
    outcome: CdrOutcome
    reference_id: str | None = None
    notes: list[str] = field(default_factory=list)
    """Observaciones (códigos 4xxx). El comprobante se acepta igual."""

    @property
    def is_accepted(self) -> bool:
        return self.outcome in (CdrOutcome.ACCEPTED, CdrOutcome.ACCEPTED_WITH_OBSERVATION)

    @property
    def has_observations(self) -> bool:
        return self.outcome is CdrOutcome.ACCEPTED_WITH_OBSERVATION or bool(self.notes)


def _elements(node: etree._Element, local_name: str) -> list[etree._Element]:
    """`xpath` declara una unión (bool | float | str | list); acá siempre es lista."""
    return cast("list[etree._Element]", node.xpath(f".//*[local-name()='{local_name}']"))


def _first_text(node: etree._Element, local_name: str) -> str | None:
    for element in _elements(node, local_name):
        if element.text and element.text.strip():
            return element.text.strip()
    return None


def _all_texts(node: etree._Element, local_name: str) -> list[str]:
    return [
        element.text.strip()
        for element in _elements(node, local_name)
        if element.text and element.text.strip()
    ]


def parse_cdr(cdr_xml: bytes) -> CdrResult:
    """Interpreta el XML del CDR.

    :raises SunatError: si el XML no es parseable o no trae `ResponseCode`.
    """
    try:
        root = etree.fromstring(cdr_xml)
    except etree.XMLSyntaxError as exc:
        raise SunatError(f"El CDR no es un XML válido: {exc}", retryable=False) from exc

    response_code = _first_text(root, "ResponseCode")
    if response_code is None:
        raise SunatError("El CDR no contiene cbc:ResponseCode.", retryable=False)

    description = _first_text(root, "Description") or ""
    reference_id = _first_text(root, "ReferenceID")

    # Las observaciones vienen en cbc:Note del ApplicationResponse.
    notes = _all_texts(root, "Note")

    return CdrResult(
        response_code=response_code,
        description=description,
        outcome=classify_cdr_code(response_code),
        reference_id=reference_id,
        notes=notes,
    )
