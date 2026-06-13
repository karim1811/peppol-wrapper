"""
CSV import module for Peppol Bridge.
Accepts a standardised CSV export from any accounting software
and converts it into an InvoiceRequest ready for UBL generation.

Expected CSV columns (flexible naming):
  invoice_number / numero / invoice_no / ref
  issue_date / date / invoice_date
  due_date / echeance (optional)
  currency / devise (optional, default EUR)

  seller_name / vendeur / emetteur_nom
  seller_endpoint / vendeur_endpoint / emetteur_id
  seller_street / vendeur_rue
  seller_city / vendeur_ville
  seller_postal / vendeur_cp / vendeur_code_postal
  seller_country / vendeur_pays (optional, default FR)
  seller_legal_id / vendeur_siret / vendeur_tva

  buyer_name / acheteur / client_nom
  buyer_endpoint / acheteur_endpoint / client_id
  buyer_street / acheteur_rue
  buyer_city / acheteur_ville
  buyer_postal / acheteur_cp / acheteur_code_postal
  buyer_country / acheteur_pays (optional, default FR)
  buyer_legal_id / acheteur_siret / acheteur_tva

  line_description / description / libelle / designation
  line_quantity / quantite / qte
  line_unit_price / prix_unitaire / pu / montant_ht
  line_unit_code / unite (optional, default C62)
  line_tax_category / tva_categorie (optional, default S)
  line_tax_percent / tva_taux / tax_percent (optional, default 20.0)
  line_tax_exemption / tva_exemption (optional)

Multiple rows with the same invoice_number = multiple lines on one invoice.
"""

import csv
import io
from collections import defaultdict
from typing import List, Tuple
from schemas import InvoiceRequest, PartyInfo, InvoiceLine


# Flexible column name mapping
_COLUMN_MAP = {
    "invoice_number": ["invoice_number", "numero", "invoice_no", "ref", "facture_numero", "no_facture"],
    "issue_date": ["issue_date", "date", "invoice_date", "date_facture", "date_emission"],
    "due_date": ["due_date", "echeance", "date_echeance", "payment_due"],
    "currency": ["currency", "devise", "monnaie"],

    "seller_name": ["seller_name", "vendeur", "emetteur_nom", "emetteur", "supplier_name", "emetteur_raison_sociale"],
    "seller_endpoint": ["seller_endpoint", "vendeur_endpoint", "emetteur_id", "supplier_endpoint", "emetteur_peppol"],
    "seller_street": ["seller_street", "vendeur_rue", "emetteur_rue", "supplier_street", "emetteur_adresse"],
    "seller_city": ["seller_city", "vendeur_ville", "emetteur_ville", "supplier_city"],
    "seller_postal": ["seller_postal", "vendeur_cp", "vendeur_code_postal", "emetteur_cp", "supplier_postal"],
    "seller_country": ["seller_country", "vendeur_pays", "emetteur_pays", "supplier_country"],
    "seller_legal_id": ["seller_legal_id", "vendeur_siret", "vendeur_tva", "emetteur_siret", "supplier_legal_id"],

    "buyer_name": ["buyer_name", "acheteur", "client_nom", "client", "customer_name", "acheteur_raison_sociale"],
    "buyer_endpoint": ["buyer_endpoint", "acheteur_endpoint", "client_id", "customer_endpoint", "acheteur_peppol"],
    "buyer_street": ["buyer_street", "acheteur_rue", "client_rue", "customer_street", "acheteur_adresse"],
    "buyer_city": ["buyer_city", "acheteur_ville", "client_ville", "customer_city"],
    "buyer_postal": ["buyer_postal", "acheteur_cp", "acheteur_code_postal", "client_cp", "customer_postal"],
    "buyer_country": ["buyer_country", "acheteur_pays", "client_pays", "customer_country"],
    "buyer_legal_id": ["buyer_legal_id", "acheteur_siret", "acheteur_tva", "client_siret", "customer_legal_id"],

    "line_description": ["line_description", "description", "libelle", "designation", "intitule"],
    "line_quantity": ["line_quantity", "quantite", "qte", "qty", "nombre"],
    "line_unit_price": ["line_unit_price", "prix_unitaire", "pu", "montant_ht", "unit_price", "price"],
    "line_unit_code": ["line_unit_code", "unite", "unit_code", "unite_code"],
    "line_tax_category": ["line_tax_category", "tva_categorie", "tax_category", "categorie_tva"],
    "line_tax_percent": ["line_tax_percent", "tva_taux", "tax_percent", "taux_tva", "tva_pourcentage"],
    "line_tax_exemption": ["line_tax_exemption", "tva_exemption", "tax_exemption", "exoneration"],
}


def _resolve_column(headers: List[str], canonical: str) -> int:
    """Find the index of a canonical column name using flexible matching."""
    candidates = _COLUMN_MAP.get(canonical, [canonical])
    headers_lower = [h.strip().lower().replace(" ", "_") for h in headers]
    for candidate in candidates:
        candidate_norm = candidate.strip().lower().replace(" ", "_")
        for i, h in enumerate(headers_lower):
            if h == candidate_norm or h.startswith(candidate_norm) or candidate_norm in h:
                return i
    return -1


def _safe_float(value: str, default: float = 0.0) -> float:
    if not value or not value.strip():
        return default
    try:
        # Handle French decimal format: "1 234,56" -> "1234.56"
        cleaned = value.strip().replace(" ", "").replace(",", ".")
        # Handle multiple dots (keep last)
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        return float(cleaned)
    except (ValueError, IndexError):
        return default


def _safe_str(value: str, default: str = "") -> str:
    return value.strip() if value else default


def parse_csv(csv_content: str) -> Tuple[List[InvoiceRequest], List[str]]:
    """
    Parse CSV content and return a list of InvoiceRequest objects.
    Returns (invoices, warnings).
    Auto-detects delimiter (comma, semicolon, tab).
    """
    warnings: List[str] = []
    
    # Auto-detect delimiter
    try:
        sample = csv_content[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","  # fallback
    
    reader = csv.reader(io.StringIO(csv_content), delimiter=delimiter)
    headers = next(reader, None)
    if not headers:
        raise ValueError("CSV vide ou sans en-tete")

    headers = [h.strip() for h in headers]
    detected_delim = delimiter if delimiter != "," else "virgule"
    detected_delim = detected_delim if detected_delim != ";" else "point-virgule"
    print(f"  CSV delimiter detected: '{detected_delim}' ({len(headers)} columns)")

    # Resolve column indices
    def col(name: str, required: bool = True) -> int:
        idx = _resolve_column(headers, name)
        if idx == -1 and required:
            raise ValueError(
                f"Colonne requise introuvable: '{name}'. "
                f"Colonnes disponibles: {headers}. "
                f"Noms acceptes: {_COLUMN_MAP.get(name, [name])}"
            )
        return idx

    # Required columns
    idx_invoice_number = col("invoice_number")
    idx_issue_date = col("issue_date")
    idx_seller_name = col("seller_name")
    idx_seller_endpoint = col("seller_endpoint")
    idx_seller_street = col("seller_street")
    idx_seller_city = col("seller_city")
    idx_seller_postal = col("seller_postal")
    idx_seller_legal_id = col("seller_legal_id")
    idx_buyer_name = col("buyer_name")
    idx_buyer_endpoint = col("buyer_endpoint")
    idx_buyer_street = col("buyer_street")
    idx_buyer_city = col("buyer_city")
    idx_buyer_postal = col("buyer_postal")
    idx_buyer_legal_id = col("buyer_legal_id")
    idx_line_desc = col("line_description")
    idx_line_qty = col("line_quantity")
    idx_line_price = col("line_unit_price")

    # Optional columns
    idx_due_date = col("due_date", required=False)
    idx_currency = col("currency", required=False)
    idx_seller_country = col("seller_country", required=False)
    idx_buyer_country = col("buyer_country", required=False)
    idx_line_unit_code = col("line_unit_code", required=False)
    idx_line_tax_cat = col("line_tax_category", required=False)
    idx_line_tax_pct = col("line_tax_percent", required=False)
    idx_line_tax_exempt = col("line_tax_exemption", required=False)

    # Group rows by invoice_number
    invoice_rows = defaultdict(list)
    for row_num, row in enumerate(reader, start=2):
        if not row or all(not c.strip() for c in row):
            continue
        inv_num = row[idx_invoice_number].strip() if idx_invoice_number < len(row) else ""
        if not inv_num:
            warnings.append(f"Ligne {row_num}: numero de facture manquant, ignoree")
            continue
        invoice_rows[inv_num].append(row)

    if not invoice_rows:
        raise ValueError("Aucune facture trouvee dans le CSV")

    invoices: List[InvoiceRequest] = []

    for inv_num, rows in invoice_rows.items():
        first = rows[0]

        def get(idx: int, default: str = "") -> str:
            if idx == -1 or idx >= len(first):
                return default
            return first[idx].strip() if first[idx] else default

        # Build lines
        lines = []
        for row_num, row in enumerate(rows, start=1):
            def rget(idx: int, default: str = "") -> str:
                if idx == -1 or idx >= len(row):
                    return default
                return row[idx].strip() if row[idx] else default

            desc = rget(idx_line_desc)
            if not desc:
                warnings.append(f"Facture {inv_num} ligne {row_num}: description manquante, ignoree")
                continue

            line = InvoiceLine(
                description=desc,
                quantity=_safe_float(rget(idx_line_qty, "1"), 1.0),
                unit_price=_safe_float(rget(idx_line_price)),
                unit_code=rget(idx_line_unit_code, "C62") or "C62",
                tax_category=rget(idx_line_tax_cat, "S") or "S",
                tax_percent=_safe_float(rget(idx_line_tax_pct, "20"), 20.0),
                tax_exemption_reason=rget(idx_line_tax_exempt) or None,
            )
            lines.append(line)

        if not lines:
            warnings.append(f"Facture {inv_num}: aucune ligne valide, ignoree")
            continue

        seller = PartyInfo(
            name=get(idx_seller_name),
            endpoint_id=get(idx_seller_endpoint),
            street=get(idx_seller_street),
            city=get(idx_seller_city),
            postal_code=get(idx_seller_postal),
            country_code=get(idx_seller_country, "FR") or "FR",
            legal_id=get(idx_seller_legal_id),
        )

        buyer = PartyInfo(
            name=get(idx_buyer_name),
            endpoint_id=get(idx_buyer_endpoint),
            street=get(idx_buyer_street),
            city=get(idx_buyer_city),
            postal_code=get(idx_buyer_postal),
            country_code=get(idx_buyer_country, "FR") or "FR",
            legal_id=get(idx_buyer_legal_id),
        )

        invoice = InvoiceRequest(
            invoice_number=inv_num,
            issue_date=get(idx_issue_date),
            due_date=get(idx_due_date) or None,
            currency=get(idx_currency, "EUR") or "EUR",
            seller=seller,
            buyer=buyer,
            lines=lines,
        )
        invoices.append(invoice)

    return invoices, warnings
