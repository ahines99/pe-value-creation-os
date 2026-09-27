"""HubSpot CRM adapter (PVC-112): customers (companies), opportunities (deals) and churn (lost renewals).

Read-only private-app token with crm.objects.companies.read and crm.objects.deals.read. Uses CRM v3 object
list endpoints with `after` cursor paging and deal-to-company associations.

Property contract (configure in HubSpot; names can be remapped with `props`):
- company: name, domain, pvc_segment, pvc_size_band, pvc_acquisition_channel, pvc_first_contract_date
- deal: dealname, amount, createdate, closedate, dealstage, dealtype, pvc_opportunity_type, closed_lost_reason
Opportunity type: `pvc_opportunity_type` if set, else dealtype newbusiness -> new, existingbusiness -> expansion.
Churn: closed-lost renewals become churn events; reason "payment_failed" maps to involuntary_payment. CRM
reason codes are sales-entered and low-trust (skills/customer-retention).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from ..domain.source_models import Dataset, DatasetKind
from .base import EvidenceSink
from .sources import ApiClient, dataset_from_records

COMPANY_PROPS = ["name", "domain", "pvc_segment", "pvc_size_band", "pvc_acquisition_channel", "pvc_first_contract_date"]
DEAL_PROPS = [
    "dealname",
    "amount",
    "createdate",
    "closedate",
    "dealstage",
    "dealtype",
    "pvc_opportunity_type",
    "closed_lost_reason",
]


def _date(v: str | None) -> str | None:
    return v[:10] if v else None


def _month(v: str) -> str:
    d = date.fromisoformat(v[:10])
    return date(d.year, d.month, 1).isoformat()


class HubSpotCrmAdapter:
    name = "hubspot"
    provides = frozenset({DatasetKind.CUSTOMERS, DatasetKind.CRM_OPPORTUNITIES, DatasetKind.CHURN})

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.hubapi.com",
        transport: httpx.BaseTransport | None = None,
        page_size: int = 100,
    ):
        self.api = ApiClient(base_url, {"Authorization": f"Bearer {token}"}, transport=transport)
        self.page_size = page_size

    def _list(
        self, obj: str, props: list[str], associations: str | None = None
    ) -> tuple[list[dict[str, Any]], list[Any]]:
        out: list[dict[str, Any]] = []
        pages: list[Any] = []
        after = None
        while True:
            params: dict[str, Any] = {"limit": self.page_size, "properties": ",".join(props)}
            if associations:
                params["associations"] = associations
            if after:
                params["after"] = after
            page = self.api.get(f"/crm/v3/objects/{obj}", params)
            pages.append(page)
            out += page.get("results", [])
            after = page.get("paging", {}).get("next", {}).get("after")
            if not after:
                return out, pages

    def load_datasets(self, company_id: str, sink: EvidenceSink | None) -> dict[DatasetKind, Dataset]:
        companies, c_pages = self._list("companies", COMPANY_PROPS)
        deals, d_pages = self._list("deals", DEAL_PROPS, associations="companies")
        customers = [
            {
                "customer_id": c["id"],
                "name": c["properties"].get("name"),
                "segment": c["properties"].get("pvc_segment"),
                "size_band": c["properties"].get("pvc_size_band"),
                "acquisition_channel": c["properties"].get("pvc_acquisition_channel"),
                "first_contract_date": _date(c["properties"].get("pvc_first_contract_date")),
                "crm_account_id": c["id"],
                "domain": c["properties"].get("domain"),
            }
            for c in companies
        ]
        opps, churn = [], []
        for d in deals:
            p = d["properties"]
            assoc = d.get("associations", {}).get("companies", {}).get("results", [])
            cust = assoc[0]["id"] if assoc else "prospect"
            stage = {"closedwon": "won", "closedlost": "lost"}.get(p.get("dealstage") or "", "open")
            otype = p.get("pvc_opportunity_type") or {"newbusiness": "new", "existingbusiness": "expansion"}.get(
                p.get("dealtype") or "", "new"
            )
            opps.append(
                {
                    "opportunity_id": d["id"],
                    "customer_id": cust,
                    "created_date": _date(p.get("createdate")),
                    "close_date": _date(p.get("closedate")),
                    "stage": stage,
                    "opportunity_type": otype,
                    "amount": p.get("amount") or "0",
                }
            )
            if otype == "renewal" and stage == "lost" and cust != "prospect" and p.get("closedate"):
                reason = p.get("closed_lost_reason") or None
                churn.append(
                    {
                        "customer_id": cust,
                        "month": _month(p["closedate"]),
                        "churn_type": "involuntary_payment" if reason == "payment_failed" else "voluntary",
                        "reason_code": None if reason == "payment_failed" else reason,
                        "notes": None,
                    }
                )
        return {
            DatasetKind.CUSTOMERS: dataset_from_records(
                DatasetKind.CUSTOMERS,
                company_id,
                customers,
                source_uri="hubspot://crm/v3/companies",
                as_of=None,
                sink=sink,
                raw_payload=c_pages,
            ),
            DatasetKind.CRM_OPPORTUNITIES: dataset_from_records(
                DatasetKind.CRM_OPPORTUNITIES,
                company_id,
                opps,
                source_uri="hubspot://crm/v3/deals",
                as_of=None,
                sink=sink,
                raw_payload=d_pages,
            ),
            DatasetKind.CHURN: dataset_from_records(
                DatasetKind.CHURN,
                company_id,
                churn,
                source_uri="hubspot://crm/v3/deals#lost-renewals",
                as_of=None,
                sink=sink,
                raw_payload=d_pages,
            ),
        }
