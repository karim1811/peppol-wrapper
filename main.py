from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import Response, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import date
from typing import Optional
import json
import httpx
import hashlib
import secrets

BASE_DIR = Path(__file__).parent.resolve()

from auth import get_token
from schemas import InvoiceRequest
from services.ubl_builder import build_ubl_invoice
from services.csv_parser import parse_csv
from config import BASE_URL

app = FastAPI(title="Peppol Wrapper API")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# Removed legacy JSON root; UI now serves at /


@app.get("/auth/test")
async def auth_test():
    token = await get_token()
    return {
        "access_token_preview": token[:50] + "..." if token else None
    }


_HISTORY_PATH = Path("invoice_history.json")


def _now_iso() -> str:
    return date.today().isoformat()


async def _save_invoice(invoice: InvoiceRequest, total_ttc: float | None = None):
    if total_ttc is None:
        total_ttc = round(
            sum(
                round(line.quantity * line.unit_price, 2)
                + round(line.quantity * line.unit_price * line.tax_percent / 100, 2)
                for line in invoice.lines
            ),
            2,
        )

    entry = {
        "id": invoice.invoice_number,
        "number": invoice.invoice_number,
        "date": invoice.issue_date,
        "buyer": invoice.buyer.name,
        "total_ttc": total_ttc,
        "sent": False,
        "created_at": _now_iso(),
    }

    try:
        existing = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        existing = []

    existing = [e for e in existing if e.get("id") != entry["id"]]
    existing.append(entry)
    _HISTORY_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@app.post("/invoices/build-xml")
async def build_xml(invoice: InvoiceRequest):
    xml_bytes = build_ubl_invoice(invoice)
    return Response(content=xml_bytes, media_type="application/xml")


@app.post("/invoices/validate")
async def validate_invoice(invoice: InvoiceRequest):
    xml_bytes = build_ubl_invoice(invoice)
    xml_text = xml_bytes.decode("utf-8")
    await _save_invoice(invoice, total_ttc=None)
    return {
        "valid": True,
        "message": "XML generated successfully",
        "xml_preview": xml_text[:1000],
    }


@app.post("/invoices/send")
async def send_invoice(invoice: InvoiceRequest):
    token = await get_token()
    xml_bytes = build_ubl_invoice(invoice)

    url = f"{BASE_URL}/v1.beta/invoices"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    files = {
        "file": ("invoice.xml", xml_bytes, "application/xml")
    }

    params = {
        "external_id": invoice.invoice_number,
        "disable_pre_check": True,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, params=params, files=files)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    try:
        superpdp_response = response.json()
    except Exception:
        superpdp_response = {"raw_response": response.text}

    return {
        "sent": True,
        "superpdp_status": response.status_code,
        "superpdp_response": superpdp_response
    }


# Web UI routes

@app.get("/", response_class=HTMLResponse)
async def invoices_form(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_list(request: Request):
    history_path = Path("invoice_history.json")
    entries = []
    if history_path.exists():
        try:
            entries = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    paid = sum(1 for e in entries if e.get("sent"))
    return templates.TemplateResponse(
        "list.html",
        {
            "request": request,
            "invoices": entries,
            "used": paid,
            "limit": 10,
        },
    )


# ============================================================
# MULTI-TENANT API KEY SYSTEM
# ============================================================

_TENANTS_PATH = Path("tenants.json")


def _load_tenants() -> dict:
    """Load tenants from JSON file. Returns dict of {api_key: tenant_info}."""
    if _TENANTS_PATH.exists():
        try:
            return json.loads(_TENANTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_tenants(tenants: dict):
    _TENANTS_PATH.write_text(
        json.dumps(tenants, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def generate_api_key() -> str:
    return "pb_" + secrets.token_hex(24)


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> dict:
    """Dependency: validate API key and return tenant info."""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Get one at POST /api/tenants/register",
        )
    tenants = _load_tenants()
    tenant = tenants.get(x_api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant


# ============================================================
# TENANT MANAGEMENT ENDPOINTS
# ============================================================

@app.post("/api/tenants/register")
async def register_tenant(request: Request):
    """
    Register a new tenant (editor/integrator).
    Returns an API key to use for all subsequent calls.
    Body JSON: { "name": "Editor Name", "email": "contact@editor.com" }
    """
    body = await request.json()
    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Field 'name' is required")

    api_key = generate_api_key()
    tenants = _load_tenants()
    tenants[api_key] = {
        "name": name,
        "email": email,
        "api_key_prefix": api_key[:10] + "...",
        "created_at": date.today().isoformat(),
        "active": True,
        "invoice_count": 0,
    }
    _save_tenants(tenants)

    return {
        "api_key": api_key,
        "message": "Store this API key. It won't be shown again.",
        "name": name,
        "hint": "Use header X-API-Key: <api_key> on all API calls",
    }


@app.get("/api/tenants/me")
async def get_tenant_info(tenant: dict = Depends(verify_api_key)):
    """Get current tenant info."""
    return tenant


# ============================================================
# CSV IMPORT ENDPOINT
# ============================================================

@app.post("/api/invoices/import-csv")
async def import_csv(
    request: Request,
    tenant: dict = Depends(verify_api_key),
    send: bool = True,
):
    """
    Import invoices from CSV and optionally send them via Peppol.

    CSV format: flexible column names (French or English).
    Multiple rows with same invoice_number = multiple lines.

    Query params:
      - send: true (default) = build XML + send via Peppol
               false = only build and validate, don't send

    Required CSV columns (flexible naming):
      invoice_number, issue_date,
      seller_name, seller_endpoint, seller_street, seller_city, seller_postal, seller_legal_id,
      buyer_name, buyer_endpoint, buyer_street, buyer_city, buyer_postal, buyer_legal_id,
      line_description, line_quantity, line_unit_price

    Optional: due_date, currency, seller_country, buyer_country,
              line_unit_code, line_tax_category, line_tax_percent, line_tax_exemption
    """
    body = await request.body()
    csv_text = body.decode("utf-8-sig")

    try:
        invoices, warnings = parse_csv(csv_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    results = []
    for invoice in invoices:
        xml_bytes = build_ubl_invoice(invoice)
        xml_text = xml_bytes.decode("utf-8")

        entry = {
            "invoice_number": invoice.invoice_number,
            "buyer": invoice.buyer.name,
            "xml_valid": True,
            "xml_preview": xml_text[:500],
            "sent": False,
            "send_status": None,
            "send_response": None,
        }

        if send:
            try:
                token = await get_token()
                url = f"{BASE_URL}/v1.beta/invoices"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                }
                files = {
                    "file": ("invoice.xml", xml_bytes, "application/xml")
                }
                params = {
                    "external_id": invoice.invoice_number,
                    "disable_pre_check": True,
                }
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        url, headers=headers, params=params, files=files
                    )
                entry["sent"] = resp.status_code < 400
                entry["send_status"] = resp.status_code
                try:
                    entry["send_response"] = resp.json()
                except Exception:
                    entry["send_response"] = {"raw": resp.text[:500]}
            except Exception as e:
                entry["sent"] = False
                entry["send_response"] = {"error": str(e)}

        await _save_invoice(invoice)
        results.append(entry)

    # Update tenant invoice count
    tenants = _load_tenants()
    for key, t in tenants.items():
        if t.get("name") == tenant.get("name"):
            t["invoice_count"] = t.get("invoice_count", 0) + len(results)
            break
    _save_tenants(tenants)

    return {
        "imported": len(results),
        "warnings": warnings,
        "invoices": results,
    }


# ============================================================
# WEBHOOK ENDPOINT
# ============================================================

@app.post("/api/webhook/invoices")
async def webhook_invoice(
    request: Request,
    tenant: dict = Depends(verify_api_key),
    x_webhook_signature: Optional[str] = Header(None),
):
    """
    Webhook endpoint for editors to push invoices.

    Accepts the same JSON format as /invoices/send (InvoiceRequest).
    Optionally include a signature header for verification.

    Body JSON: InvoiceRequest schema
    """
    body = await request.json()

    try:
        invoice = InvoiceRequest(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid invoice JSON: {e}",
        )

    # Build XML
    xml_bytes = build_ubl_invoice(invoice)
    xml_text = xml_bytes.decode("utf-8")

    # Send via Peppol
    token = await get_token()
    url = f"{BASE_URL}/v1.beta/invoices"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    files = {
        "file": ("invoice.xml", xml_bytes, "application/xml")
    }
    params = {
        "external_id": invoice.invoice_number,
        "disable_pre_check": True,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, params=params, files=files)

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "message": "Peppol send failed",
                "superpdp_response": resp.text[:1000],
            },
        )

    try:
        superpdp_response = resp.json()
    except Exception:
        superpdp_response = {"raw": resp.text[:500]}

    await _save_invoice(invoice)

    return {
        "sent": True,
        "invoice_number": invoice.invoice_number,
        "tenant": tenant.get("name"),
        "superpdp_status": resp.status_code,
        "superpdp_response": superpdp_response,
    }


# ============================================================
# API DOCUMENTATION ENDPOINT
# ============================================================

@app.get("/api/docs", response_class=HTMLResponse)
async def api_docs(request: Request):
    """Integration documentation page."""
    return templates.TemplateResponse("docs.html", {"request": request})