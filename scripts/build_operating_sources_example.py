"""Authored contracts, service schedules and invoices, never company records."""

from datetime import date
from pathlib import Path

from scripts.build_operating_plan_example import example as plan_example
from scripts.build_underwriting_example import example as underwriting_example

from pe_value_os.diligence.operating_sources import OperatingSourceBook
from pe_value_os.diligence.scheduling import fingerprint
from pe_value_os.diligence.underwriting import month_start


def example() -> OperatingSourceBook:
    case, plan = underwriting_example(), plan_example()
    renewals = []
    for key, revenue, renewal, term_end, days, permission, cap in (
        ("early-90-day", "300000", "2027-01-01", "2027-12-31", 90, "yes", ".05"),
        ("spring-capped", "250000", "2027-04-01", "2028-03-31", 90, "yes", ".04"),
        ("short-term", "150000", "2027-02-01", "2027-06-30", 30, "yes", ".03"),
        ("prohibited", "200000", "2027-04-01", "2028-03-31", 30, "no", "0"),
        ("unknown-rights", "100000", "2027-04-01", "2028-03-31", 30, "unknown", None),
    ):
        renewals.append(
            {
                "record_id": key,
                "contract_id": "constructed-" + key,
                "monthly_revenue": revenue,
                "renewal_on": renewal,
                "term_ends_on": term_end,
                "notice_days": days,
                "planned_notice_on": "2026-10-01",
                "permitted": permission,
                "uplift_cap": cap,
                "evidence_locator": "Authored contract term: " + key,
            }
        )
    service = []
    for index in range(24):
        month = month_start(case.start, index)
        service.append(
            {
                "month": month,
                "contacts_control": 20000,
                "qa_hours": "80",
                "vendor_spend": "100000",
                "vendor_minimum": "82000",
                "avoidable_hourly_rate": "35",
                "release_on": "2027-02-15",
                "release_evidence": "Constructed vendor amendment with February 15 effective date",
                "queues": [
                    {
                        "queue_id": "standard",
                        "contacts": 12000,
                        "eligible_contacts": 8000,
                        "handling_minutes": "12",
                        "sample_count": 100,
                        "resolved_count": 90,
                        "recontact_count": 10,
                        "quality_review": "passed",
                        "evidence_locator": "Authored standard queue and 100-case evaluation",
                    },
                    {
                        "queue_id": "sensitive",
                        "contacts": 8000,
                        "eligible_contacts": 3000,
                        "handling_minutes": "18",
                        "sample_count": 100,
                        "resolved_count": 95,
                        "recontact_count": 5,
                        "quality_review": "failed",
                        "evidence_locator": "Authored quality challenge; high resolution does not clear safety review",
                    },
                ],
            }
        )
    invoices = []
    for key, amount, credited, paid, disputed, original in (
        ("open", "700000", "0", "100000", "0", "2027-03-15"),
        ("partial-dispute", "400000", "50000", "50000", "150000", "2027-03-15"),
        ("full-dispute", "300000", "0", "0", "300000", "2027-04-15"),
        ("already-paid", "100000", "0", "100000", "0", "2027-03-15"),
        ("window-missed", "100000", "0", "0", "0", "2026-10-15"),
    ):
        invoices.append(
            {
                "record_id": key,
                "invoice_id": "constructed-" + key,
                "issued_on": "2026-08-01",
                "due_on": "2026-09-30",
                "amount": amount,
                "credited": credited,
                "paid_at_cutoff": paid,
                "disputed": disputed,
                "accelerated_on": "2026-10-01",
                "counterfactual_on": original,
                "evidence_locator": "Authored invoice and payment counterfactual: " + key,
            }
        )
    return OperatingSourceBook.model_validate(
        {
            "schema_version": 1,
            "classification": "constructed_operating_records",
            "book_id": "progress-constructed-source-review-v1",
            "case_id": case.case_id,
            "company": case.company,
            "currency": case.currency,
            "underwriting_sha256": fingerprint(case),
            "plan_sha256": fingerprint(plan),
            "cutoff": date(2026, 10, 1),
            "renewal_monthly_revenue_control": "1000000",
            "invoice_open_balance_control": "1300000",
            "scope_description": "Five authored renewal contracts, a single vendor pool with two queues in 24 authored monthly plans, and five opening invoices. These controls reconcile this exercise only, not any Progress account or segment.",
            "renewals": renewals,
            "service_months": service,
            "invoices": invoices,
        }
    )


if __name__ == "__main__":
    destination = Path("data/constructed/progress/operating-sources.json")
    destination.write_text(example().model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {destination}")
