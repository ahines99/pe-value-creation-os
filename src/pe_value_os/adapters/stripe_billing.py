"""Stripe billing adapter (PVC-113): invoices, price books, concessions (credit notes) and billing customers.

Read-only; uses a restricted API key with read access to invoices, prices, credit notes and customers.
Amounts are in the smallest currency unit and converted to Decimal major units. List pagination uses
`starting_after`; invoice lines beyond the embedded page are fetched from /v1/invoices/{id}/lines.

Mapping:
- InvoiceLine: list price = price.unit_amount; on-invoice discount = sum(discount_amounts); net = qty x list - discount.
- PriceBook: one per price; is_current = price.active.
- Concession: credit notes (type credit) by customer and date.
- Billing customers (for entity resolution): id, name, email domain.
The company's billing customer ids are Stripe ids; `CompositeAdapter` resolves them to canonical customers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx

from ..domain.entity_resolution import ForeignEntity
from ..domain.source_models import Dataset, DatasetKind
from .base import EvidenceSink
from .sources import ApiClient, dataset_from_records

CENTS = Decimal(100)
Q = Decimal("0.01")


def _money(minor_units: Any) -> Decimal:
    return (Decimal(minor_units or 0) / CENTS).quantize(Q)


def _d(ts: int) -> date:
    return datetime.fromtimestamp(ts, UTC).date()


def size_band(qty: Decimal) -> str:
    return "large" if qty >= 200 else "medium" if qty >= 50 else "small"


class StripeBillingAdapter:
    name = "stripe"
    provides = frozenset({DatasetKind.INVOICES, DatasetKind.PRICE_BOOKS, DatasetKind.CONCESSIONS})

    def __init__(self, api_key: str, *, base_url: str = "https://api.stripe.com",
                 transport: httpx.BaseTransport | None = None, page_size: int = 100):
        self.api = ApiClient(base_url, {"Authorization": f"Bearer {api_key}"}, transport=transport)
        self.page_size = page_size
        self._customers: list[dict[str, Any]] | None = None

    def _list(self, path: str, **params: Any) -> tuple[list[dict[str, Any]], list[Any]]:
        items: list[dict[str, Any]] = []
        pages: list[Any] = []
        after = None
        while True:
            q = {k: v for k, v in {"limit": self.page_size, **params, "starting_after": after}.items()
                 if v is not None}
            page = self.api.get(path, q)
            pages.append(page)
            data = page.get("data", [])
            items += data
            if not page.get("has_more") or not data:
                return items, pages
            after = data[-1]["id"]

    def customers(self) -> list[dict[str, Any]]:
        if self._customers is None:
            self._customers, _ = self._list("/v1/customers")
        return self._customers

    def foreign_entities(self) -> list[ForeignEntity]:
        return [ForeignEntity("stripe", c["id"], c.get("name"), (c.get("email") or "").split("@")[-1] or None)
                for c in self.customers()]

    def load_datasets(self, company_id: str, sink: EvidenceSink | None) -> dict[DatasetKind, Dataset]:
        prices, p_pages = self._list("/v1/prices")
        price_by_id = {p["id"]: p for p in prices}
        invoices, i_pages = self._list("/v1/invoices", status="paid")
        rows = []
        for inv in invoices:
            lines = list(inv.get("lines", {}).get("data", []))
            if inv.get("lines", {}).get("has_more"):
                more, extra = self._list(f"/v1/invoices/{inv['id']}/lines",
                                         starting_after=lines[-1]["id"] if lines else None)
                lines += more
                i_pages += extra
            for ln in lines:
                price = ln.get("price") or price_by_id.get(ln.get("price_id", ""), {})
                qty = Decimal(str(ln.get("quantity") or 0))
                unit = _money(price.get("unit_amount"))
                disc = _money(sum(int(x["amount"]) for x in ln.get("discount_amounts", [])))
                rows.append({
                    "invoice_id": inv["id"], "line_id": ln["id"], "customer_id": inv["customer"],
                    "invoice_date": _d(inv["created"]).isoformat(), "product": price.get("product"),
                    "price_book_id": price.get("id"), "quantity": str(qty), "list_price_per_unit": str(unit),
                    "on_invoice_discount": str(disc), "net_amount": str((qty * unit - disc).quantize(Q)),
                    "currency": (inv.get("currency") or "").upper(), "deal_size_band": size_band(qty),
                })
        credit_notes, c_pages = self._list("/v1/credit_notes")
        conc = [{"customer_id": cn["customer"], "concession_date": _d(cn["created"]).isoformat(),
                 "concession_type": "credit", "amount": str(_money(cn["total"]))}
                for cn in credit_notes if cn.get("status") != "void"]
        books = [{"price_book_id": p["id"], "product": p["product"],
                  "list_price_per_unit": str(_money(p.get("unit_amount"))),
                  "effective_from": _d(p["created"]).isoformat(), "effective_to": None,
                  "is_current": bool(p.get("active"))} for p in prices]
        now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        return {
            DatasetKind.INVOICES: dataset_from_records(DatasetKind.INVOICES, company_id, rows,
                                                       source_uri="stripe://v1/invoices", as_of=now, sink=sink,
                                                       raw_payload=i_pages),
            DatasetKind.PRICE_BOOKS: dataset_from_records(DatasetKind.PRICE_BOOKS, company_id, books,
                                                          source_uri="stripe://v1/prices", as_of=now, sink=sink,
                                                          raw_payload=p_pages),
            DatasetKind.CONCESSIONS: dataset_from_records(DatasetKind.CONCESSIONS, company_id, conc,
                                                          source_uri="stripe://v1/credit_notes", as_of=now, sink=sink,
                                                          raw_payload=c_pages),
        }
