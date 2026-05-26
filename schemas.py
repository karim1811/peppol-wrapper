from typing import Optional, List
from pydantic import BaseModel, Field


class PartyInfo(BaseModel):
    name: str
    endpoint_id: str
    endpoint_scheme: str = "9915"
    street: str
    city: str
    postal_code: str
    country_code: str = "FR"
    legal_id: str
    legal_id_scheme: str = "0002"


class InvoiceLine(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    unit_code: str = "C62"
    tax_category: str = "S"
    tax_percent: float = 20.0
    tax_exemption_reason: Optional[str] = None

    @property
    def line_amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)

    @property
    def tax_amount(self) -> float:
        return round(self.line_amount * self.tax_percent / 100, 2)


class InvoiceRequest(BaseModel):
    invoice_number: str
    issue_date: str
    due_date: Optional[str] = None
    currency: str = "EUR"
    buyer_reference: str = "REF-ACHETEUR"
    seller: PartyInfo
    buyer: PartyInfo
    lines: List[InvoiceLine] = Field(..., min_length=1)
    payment_means_code: str = "30"
    iban: Optional[str] = None