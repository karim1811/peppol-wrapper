from datetime import date, timedelta
import xml.etree.ElementTree as ET
from schemas import InvoiceRequest

NS_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
NS_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
NS_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

ET.register_namespace("", NS_INVOICE)
ET.register_namespace("cac", NS_CAC)
ET.register_namespace("cbc", NS_CBC)


def _add(parent, tag, text=None, attrib=None):
    if attrib is None:
        attrib = {}
    el = ET.SubElement(parent, tag, attrib)
    if text is not None:
        el.text = str(text)
    return el


def build_ubl_invoice( InvoiceRequest) -> bytes:
    invoice = ET.Element(f"{{{NS_INVOICE}}}Invoice")

    _add(invoice, f"{{{NS_CBC}}}CustomizationID", "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0")
    _add(invoice, f"{{{NS_CBC}}}ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    _add(invoice, f"{{{NS_CBC}}}ID", data.invoice_number)
    _add(invoice, f"{{{NS_CBC}}}IssueDate", data.issue_date)
    due = data.due_date or (date.fromisoformat(data.issue_date) + timedelta(days=30)).isoformat()
    _add(invoice, f"{{{NS_CBC}}}DueDate", due)
    _add(invoice, f"{{{NS_CBC}}}InvoiceTypeCode", "380")
    _add(invoice, f"{{{NS_CBC}}}DocumentCurrencyCode", data.currency)
    _add(invoice, f"{{{NS_CBC}}}BuyerReference", data.buyer_reference)

    supplier = _add(invoice, f"{{{NS_CAC}}}AccountingSupplierParty")
    supplier_party = _add(supplier, f"{{{NS_CAC}}}Party")
    _add(supplier_party, f"{{{NS_CBC}}}EndpointID", data.seller.endpoint_id, {"schemeID": data.seller.endpoint_scheme})
    supplier_name = _add(supplier_party, f"{{{NS_CAC}}}PartyName")
    _add(supplier_name, f"{{{NS_CBC}}}Name", data.seller.name)
    s_addr = _add(supplier_party, f"{{{NS_CAC}}}PostalAddress")
    _add(s_addr, f"{{{NS_CBC}}}StreetName", data.seller.street)
    _add(s_addr, f"{{{NS_CBC}}}CityName", data.seller.city)
    _add(s_addr, f"{{{NS_CBC}}}PostalZone", data.seller.postal_code)
    s_country = _add(s_addr, f"{{{NS_CAC}}}Country")
    _add(s_country, f"{{{NS_CBC}}}IdentificationCode", data.seller.country_code)
    s_legal = _add(supplier_party, f"{{{NS_CAC}}}PartyLegalEntity")
    _add(s_legal, f"{{{NS_CBC}}}RegistrationName", data.seller.name)
    _add(s_legal, f"{{{NS_CBC}}}CompanyID", data.seller.legal_id, {"schemeID": data.seller.legal_id_scheme})

    customer = _add(invoice, f"{{{NS_CAC}}}AccountingCustomerParty")
    customer_party = _add(customer, f"{{{NS_CAC}}}Party")
    _add(customer_party, f"{{{NS_CBC}}}EndpointID", data.buyer.endpoint_id, {"schemeID": data.buyer.endpoint_scheme})
    customer_name = _add(customer_party, f"{{{NS_CAC}}}PartyName")
    _add(customer_name, f"{{{NS_CBC}}}Name", data.buyer.name)
    b_addr = _add(customer_party, f"{{{NS_CAC}}}PostalAddress")
    _add(b_addr, f"{{{NS_CBC}}}StreetName", data.buyer.street)
    _add(b_addr, f"{{{NS_CBC}}}CityName", data.buyer.city)
    _add(b_addr, f"{{{NS_CBC}}}PostalZone", data.buyer.postal_code)
    b_country = _add(b_addr, f"{{{NS_CAC}}}Country")
    _add(b_country, f"{{{NS_CBC}}}IdentificationCode", data.buyer.country_code)
    b_legal = _add(customer_party, f"{{{NS_CAC}}}PartyLegalEntity")
    _add(b_legal, f"{{{NS_CBC}}}RegistrationName", data.buyer.name)

    payment = _add(invoice, f"{{{NS_CAC}}}PaymentMeans")
    _add(payment, f"{{{NS_CBC}}}PaymentMeansCode", data.payment_means_code)
    if data.iban:
        payee_account = _add(payment, f"{{{NS_CAC}}}PayeeFinancialAccount")
        _add(payee_account, f"{{{NS_CBC}}}ID", data.iban)

    total_tax = sum(line.tax_amount for line in data.lines)
    total_ht = sum(line.line_amount for line in data.lines)
    total_ttc = total_ht + total_tax

    tax_total = _add(invoice, f"{{{NS_CAC}}}TaxTotal")
    _add(tax_total, f"{{{NS_CBC}}}TaxAmount", f"{total_tax:.2f}", {"currencyID": data.currency})

    from collections import defaultdict
    tax_groups = defaultdict(lambda: {"taxable": 0.0, "tax": 0.0})
    for line in data.lines:
        key = (line.tax_category, line.tax_percent, line.tax_exemption_reason)
        tax_groups[key]["taxable"] += line.line_amount
        tax_groups[key]["tax"] += line.tax_amount

    for (cat_id, percent, exemption), amounts in tax_groups.items():
        subtotal = _add(tax_total, f"{{{NS_CAC}}}TaxSubtotal")
        _add(subtotal, f"{{{NS_CBC}}}TaxableAmount", f"{amounts['taxable']:.2f}", {"currencyID": data.currency})
        _add(subtotal, f"{{{NS_CBC}}}TaxAmount", f"{amounts['tax']:.2f}", {"currencyID": data.currency})
        cat = _add(subtotal, f"{{{NS_CAC}}}TaxCategory")
        _add(cat, f"{{{NS_CBC}}}ID", cat_id)
        _add(cat, f"{{{NS_CBC}}}Percent", str(percent))
        if exemption:
            _add(cat, f"{{{NS_CBC}}}TaxExemptionReason", exemption)
        scheme = _add(cat, f"{{{NS_CAC}}}TaxScheme")
        _add(scheme, f"{{{NS_CBC}}}ID", "VAT")

    monetary = _add(invoice, f"{{{NS_CAC}}}LegalMonetaryTotal")
    _add(monetary, f"{{{NS_CBC}}}LineExtensionAmount", f"{total_ht:.2f}", {"currencyID": data.currency})
    _add(monetary, f"{{{NS_CBC}}}TaxExclusiveAmount", f"{total_ht:.2f}", {"currencyID": data.currency})
    _add(monetary, f"{{{NS_CBC}}}TaxInclusiveAmount", f"{total_ttc:.2f}", {"currencyID": data.currency})
    _add(monetary, f"{{{NS_CBC}}}PayableAmount", f"{total_ttc:.2f}", {"currencyID": data.currency})

    for i, line in enumerate(data.lines, start=1):
        inv_line = _add(invoice, f"{{{NS_CAC}}}InvoiceLine")
        _add(inv_line, f"{{{NS_CBC}}}ID", str(i))
        _add(inv_line, f"{{{NS_CBC}}}InvoicedQuantity", str(line.quantity), {"unitCode": line.unit_code})
        _add(inv_line, f"{{{NS_CBC}}}LineExtensionAmount", f"{line.line_amount:.2f}", {"currencyID": data.currency})
        item = _add(inv_line, f"{{{NS_CAC}}}Item")
        _add(item, f"{{{NS_CBC}}}Name", line.description)
        line_tax_cat = _add(item, f"{{{NS_CAC}}}ClassifiedTaxCategory")
        _add(line_tax_cat, f"{{{NS_CBC}}}ID", line.tax_category)
        _add(line_tax_cat, f"{{{NS_CBC}}}Percent", str(line.tax_percent))
        if line.tax_exemption_reason:
            _add(line_tax_cat, f"{{{NS_CBC}}}TaxExemptionReason", line.tax_exemption_reason)
        line_scheme = _add(line_tax_cat, f"{{{NS_CAC}}}TaxScheme")
        _add(line_scheme, f"{{{NS_CBC}}}ID", "VAT")
        price_el = _add(inv_line, f"{{{NS_CAC}}}Price")
        _add(price_el, f"{{{NS_CBC}}}PriceAmount", f"{line.unit_price:.2f}", {"currencyID": data.currency})

    return ET.tostring(invoice, encoding="utf-8", xml_declaration=True)