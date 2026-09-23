"""Vendor API simulator for adapter conformance tests (PVC-110..115).

Builds Stripe, HubSpot and Zendesk objects from a fixture company and serves them through an httpx
MockTransport with each vendor's paging semantics (Stripe starting_after/has_more, HubSpot paging.next.after,
Zendesk incremental cursor and next_page). Objects are generated at test time, so no large payloads are committed.
Id spaces differ per system, as in real life: Stripe `cus_*`, HubSpot numeric company ids, Zendesk organisation
ids; the base CSV export keys ARR, usage and contracts by Stripe customer id.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

FIX = Path(__file__).parent / "fixtures" / "companies"


def _rows(company: str, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader((FIX / company / f"{name}.csv").open(encoding="utf-8")))


def _ts(d: str) -> int:
    return int(datetime.combine(date.fromisoformat(d[:10]), datetime.min.time(), UTC).replace(hour=12).timestamp())


def cents(x: str) -> int:
    return int((Decimal(x) * 100).to_integral_value())


class VendorSim:
    def __init__(self, company: str = "beacon-pricing"):
        self.company = company
        customers = _rows(company, "customers")
        self.cus = {c["customer_id"]: "cus_" + c["billing_account_id"].split("-")[-1] for c in customers}
        self.hs = {c["customer_id"]: c["crm_account_id"].split("-")[-1] for c in customers}
        self.org = {c["customer_id"]: 100000 + int(c["crm_account_id"].split("-")[-1]) for c in customers}
        self.stripe_customers = [{"id": self.cus[c["customer_id"]], "name": c["name"],
                                  "email": f"billing@{c['domain']}"} for c in customers]
        self.prices = [{"id": p["price_book_id"], "product": p["product"], "unit_amount": cents(p["list_price_per_unit"]),
                        "active": p["is_current"].lower() == "true", "created": _ts(p["effective_from"])}
                       for p in _rows(company, "price_books")]
        by_inv: dict[str, list[dict[str, str]]] = defaultdict(list)
        for ln in _rows(company, "invoices"):
            by_inv[ln["invoice_id"]].append(ln)
        self.invoices = []
        for inv_id, lines in by_inv.items():
            self.invoices.append({
                "id": inv_id, "customer": self.cus[lines[0]["customer_id"]], "created": _ts(lines[0]["invoice_date"]),
                "currency": "usd", "status": "paid",
                "lines": {"has_more": False, "data": [{
                    "id": f"{inv_id}-{ln['line_id']}", "quantity": int(Decimal(ln["quantity"])),
                    "price": {"id": ln["price_book_id"], "product": ln["product"],
                              "unit_amount": cents(ln["list_price_per_unit"])},
                    "discount_amounts": [{"amount": cents(ln["on_invoice_discount"])}]} for ln in lines]}})
        self.credit_notes = [{"id": f"cn_{i}", "customer": self.cus[c["customer_id"]], "created": _ts(c["concession_date"]),
                              "total": cents(c["amount"]), "status": "issued"}
                             for i, c in enumerate(_rows(company, "concessions"))]
        self.hs_companies = [{"id": self.hs[c["customer_id"]], "properties": {
            "name": c["name"], "domain": c["domain"], "pvc_segment": c["segment"], "pvc_size_band": c["size_band"],
            "pvc_acquisition_channel": c["acquisition_channel"],
            "pvc_first_contract_date": c["first_contract_date"] + "T00:00:00Z"}} for c in customers]
        churn = {(e["customer_id"], e["month"]): e for e in _rows(company, "churn")}
        self.deals = []
        for o in _rows(company, "crm_opportunities"):
            reason = None
            if o["opportunity_type"] == "renewal" and o["stage"] == "lost":
                ev = churn.pop((o["customer_id"], o["close_date"][:8] + "01"), None)
                reason = ev["reason_code"] if ev else None
            d: dict[str, Any] = {"id": o["opportunity_id"], "properties": {
                "dealname": o["opportunity_id"], "amount": o["amount"], "createdate": o["created_date"] + "T00:00:00Z",
                "closedate": (o["close_date"] + "T00:00:00Z") if o["close_date"] else None,
                "dealstage": {"won": "closedwon", "lost": "closedlost"}.get(o["stage"], "appointmentscheduled"),
                "dealtype": "newbusiness" if o["opportunity_type"] == "new" else "existingbusiness",
                "pvc_opportunity_type": o["opportunity_type"], "closed_lost_reason": reason}}
            if o["customer_id"] != "prospect":
                d["associations"] = {"companies": {"results": [{"id": self.hs[o["customer_id"]], "type": "deal_to_company"}]}}
            self.deals.append(d)
        for (cid, month), ev in churn.items():  # churn not represented by a CRM deal: add lost renewals
            self.deals.append({"id": f"churn-{cid}-{month}", "properties": {
                "dealname": "renewal", "amount": "0", "createdate": month + "T00:00:00Z", "closedate": month + "T00:00:00Z",
                "dealstage": "closedlost", "dealtype": "existingbusiness", "pvc_opportunity_type": "renewal",
                "closed_lost_reason": "payment_failed" if ev["churn_type"] == "involuntary_payment" else ev["reason_code"]},
                "associations": {"companies": {"results": [{"id": self.hs[cid], "type": "deal_to_company"}]}}})
        self.orgs = [{"id": self.org[c["customer_id"]], "name": c["name"], "domain_names": [c["domain"]]}
                     for c in customers]
        sev = {"low": "low", "medium": "normal", "high": "high"}
        self.tickets = [{
            "id": int(t["ticket_id"].split("-")[-1]), "created_at": t["created_at"] + "Z",
            "organization_id": self.org[t["customer_id"]], "priority": sev[t["severity"]],
            "group_id": 1 if t["tier"] == "tier1" else 2,
            "custom_fields": [{"id": 901, "value": t["category"]}, {"id": 902, "value": t["handle_minutes"]}],
            "satisfaction_rating": {"score": ("good" if int(t["csat"]) >= 4 else "bad") if t["csat"] else "unoffered"},
        } for t in _rows(company, "support")]
        self.calls: list[str] = []
        self.fail: dict[str, int] = {}  # path prefix -> status code to return

    # --- base export keyed by billing ids ---------------------------------------------------------------------
    def write_base_export(self, root: Path) -> Path:
        src, dst = FIX / self.company, root / self.company
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy(src / "company.json", dst / "company.json")
        manifest = json.loads((src / "manifest.json").read_text())
        keep = ["pnl", "arr", "usage", "contracts", "headcount", "documents"]
        manifest["datasets"] = {k: v for k, v in manifest["datasets"].items() if k in keep}
        for name in keep:
            rows = _rows(self.company, name)
            if rows and "customer_id" in rows[0]:
                for r in rows:
                    r["customer_id"] = self.cus[r["customer_id"]]
            with (dst / f"{name}.csv").open("w", encoding="utf-8", newline="\n") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
        (dst / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    # --- transport ------------------------------------------------------------------------------------------------
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, req: httpx.Request) -> httpx.Response:
        path, q = req.url.path, dict(req.url.params)
        self.calls.append(f"{req.url.host}{path}?{req.url.query.decode() if isinstance(req.url.query, bytes) else req.url.query}")
        for prefix, code in self.fail.items():
            if path.startswith(prefix):
                return httpx.Response(code, json={"error": "simulated"})
        if req.url.host == "api.stripe.com":
            items = {"/v1/customers": self.stripe_customers, "/v1/prices": self.prices, "/v1/invoices": self.invoices,
                     "/v1/credit_notes": self.credit_notes}[path]
            limit = int(q.get("limit", 10))
            start = 0
            if q.get("starting_after"):
                start = next(i for i, x in enumerate(items) if x["id"] == q["starting_after"]) + 1
            page = items[start:start + limit]
            return httpx.Response(200, json={"object": "list", "data": page, "has_more": start + limit < len(items)})
        if req.url.host == "api.hubapi.com":
            items = {"/crm/v3/objects/companies": self.hs_companies, "/crm/v3/objects/deals": self.deals}[path]
            limit, start = int(q.get("limit", 10)), int(q.get("after", 0))
            body: dict[str, Any] = {"results": items[start:start + limit]}
            if start + limit < len(items):
                body["paging"] = {"next": {"after": str(start + limit)}}
            return httpx.Response(200, json=body)
        if path == "/api/v2/organizations.json":
            page = int(q.get("page", 1))
            size = 100
            chunk = self.orgs[(page - 1) * size: page * size]
            nxt = f"https://acme.zendesk.com/api/v2/organizations.json?page={page + 1}" if page * size < len(self.orgs) else None
            return httpx.Response(200, json={"organizations": chunk, "next_page": nxt})
        if path == "/api/v2/incremental/tickets/cursor.json":
            start = int(q.get("cursor", 0))
            size = 1000
            chunk = self.tickets[start:start + size]
            end = start + size >= len(self.tickets)
            return httpx.Response(200, json={"tickets": chunk, "after_cursor": None if end else str(start + size),
                                             "end_of_stream": end})
        return httpx.Response(404)
