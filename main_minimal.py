from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent.resolve()

app = FastAPI(title="Peppol UI")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

INDEX_HTML = (BASE / "templates" / "index.html").read_text(encoding="utf-8")

@app.get("/")
def home():
    return HTMLResponse(INDEX_HTML)

@app.post("/api/invoices/validate")
def api_validate():
    return JSONResponse({"ok": True, "message": "validation prête"})

@app.post("/api/invoices/build-xml")
def api_build():
    xml = '<?xml version="1.0" encoding="UTF-8"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>\n'
    return Response(content=xml, media_type="application/xml")

@app.post("/api/invoices/send")
def api_send():
    return JSONResponse({"ok": True, "message": "envoi simulé"})
