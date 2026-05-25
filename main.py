from datetime import date, timedelta
import traceback
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel

from auth import get_token, get_company_token
from config import BASE_URL

app = FastAPI(
    title="Peppol Wrapper API",
    description="Connecte n'importe quel logiciel au réseau Peppol via SUPER PDP",
    version="0.1.0"
)

class InvoicePayload(BaseModel):
    invoice: dict


def _add(parent, tag, text=None, attrib=None):
    if attrib is None:
        attrib = {}
    el = ET.SubElement(parent, tag, attrib)
    if text is not None:
        el.text = str(text)
    return el


def generate_minimal_ubl_xml(invoice_number: str, issue_date: str) -> bytes:
    ns_invoice = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    ns_cac = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    ns_cbc = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

    ET.register_namespace("", ns_invoice)
    ET.register_namespace("cac", ns_cac)
    ET.register_namespace("cbc", ns_cbc)

    invoice = ET.Element(f"{{{ns_invoice}}}Invoice")
    _add(invoice, f"{{{ns_cbc}}}CustomizationID", "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0")
    _add(invoice, f"{{{ns_cbc}}}ProfileID", "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0")
    _add(invoice, f"{{{ns_cbc}}}ID", invoice_number)
    _add(invoice, f"{{{ns_cbc}}}IssueDate", issue_date)
    _add(invoice, f"{{{ns_cbc}}}DueDate", (date.fromisoformat(issue_date) + timedelta(days=30)).isoformat())
    _add(invoice, f"{{{ns_cbc}}}InvoiceTypeCode", "380")
    _add(invoice, f"{{{ns_cbc}}}DocumentCurrencyCode", "EUR")
    _add(invoice, f"{{{ns_cbc}}}BuyerReference", "sandbox-buyer")

    supplier = _add(invoice, f"{{{ns_cac}}}AccountingSupplierParty")
    supplier_party = _add(supplier, f"{{{ns_cac}}}Party")
    _add(supplier_party, f"{{{ns_cbc}}}EndpointID", "phase4-test-sender", {"schemeID": "9915"})
    supplier_name = _add(supplier_party, f"{{{ns_cac}}}PartyName")
    _add(supplier_name, f"{{{ns_cbc}}}Name", "Phase4 Test Sender")
    supplier_address = _add(supplier_party, f"{{{ns_cac}}}PostalAddress")
    _add(supplier_address, f"{{{ns_cbc}}}StreetName", "Rue de test 1")
    _add(supplier_address, f"{{{ns_cbc}}}CityName", "Paris")
    _add(supplier_address, f"{{{ns_cbc}}}PostalZone", "75001")
    supplier_country = _add(supplier_address, f"{{{ns_cac}}}Country")
    _add(supplier_country, f"{{{ns_cbc}}}IdentificationCode", "FR")
    supplier_legal = _add(supplier_party, f"{{{ns_cac}}}PartyLegalEntity")
    _add(supplier_legal, f"{{{ns_cbc}}}RegistrationName", "Phase4 Test Sender")
    _add(supplier_legal, f"{{{ns_cbc}}}CompanyID", "000000002", {"schemeID": "0002"})

    customer = _add(invoice, f"{{{ns_cac}}}AccountingCustomerParty")
    customer_party = _add(customer, f"{{{ns_cac}}}Party")
    _add(customer_party, f"{{{ns_cbc}}}EndpointID", "helger", {"schemeID": "9915"})
    customer_name = _add(customer_party, f"{{{ns_cac}}}PartyName")
    _add(customer_name, f"{{{ns_cbc}}}Name", "Helger Test Receiver")
    customer_address = _add(customer_party, f"{{{ns_cac}}}PostalAddress")
    _add(customer_address, f"{{{ns_cbc}}}StreetName", "Avenue de test 2")
    _add(customer_address, f"{{{ns_cbc}}}CityName", "Lyon")
    _add(customer_address, f"{{{ns_cbc}}}PostalZone", "69001")
    customer_country = _add(customer_address, f"{{{ns_cac}}}Country")
    _add(customer_country, f"{{{ns_cbc}}}IdentificationCode", "FR")
    customer_legal = _add(customer_party, f"{{{ns_cac}}}PartyLegalEntity")
    _add(customer_legal, f"{{{ns_cbc}}}RegistrationName", "Helger Test Receiver")

    payment_means = _add(invoice, f"{{{ns_cac}}}PaymentMeans")
    _add(payment_means, f"{{{ns_cbc}}}PaymentMeansCode", "30")
    payee_account = _add(payment_means, f"{{{ns_cac}}}PayeeFinancialAccount")
    _add(payee_account, f"{{{ns_cbc}}}ID", "IBAN32423940")

    tax_total = _add(invoice, f"{{{ns_cac}}}TaxTotal")
    _add(tax_total, f"{{{ns_cbc}}}TaxAmount", "0.00", {"currencyID": "EUR"})
    tax_subtotal = _add(tax_total, f"{{{ns_cac}}}TaxSubtotal")
    _add(tax_subtotal, f"{{{ns_cbc}}}TaxableAmount", "100.00", {"currencyID": "EUR"})
    _add(tax_subtotal, f"{{{ns_cbc}}}TaxAmount", "0.00", {"currencyID": "EUR"})
    tax_category = _add(tax_subtotal, f"{{{ns_cac}}}TaxCategory")
    _add(tax_category, f"{{{ns_cbc}}}ID", "O")
    _add(tax_category, f"{{{ns_cbc}}}Percent", "0")
    _add(tax_category, f"{{{ns_cbc}}}TaxExemptionReason", "Not subject to VAT")
    tax_scheme = _add(tax_category, f"{{{ns_cac}}}TaxScheme")
    _add(tax_scheme, f"{{{ns_cbc}}}ID", "VAT")

    monetary_total = _add(invoice, f"{{{ns_cac}}}LegalMonetaryTotal")
    _add(monetary_total, f"{{{ns_cbc}}}LineExtensionAmount", "100.00", {"currencyID": "EUR"})
    _add(monetary_total, f"{{{ns_cbc}}}TaxExclusiveAmount", "100.00", {"currencyID": "EUR"})
    _add(monetary_total, f"{{{ns_cbc}}}TaxInclusiveAmount", "100.00", {"currencyID": "EUR"})
    _add(monetary_total, f"{{{ns_cbc}}}PayableAmount", "100.00", {"currencyID": "EUR"})

    line = _add(invoice, f"{{{ns_cac}}}InvoiceLine")
    _add(line, f"{{{ns_cbc}}}ID", "1")
    _add(line, f"{{{ns_cbc}}}InvoicedQuantity", "1", {"unitCode": "C62"})
    _add(line, f"{{{ns_cbc}}}LineExtensionAmount", "100.00", {"currencyID": "EUR"})
    item = _add(line, f"{{{ns_cac}}}Item")
    _add(item, f"{{{ns_cbc}}}Name", "Prestation de test sandbox")
    line_tax = _add(item, f"{{{ns_cac}}}ClassifiedTaxCategory")
    _add(line_tax, f"{{{ns_cbc}}}ID", "O")
    _add(line_tax, f"{{{ns_cbc}}}Percent", "0")
    _add(line_tax, f"{{{ns_cbc}}}TaxExemptionReason", "Not subject to VAT")
    line_tax_scheme = _add(line_tax, f"{{{ns_cac}}}TaxScheme")
    _add(line_tax_scheme, f"{{{ns_cbc}}}ID", "VAT")
    price = _add(line, f"{{{ns_cac}}}Price")
    _add(price, f"{{{ns_cbc}}}PriceAmount", "100.00", {"currencyID": "EUR"})

    return ET.tostring(invoice, encoding="utf-8", xml_declaration=True)


@app.get("/")
async def root():
    return {"message": "Peppol Wrapper API is running"}


@app.get("/token-test")
async def test_token():
    try:
        token = await get_token()
        return {"status": "ok", "token_preview": token[:20] + "..."}
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


@app.get("/session")
async def get_session():
    try:
        token = await get_token()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/oauth2_sessions/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/company")
async def get_company():
    try:
        token = await get_token()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/companies/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/company/seller")
async def get_seller_company():
    try:
        token = await get_company_token("seller")
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/companies/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/company/buyer")
async def get_buyer_company():
    try:
        token = await get_company_token("buyer")
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/companies/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices/test-xml")
async def get_test_invoice_xml():
    try:
        today = date.today().isoformat()
        invoice_number = f"TEST-{today}"
        xml_bytes = generate_minimal_ubl_xml(invoice_number, today)
        return Response(content=xml_bytes, media_type="application/xml")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/invoices/send")
async def send_invoice(payload: InvoicePayload):
    try:
        token = await get_company_token("seller")
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/v1.beta/invoices",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload.invoice
            )
            if r.status_code >= 400:
                raise HTTPException(
                    status_code=r.status_code,
                    detail={
                        "superpdp_status": r.status_code,
                        "superpdp_body": r.text,
                        "invoice_sent": payload.invoice
                    }
                )
            return {"status": "sent", "response": r.json()}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/invoices/send-test")
async def send_test_invoice():
    try:
        seller_token = await get_company_token("seller")
        today = date.today().isoformat()
        invoice_number = f"TEST-{today}"
        xml_bytes = generate_minimal_ubl_xml(invoice_number, today)
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/v1.beta/invoices?disable_pre_check=true",
                content=xml_bytes,
                headers={
                    "Authorization": f"Bearer {seller_token}",
                    "Content-Type": "application/xml"
                }
            )
            if r.status_code >= 400:
                raise HTTPException(
                    status_code=r.status_code,
                    detail={
                        "superpdp_status": r.status_code,
                        "superpdp_body": r.text,
                        "invoice_xml": xml_bytes.decode("utf-8")
                    }
                )
            return {
                "status": "sent",
                "invoice_number": invoice_number,
                "response": r.json()
            }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices")
async def get_invoices(direction: str = Query(None, pattern="^(in|out)$")):
    try:
        token = await get_token()
        params = {}
        if direction:
            params["direction"] = direction
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/invoices",
                headers={"Authorization": f"Bearer {token}"},
                params=params
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices/seller")
async def get_seller_invoices(direction: str = Query(None, pattern="^(in|out)$")):
    try:
        token = await get_company_token("seller")
        params = {}
        if direction:
            params["direction"] = direction
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/invoices",
                headers={"Authorization": f"Bearer {token}"},
                params=params
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices/buyer")
async def get_buyer_invoices(direction: str = Query(None, pattern="^(in|out)$")):
    try:
        token = await get_company_token("buyer")
        params = {}
        if direction:
            params["direction"] = direction
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/invoices",
                headers={"Authorization": f"Bearer {token}"},
                params=params
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: int):
    try:
        token = await get_token()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/v1.beta/invoices/{invoice_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if r.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Invoice {invoice_id} introuvable côté SUPER PDP"
                )
            r.raise_for_status()
            return r.json()
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
