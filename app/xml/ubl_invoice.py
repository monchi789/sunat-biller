"""Builder del `Invoice` UBL 2.1 — sirve para Factura (01) y Boleta (03).

Sigue el árbol de `docs/GUIA_PROYECTO.md` §6.2. Los atributos de catálogo
(`listID`, `listAgencyName`, `schemeURI`…) no son adorno: SUNAT los valida contra
el XSD y el rechazo resultante es poco descriptivo.
"""

from __future__ import annotations

from decimal import Decimal

from lxml import etree

from app.catalogs.tax_schemes import TaxSchemeInfo
from app.domain.money import ZERO, fmt2, fmt6, fmt_price
from app.domain.tax_engine import ItemComputation, TaxSubtotal
from app.xml.context import DocumentContext, ItemContext, PartyContext
from app.xml.namespaces import CAC, CBC, EXT, INVOICE, cac, cbc, ext, nsmap
from app.xml.xml_signer import build_signature_placeholder

# Atributos de catálogo que SUNAT exige en cada nodo codificado.
_CAT01 = {
    "listAgencyName": "PE:SUNAT",
    "listName": "Tipo de Documento",
    "listURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo01",
}
_CAT06 = {
    "schemeName": "Documento de Identidad",
    "schemeAgencyName": "PE:SUNAT",
    "schemeURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo06",
}
_CAT16 = {
    "listName": "Tipo de Precio",
    "listAgencyName": "PE:SUNAT",
    "listURI": "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo16",
}
_CURRENCY = {
    "listID": "ISO 4217 Alpha",
    "listName": "Currency",
    "listAgencyName": "United Nations Economic Commission for Europe",
}
_UNIT = {
    "unitCodeListID": "UN/ECE rec 20",
    "unitCodeListAgencyName": "United Nations Economic Commission for Europe",
}


def _sub(parent: etree._Element, tag: str, text: str | None = None, **attrs: str) -> etree._Element:
    element = etree.SubElement(parent, tag, **attrs)
    if text is not None:
        element.text = text
    return element


def _amount(parent: etree._Element, tag: str, value: Decimal, currency: str) -> etree._Element:
    return _sub(parent, tag, fmt2(value), currencyID=currency)


# ────────────────────────────────────────────────────────────── bloques


def build_ubl_extensions(root: etree._Element) -> None:
    """`ext:UBLExtensions` con el hueco donde signxml pondrá la firma."""
    extensions = _sub(root, ext("UBLExtensions"))
    extension = _sub(extensions, ext("UBLExtension"))
    content = _sub(extension, ext("ExtensionContent"))
    build_signature_placeholder(content)


def build_signature_block(root: etree._Element, ctx: DocumentContext) -> None:
    """`cac:Signature` — referencia a la firma y datos del firmante."""
    signature = _sub(root, cac("Signature"))
    _sub(signature, cbc("ID"), ctx.signature_id)

    party = _sub(signature, cac("SignatoryParty"))
    identification = _sub(party, cac("PartyIdentification"))
    _sub(identification, cbc("ID"), ctx.supplier.document_number)
    name = _sub(party, cac("PartyName"))
    _sub(name, cbc("Name"), ctx.supplier.legal_name)

    attachment = _sub(signature, cac("DigitalSignatureAttachment"))
    reference = _sub(attachment, cac("ExternalReference"))
    _sub(reference, cbc("URI"), f"#{ctx.signature_id}")


def build_supplier(root: etree._Element, supplier: PartyContext) -> None:
    accounting = _sub(root, cac("AccountingSupplierParty"))
    party = _sub(accounting, cac("Party"))

    identification = _sub(party, cac("PartyIdentification"))
    _sub(identification, cbc("ID"), supplier.document_number, schemeID=supplier.document_type, **_CAT06)

    if supplier.commercial_name:
        name = _sub(party, cac("PartyName"))
        _sub(name, cbc("Name"), supplier.commercial_name)

    legal_entity = _sub(party, cac("PartyLegalEntity"))
    _sub(legal_entity, cbc("RegistrationName"), supplier.legal_name)

    address = _sub(legal_entity, cac("RegistrationAddress"))
    if supplier.ubigeo:
        _sub(address, cbc("ID"), supplier.ubigeo)
    _sub(address, cbc("AddressTypeCode"), "0000")  # domicilio fiscal
    if supplier.district:
        _sub(address, cbc("CitySubdivisionName"), supplier.district)
    if supplier.province:
        _sub(address, cbc("CityName"), supplier.province)
    if supplier.department:
        _sub(address, cbc("CountrySubentity"), supplier.department)
    if supplier.address:
        line = _sub(address, cac("AddressLine"))
        _sub(line, cbc("Line"), supplier.address)
    country = _sub(address, cac("Country"))
    _sub(country, cbc("IdentificationCode"), supplier.country_code)


def build_customer(root: etree._Element, customer: PartyContext) -> None:
    accounting = _sub(root, cac("AccountingCustomerParty"))
    party = _sub(accounting, cac("Party"))

    identification = _sub(party, cac("PartyIdentification"))
    _sub(identification, cbc("ID"), customer.document_number, schemeID=customer.document_type, **_CAT06)

    legal_entity = _sub(party, cac("PartyLegalEntity"))
    _sub(legal_entity, cbc("RegistrationName"), customer.legal_name)

    if customer.address or customer.ubigeo:
        address = _sub(legal_entity, cac("RegistrationAddress"))
        if customer.ubigeo:
            _sub(address, cbc("ID"), customer.ubigeo)
        if customer.address:
            line = _sub(address, cac("AddressLine"))
            _sub(line, cbc("Line"), customer.address)
        country = _sub(address, cac("Country"))
        _sub(country, cbc("IdentificationCode"), customer.country_code)


def build_payment_terms(root: etree._Element, ctx: DocumentContext) -> None:
    """`cac:PaymentTerms` — al contado una sola entrada; a crédito, total + cuotas."""
    if not ctx.is_credit:
        terms = _sub(root, cac("PaymentTerms"))
        _sub(terms, cbc("ID"), "FormaPago")
        _sub(terms, cbc("PaymentMeansID"), "Contado")
        return

    header = _sub(root, cac("PaymentTerms"))
    _sub(header, cbc("ID"), "FormaPago")
    _sub(header, cbc("PaymentMeansID"), "Credito")
    _amount(header, cbc("Amount"), ctx.totals.total, ctx.currency)

    for installment in ctx.installments:
        terms = _sub(root, cac("PaymentTerms"))
        _sub(terms, cbc("ID"), "FormaPago")
        _sub(terms, cbc("PaymentMeansID"), f"Cuota{installment.number:03d}")
        _amount(terms, cbc("Amount"), installment.amount, ctx.currency)
        _sub(terms, cbc("PaymentDueDate"), installment.due_date.isoformat())


def _tax_scheme(parent: etree._Element, scheme: TaxSchemeInfo) -> None:
    node = _sub(parent, cac("TaxScheme"))
    _sub(node, cbc("ID"), scheme.scheme_id)
    _sub(node, cbc("Name"), scheme.scheme_name)
    _sub(node, cbc("TaxTypeCode"), scheme.tax_type_code)


def build_header_tax_total(root: etree._Element, ctx: DocumentContext) -> None:
    """`cac:TaxTotal` de cabecera. A este nivel `TaxCategory` solo lleva `TaxScheme`."""
    totals = ctx.totals
    tax_total = _sub(root, cac("TaxTotal"))
    _amount(tax_total, cbc("TaxAmount"), totals.tax_amount_total, ctx.currency)

    for subtotal in totals.tax_subtotals:
        _build_header_subtotal(tax_total, subtotal, ctx.currency)


def _build_header_subtotal(parent: etree._Element, subtotal: TaxSubtotal, currency: str) -> None:
    node = _sub(parent, cac("TaxSubtotal"))
    _amount(node, cbc("TaxableAmount"), subtotal.taxable_amount, currency)
    _amount(node, cbc("TaxAmount"), subtotal.tax_amount, currency)
    category = _sub(node, cac("TaxCategory"))
    _tax_scheme(category, subtotal.scheme)


def build_legal_monetary_total(root: etree._Element, ctx: DocumentContext) -> None:
    totals = ctx.totals
    node = _sub(root, cac("LegalMonetaryTotal"))
    _amount(node, cbc("LineExtensionAmount"), totals.subtotal, ctx.currency)
    _amount(node, cbc("TaxInclusiveAmount"), totals.tax_inclusive_amount, ctx.currency)
    if totals.discount_total > 0:
        _amount(node, cbc("AllowanceTotalAmount"), totals.discount_total, ctx.currency)
    _amount(node, cbc("PayableAmount"), totals.total, ctx.currency)


def build_line(
    root: etree._Element,
    item: ItemContext,
    computation: ItemComputation,
    currency: str,
    igv_rate: Decimal,
    *,
    tag: str,
    quantity_tag: str,
) -> None:
    """Una línea de detalle. `tag`/`quantity_tag` varían entre Invoice, CreditNote y DebitNote."""
    line = _sub(root, tag)
    _sub(line, cbc("ID"), str(item.line_number))
    _sub(line, quantity_tag, fmt6(item.quantity), unitCode=item.unit_code, **_UNIT)
    _amount(line, cbc("LineExtensionAmount"), computation.line_extension_amount, currency)

    # Precio de venta unitario (con IGV) o valor referencial si es gratuita.
    pricing = _sub(line, cac("PricingReference"))
    alternative = _sub(pricing, cac("AlternativeConditionPrice"))
    _sub(alternative, cbc("PriceAmount"), fmt_price(computation.unit_price), currencyID=currency)
    _sub(alternative, cbc("PriceTypeCode"), computation.price_type, **_CAT16)

    _build_line_tax_total(line, computation, currency, igv_rate)

    item_node = _sub(line, cac("Item"))
    _sub(item_node, cbc("Description"), item.description)
    if item.product_code:
        identification = _sub(item_node, cac("SellersItemIdentification"))
        _sub(identification, cbc("ID"), item.product_code)

    price = _sub(line, cac("Price"))
    _sub(price, cbc("PriceAmount"), fmt_price(computation.unit_value), currencyID=currency)


def _build_line_tax_total(
    line: etree._Element, computation: ItemComputation, currency: str, igv_rate: Decimal
) -> None:
    """A nivel de línea, `TaxCategory` sí lleva `Percent` y la afectación."""
    total_tax = computation.igv_amount + computation.isc_amount + computation.icbper_amount
    tax_total = _sub(line, cac("TaxTotal"))
    _amount(tax_total, cbc("TaxAmount"), total_tax, currency)

    subtotal = _sub(tax_total, cac("TaxSubtotal"))
    _amount(subtotal, cbc("TaxableAmount"), computation.taxable_amount, currency)
    _amount(subtotal, cbc("TaxAmount"), computation.igv_amount, currency)

    category = _sub(subtotal, cac("TaxCategory"))
    # `Percent` es la tasa **efectivamente aplicada**, no la del IGV genérico:
    # 18.00 solo en la familia gravada (categoría "S", incluidas las gratuitas de
    # origen gravado). Exoneradas, inafectas y exportación declaran 0.00; poner
    # 18.00 ahí es un rechazo 2xxx.
    percent = igv_rate * 100 if computation.scheme.category_id == "S" else ZERO
    _sub(category, cbc("Percent"), fmt2(percent))
    _sub(category, cbc("TaxExemptionReasonCode"), computation.tax_affectation)
    _tax_scheme(category, computation.scheme)


# ────────────────────────────────────────────────────────────── documento


def build_invoice(ctx: DocumentContext, *, igv_rate: Decimal) -> etree._Element:
    """Construye el árbol del `Invoice`, con el placeholder de firma listo."""
    root = etree.Element(f"{{{INVOICE}}}Invoice", nsmap=nsmap(INVOICE))

    build_ubl_extensions(root)

    _sub(root, cbc("UBLVersionID"), "2.1")
    _sub(root, cbc("CustomizationID"), "2.0")
    _sub(root, cbc("ID"), ctx.document_id)
    _sub(root, cbc("IssueDate"), ctx.issue_date.isoformat())
    if ctx.issue_time is not None:
        _sub(root, cbc("IssueTime"), ctx.issue_time.isoformat())
    _sub(root, cbc("InvoiceTypeCode"), ctx.document_type, listID=ctx.operation_type, **_CAT01)
    _sub(root, cbc("Note"), ctx.amount_in_words, languageLocaleID="1000")
    _sub(root, cbc("DocumentCurrencyCode"), ctx.currency, **_CURRENCY)
    _sub(root, cbc("LineCountNumeric"), str(len(ctx.items)))

    build_signature_block(root, ctx)
    build_supplier(root, ctx.supplier)
    if ctx.customer is not None:
        build_customer(root, ctx.customer)
    build_payment_terms(root, ctx)
    build_header_tax_total(root, ctx)
    build_legal_monetary_total(root, ctx)

    for item, computation in zip(ctx.items, ctx.totals.items, strict=True):
        build_line(
            root, item, computation, ctx.currency, igv_rate,
            tag=cac("InvoiceLine"), quantity_tag=cbc("InvoicedQuantity"),
        )

    return root


def render_invoice(ctx: DocumentContext, *, igv_rate: Decimal) -> bytes:
    """Serializa el `Invoice` **sin firmar**. Útil para golden tests."""
    return etree.tostring(
        build_invoice(ctx, igv_rate=igv_rate),
        xml_declaration=True, encoding="UTF-8", standalone=False, pretty_print=True,
    )


__all__ = ["CAC", "CBC", "EXT", "build_invoice", "render_invoice"]
