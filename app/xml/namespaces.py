"""Namespaces UBL 2.1 y extensiones SUNAT.

Nota sobre `pe-cac`: RNF-05.1 de la guía lo menciona, pero ese prefijo pertenece
al perfil **UBL 2.0** de SUNAT (`.../peru/schema/xsd/SunatAggregateComponents-1`
se declaraba junto a `pe-cac` en los documentos antiguos). En el perfil UBL 2.1
vigente solo se usa `sac`; no se declara `pe-cac` para no ensuciar el documento
con un namespace no utilizado, que además altera la canonicalización.
"""

from __future__ import annotations

from typing import Final

# ── UBL 2.1 — documentos raíz ───────────────────────────────────────────────
INVOICE: Final = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CREDIT_NOTE: Final = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
DEBIT_NOTE: Final = "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2"

# ── UBL 2.1 — componentes comunes ───────────────────────────────────────────
CAC: Final = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC: Final = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
EXT: Final = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"

# ── Firma digital ───────────────────────────────────────────────────────────
DS: Final = "http://www.w3.org/2000/09/xmldsig#"

# ── Extensiones SUNAT ───────────────────────────────────────────────────────
SAC: Final = "urn:sunat:names:specification:ubl:peru:schema:xsd:SunatAggregateComponents-1"

# ── Resúmenes (RC y RA) ─────────────────────────────────────────────────────
SUMMARY_DOCUMENTS: Final = "urn:sunat:names:specification:ubl:peru:schema:xsd:SummaryDocuments-1"
VOIDED_DOCUMENTS: Final = "urn:sunat:names:specification:ubl:peru:schema:xsd:VoidedDocuments-1"


def nsmap(root_namespace: str, *, include_sac: bool = False) -> dict[str | None, str]:
    """Mapa de prefijos para el elemento raíz de un documento.

    El namespace del documento va sin prefijo (default) y el resto con el prefijo
    que SUNAT espera. `ds` se declara siempre porque el hueco de la firma vive en
    `ext:ExtensionContent` desde la construcción del documento.
    """
    mapping: dict[str | None, str] = {
        None: root_namespace,
        "cac": CAC,
        "cbc": CBC,
        "ext": EXT,
        "ds": DS,
    }
    if include_sac:
        mapping["sac"] = SAC
    return mapping


def qname(namespace: str, tag: str) -> str:
    """Nombre cualificado en la sintaxis de `lxml`: `{namespace}tag`."""
    return f"{{{namespace}}}{tag}"


def cbc(tag: str) -> str:
    return qname(CBC, tag)


def cac(tag: str) -> str:
    return qname(CAC, tag)


def ext(tag: str) -> str:
    return qname(EXT, tag)


def ds(tag: str) -> str:
    return qname(DS, tag)


def sac(tag: str) -> str:
    return qname(SAC, tag)
