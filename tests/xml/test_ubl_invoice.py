"""Estructura del `Invoice` UBL 2.1 frente a lo que exige SUNAT."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from lxml import etree

from app.domain.tax_engine import ItemInput
from app.xml.context import DocumentContext, InstallmentContext, ItemContext
from app.xml.namespaces import CAC, CBC, cac, cbc, ds, ext
from app.xml.ubl_invoice import build_invoice, render_invoice
from tests.conftest import IGV_RATE
from tests.xml.conftest import SUPPLIER, make_context, make_totals


def tree(ctx: DocumentContext) -> etree._Element:
    return build_invoice(ctx, igv_rate=IGV_RATE)


def text(root: etree._Element, path: str) -> str | None:
    node = root.find(path)
    return node.text if node is not None else None


class TestCabecera:
    def test_version_y_customization(self, simple_invoice: DocumentContext) -> None:
        root = tree(simple_invoice)
        assert text(root, f"./{cbc('UBLVersionID')}") == "2.1"
        assert text(root, f"./{cbc('CustomizationID')}") == "2.0"

    def test_identificador_y_fecha(self, simple_invoice: DocumentContext) -> None:
        root = tree(simple_invoice)
        assert text(root, f"./{cbc('ID')}") == "F001-00000001"
        assert text(root, f"./{cbc('IssueDate')}") == "2024-01-15"
        assert text(root, f"./{cbc('IssueTime')}") == "12:00:00"

    def test_tipo_de_documento_lleva_el_tipo_de_operacion_en_listid(
        self, simple_invoice: DocumentContext
    ) -> None:
        """`listID` es el Catálogo 51 y el valor del nodo el Catálogo 01."""
        node = tree(simple_invoice).find(f"./{cbc('InvoiceTypeCode')}")
        assert node.text == "01"
        assert node.get("listID") == "0101"
        assert node.get("listAgencyName") == "PE:SUNAT"

    def test_importe_en_letras(self, simple_invoice: DocumentContext) -> None:
        node = tree(simple_invoice).find(f"./{cbc('Note')}")
        assert node.text == "SON CIENTO DIECIOCHO CON 00/100 SOLES"
        assert node.get("languageLocaleID") == "1000"

    def test_cuenta_de_lineas(self, simple_invoice: DocumentContext) -> None:
        assert text(tree(simple_invoice), f"./{cbc('LineCountNumeric')}") == "1"

    def test_boleta_usa_tipo_03(self, simple_invoice: DocumentContext) -> None:
        ctx = make_context(simple_invoice.totals, simple_invoice.items,
                           document_type="03", document_id="B001-00000001")
        assert tree(ctx).find(f"./{cbc('InvoiceTypeCode')}").text == "03"


class TestExtensionesYFirma:
    def test_el_placeholder_de_firma_existe_y_esta_vacio(self, simple_invoice: DocumentContext) -> None:
        node = tree(simple_invoice).find(f".//{ext('ExtensionContent')}/{ds('Signature')}")
        assert node is not None
        assert node.get("Id") == "placeholder"
        assert len(node) == 0

    def test_ublextensions_es_el_primer_hijo(self, simple_invoice: DocumentContext) -> None:
        """SUNAT valida el orden de los elementos contra el XSD."""
        assert tree(simple_invoice)[0].tag == ext("UBLExtensions")

    def test_cac_signature_referencia_al_firmante(self, simple_invoice: DocumentContext) -> None:
        root = tree(simple_invoice)
        assert text(root, f"./{cac('Signature')}/{cbc('ID')}") == "SignatureSP"
        ruc = root.find(f"./{cac('Signature')}//{cac('PartyIdentification')}/{cbc('ID')}")
        assert ruc.text == SUPPLIER.document_number
        uri = root.find(f"./{cac('Signature')}//{cbc('URI')}")
        assert uri.text == "#SignatureSP"


class TestPartes:
    def test_emisor(self, simple_invoice: DocumentContext) -> None:
        party = tree(simple_invoice).find(f"./{cac('AccountingSupplierParty')}/{cac('Party')}")
        ruc = party.find(f"./{cac('PartyIdentification')}/{cbc('ID')}")
        assert ruc.text == "20000000001"
        assert ruc.get("schemeID") == "6"
        assert ruc.get("schemeAgencyName") == "PE:SUNAT"
        assert party.find(f".//{cbc('RegistrationName')}").text == "EMPRESA DE PRUEBA SAC"
        assert party.find(f".//{cbc('AddressTypeCode')}").text == "0000"

    def test_receptor(self, simple_invoice: DocumentContext) -> None:
        party = tree(simple_invoice).find(f"./{cac('AccountingCustomerParty')}/{cac('Party')}")
        assert party.find(f"./{cac('PartyIdentification')}/{cbc('ID')}").text == "20512345678"
        assert party.find(f".//{cbc('RegistrationName')}").text == "CLIENTE EMPRESARIAL SAC"

    def test_boleta_a_publico_en_general_omite_el_receptor(
        self, simple_invoice: DocumentContext
    ) -> None:
        ctx = make_context(simple_invoice.totals, simple_invoice.items,
                           document_type="03", customer=None)
        assert tree(ctx).find(f"./{cac('AccountingCustomerParty')}") is None

    def test_receptor_con_dni(self, simple_invoice: DocumentContext) -> None:
        from app.xml.context import PartyContext
        dni = PartyContext(document_type="1", document_number="12345678", legal_name="JUAN PEREZ")
        ctx = make_context(simple_invoice.totals, simple_invoice.items,
                           document_type="03", customer=dni)
        node = tree(ctx).find(f"./{cac('AccountingCustomerParty')}//{cac('PartyIdentification')}/{cbc('ID')}")
        assert node.get("schemeID") == "1"
        assert node.text == "12345678"


class TestFormaDePago:
    def test_contado(self, simple_invoice: DocumentContext) -> None:
        terms = tree(simple_invoice).findall(f"./{cac('PaymentTerms')}")
        assert len(terms) == 1
        assert terms[0].find(f"./{cbc('PaymentMeansID')}").text == "Contado"

    def test_credito_con_cuotas(self, simple_invoice: DocumentContext) -> None:
        ctx = make_context(
            simple_invoice.totals, simple_invoice.items,
            payment_terms="Credito",
            installments=[
                InstallmentContext(1, date(2024, 2, 15), Decimal("59.00")),
                InstallmentContext(2, date(2024, 3, 15), Decimal("59.00")),
            ],
        )
        terms = tree(ctx).findall(f"./{cac('PaymentTerms')}")
        assert len(terms) == 3  # cabecera + 2 cuotas
        assert terms[0].find(f"./{cbc('PaymentMeansID')}").text == "Credito"
        assert terms[0].find(f"./{cbc('Amount')}").text == "118.00"
        assert terms[1].find(f"./{cbc('PaymentMeansID')}").text == "Cuota001"
        assert terms[1].find(f"./{cbc('PaymentDueDate')}").text == "2024-02-15"
        assert terms[2].find(f"./{cbc('PaymentMeansID')}").text == "Cuota002"


class TestTotales:
    def test_tax_total_de_cabecera(self, simple_invoice: DocumentContext) -> None:
        tax_total = tree(simple_invoice).find(f"./{cac('TaxTotal')}")
        assert tax_total.find(f"./{cbc('TaxAmount')}").text == "18.00"
        subtotal = tax_total.find(f"./{cac('TaxSubtotal')}")
        assert subtotal.find(f"./{cbc('TaxableAmount')}").text == "100.00"
        assert subtotal.find(f".//{cbc('ID')}").text == "1000"

    def test_la_cabecera_no_lleva_percent(self, simple_invoice: DocumentContext) -> None:
        """A nivel de cabecera `TaxCategory` solo contiene `TaxScheme`."""
        category = tree(simple_invoice).find(f"./{cac('TaxTotal')}//{cac('TaxCategory')}")
        assert category.find(f"./{cbc('Percent')}") is None

    def test_legal_monetary_total(self, simple_invoice: DocumentContext) -> None:
        node = tree(simple_invoice).find(f"./{cac('LegalMonetaryTotal')}")
        assert node.find(f"./{cbc('LineExtensionAmount')}").text == "100.00"
        assert node.find(f"./{cbc('TaxInclusiveAmount')}").text == "118.00"
        assert node.find(f"./{cbc('PayableAmount')}").text == "118.00"

    def test_descuento_global_solo_si_existe(self, simple_invoice: DocumentContext) -> None:
        node = tree(simple_invoice).find(f"./{cac('LegalMonetaryTotal')}")
        assert node.find(f"./{cbc('AllowanceTotalAmount')}") is None

        totals = make_totals(
            ItemInput(quantity=Decimal(1), tax_affectation="10",
                      unit_value=Decimal("100.00"), discount=Decimal("10.00"))
        )
        ctx = make_context(totals, simple_invoice.items)
        node = tree(ctx).find(f"./{cac('LegalMonetaryTotal')}")
        assert node.find(f"./{cbc('AllowanceTotalAmount')}").text == "10.00"

    def test_todo_importe_lleva_moneda(self, simple_invoice: DocumentContext) -> None:
        root = tree(simple_invoice)
        for tag in ("LineExtensionAmount", "TaxInclusiveAmount", "PayableAmount", "TaxAmount"):
            for node in root.findall(f".//{cbc(tag)}"):
                assert node.get("currencyID") == "PEN", tag


class TestLineas:
    def test_estructura_de_linea(self, simple_invoice: DocumentContext) -> None:
        line = tree(simple_invoice).find(f"./{cac('InvoiceLine')}")
        assert line.find(f"./{cbc('ID')}").text == "1"
        assert line.find(f"./{cbc('InvoicedQuantity')}").get("unitCode") == "ZZ"
        assert line.find(f"./{cbc('LineExtensionAmount')}").text == "100.00"
        assert line.find(f".//{cac('Item')}/{cbc('Description')}").text == "SERVICIO DE CONSULTORIA"
        assert line.find(f"./{cac('Price')}/{cbc('PriceAmount')}").text == "100.00"

    def test_precio_de_referencia_con_igv(self, simple_invoice: DocumentContext) -> None:
        line = tree(simple_invoice).find(f"./{cac('InvoiceLine')}")
        alternative = line.find(f".//{cac('AlternativeConditionPrice')}")
        assert alternative.find(f"./{cbc('PriceAmount')}").text == "118.00"
        assert alternative.find(f"./{cbc('PriceTypeCode')}").text == "01"

    def test_los_importes_unitarios_nunca_salen_sin_decimales(self) -> None:
        """`59` en vez de `59.00` es rechazo directo de SUNAT."""
        totals = make_totals(
            ItemInput(quantity=Decimal(2), tax_affectation="10", unit_value=Decimal("50.00"))
        )
        ctx = make_context(totals, [ItemContext(1, "X", "NIU", Decimal(2))])
        for node in tree(ctx).findall(f".//{cbc('PriceAmount')}"):
            assert "." in node.text, f"PriceAmount sin decimales: {node.text}"

    def test_codigo_de_producto_es_opcional(self, simple_invoice: DocumentContext) -> None:
        ctx = make_context(simple_invoice.totals, [ItemContext(1, "SIN CODIGO", "NIU", Decimal(1))])
        assert tree(ctx).find(f".//{cac('SellersItemIdentification')}") is None


class TestPorcentajeDeImpuesto:
    """`Percent` debe ser la tasa aplicada, no el 18 % genérico."""

    @pytest.mark.parametrize(
        ("affectation", "percent"),
        [("10", "18.00"), ("20", "0.00"), ("30", "0.00"), ("40", "0.00"), ("15", "18.00")],
    )
    def test_percent_por_afectacion(self, affectation: str, percent: str) -> None:
        totals = make_totals(
            ItemInput(quantity=Decimal(1), tax_affectation=affectation, unit_value=Decimal("100.00"))
        )
        ctx = make_context(totals, [ItemContext(1, "X", "NIU", Decimal(1))])
        line = tree(ctx).find(f"./{cac('InvoiceLine')}")
        assert line.find(f".//{cac('TaxCategory')}/{cbc('Percent')}").text == percent

    def test_la_afectacion_viaja_en_tax_exemption_reason_code(self) -> None:
        totals = make_totals(
            ItemInput(quantity=Decimal(1), tax_affectation="20", unit_value=Decimal("100.00"))
        )
        ctx = make_context(totals, [ItemContext(1, "X", "NIU", Decimal(1))])
        line = tree(ctx).find(f"./{cac('InvoiceLine')}")
        assert line.find(f".//{cbc('TaxExemptionReasonCode')}").text == "20"


class TestSerializacion:
    def test_declaracion_xml_y_encoding(self, simple_invoice: DocumentContext) -> None:
        xml = render_invoice(simple_invoice, igv_rate=IGV_RATE)
        assert xml.startswith(b"<?xml version='1.0' encoding='UTF-8'")

    def test_namespaces_declarados_en_la_raiz(self, simple_invoice: DocumentContext) -> None:
        nsmap = tree(simple_invoice).nsmap
        assert nsmap[None] == "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
        assert nsmap["cac"] == CAC
        assert nsmap["cbc"] == CBC
        assert "ds" in nsmap

    def test_es_determinista(self, simple_invoice: DocumentContext) -> None:
        """Sin determinismo, la firma no es reproducible y los golden fallan."""
        first = render_invoice(simple_invoice, igv_rate=IGV_RATE)
        second = render_invoice(simple_invoice, igv_rate=IGV_RATE)
        assert first == second
