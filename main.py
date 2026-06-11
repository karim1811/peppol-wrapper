from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import date
import json
import httpx

BASE_DIR = Path(__file__).parent.resolve()

from auth import get_token
from schemas import InvoiceRequest
from services.ubl_builder import build_ubl_invoice
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