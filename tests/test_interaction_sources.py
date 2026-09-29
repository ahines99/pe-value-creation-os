"""Exact source scope, independent worked pool budgets and saved source challenges."""

import json
from datetime import date
from decimal import Decimal

import pytest
from scripts.build_operating_sources_example import example as source_example

from pe_value_os import security
from pe_value_os.diligence.cases import RevisionDraft
from pe_value_os.diligence.interactions import InteractionCase
from pe_value_os.diligence.operating_sources import (
    AllocatedSourceBook,
    OperatingSourceBook,
    operating_records,
    source_forecast,
)
from pe_value_os.diligence.operating_sources_render import build_sources_report
from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
from pe_value_os.diligence.source_revisions import SourceCasePayload
from pe_value_os.diligence.underwriting import Entry, totals

from .test_benefit_interactions import paired
from .test_case_revisions import principal, setup
from .test_interaction_workflow import plan_for, revision


def fixture(kind="pricing", mode="partition", shares=(".4", ".3")):
    raw, parent, alternative, _ = paired(kind, mode, shares, **{"cost-action": "50000", "contacts": "20000"})
    case = InteractionCase.model_validate(raw)
    plan_raw = plan_for(case, parent, alternative).model_dump(mode="json")
    # Isolate source economics: these test budgets are explicitly constructed.
    plan_raw["maximum_active_workstreams"] = 4
    for resource in plan_raw["resources"]:
        resource["weekly_hours"] = ["100"] * 15
    plan = OperatingPlan.model_validate(plan_raw)
    book_raw = source_example().model_dump(mode="json")
    book_raw.update(underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan))
    renewal = book_raw["renewals"][0]
    renewal.update(
        record_id="one-contract",
        contract_id="one-contract",
        monthly_revenue="3100",
        renewal_on="2027-01-01",
        term_ends_on="2027-01-31",
        notice_days=0,
        uplift_cap=".5",
    )
    service = book_raw["service_months"][3]
    service.update(vendor_minimum="88000", release_on="2027-01-01")
    invoice = book_raw["invoices"][0]
    invoice.update(record_id="one-invoice", invoice_id="one-invoice", amount="1000", paid_at_cutoff="0")
    book_raw.update(
        renewals=[renewal],
        service_months=[service],
        invoices=[invoice],
        renewal_monthly_revenue_control="3100",
        invoice_open_balance_control="1000",
    )
    records = OperatingSourceBook.model_validate(book_raw)
    book = wrap(records, case)
    return case, plan, book, parent, alternative


def wrap(records, case):
    kinds = {d.kind: d.benefit_pool for d in case.scenarios[0].drivers}
    expected = {"renewal": "pricing", "service_month": "service", "invoice": "collections"}
    return AllocatedSourceBook.model_validate(
        {
            "schema_version": 3,
            "records": records.model_dump(mode="json"),
            "pool_ids": [p.pool_id for p in case.interaction_policy.pools],
            "assignments": [
                {"kind": kind, "record_id": key, "record_sha256": fingerprint(row), "pool_id": kinds[expected[kind]]}
                for (kind, key), row in operating_records(records).items()
            ],
            "allocation_rationale": "Authored same-record shares; no company impact asserted",
        }
    )


def base(report):
    return next(s for s in report["scenarios"] if s["scenario_id"] == "base")


def rebound(case, plan, book):
    plan_raw = plan.model_dump(mode="json")
    plan_raw["underwriting_sha256"] = fingerprint(case)
    plan = OperatingPlan.model_validate(plan_raw)
    raw = book.records.model_dump(mode="json")
    raw.update(underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan))
    return plan, wrap(OperatingSourceBook.model_validate(raw), case)


def test_one_contract_allocated_before_rates_and_settled_after_term():
    case, plan, book, parent, alternative = fixture()
    result = source_forecast(book, case, plan)
    scenario = base(result)
    entries = tuple(Entry.model_validate(e) for e in scenario["entries"] if e["reference"] == "renewal:one-contract")
    jan = totals(entries, date(2027, 1, 1), date(2027, 1, 31))
    # 70% of 3,100 at 10% uplift, 5% churn, 20% variable cost.
    assert jan["gross_price_benefit"] == Decimal("206.15")
    assert jan["revenue_leakage"] == Decimal("-108.50")
    assert jan["variable_cost"] == Decimal("-19.53")
    assert jan["incremental_ebitda"] == Decimal("78.12")
    assert totals(entries, case.start, date(2027, 1, 8))["incremental_ebitda"] == Decimal("20.16")
    feb = totals(entries, date(2027, 2, 1), date(2027, 2, 28))
    assert feb["incremental_ebitda"] == 0 and feb["operating_cash"] == Decimal("97.65")
    assert {e.initiative_id for e in entries} == {parent, alternative}
    raw = case.model_dump(mode="json")
    raw["interaction_policy"]["selected_initiatives"].remove(alternative)
    excluded = InteractionCase.model_validate(raw)
    p, b = rebound(excluded, plan, book)
    reduced = base(source_forecast(b, excluded, p))
    assert sum(
        Decimal(e["amount"])
        for e in reduced["entries"]
        if e["reference"] == "renewal:one-contract" and e["component"] == "gross_price_benefit"
    ) == Decimal("117.8")
    assert (
        next(
            d
            for d in reduced["decisions"]
            if d.get("record_id") == "one-contract" and d["initiative_id"] == alternative
        )["reason"]
        == "Excluded by the recorded selection"
    )


def test_service_allocates_qa_and_vendor_minimum_before_financial_cap():
    case, plan, book, _, _ = fixture("service")
    scenario = base(source_forecast(book, case, plan))
    january = scenario["monthly"][3]
    # Full pool: 7,000 contacts * .6 resolution * .2 hour - 80 QA = 760 hours.
    # Shared vendor commitment leaves 12,000 releasable; 70% budget = 8,400.
    assert january["capacity_hours"] == 532
    assert january["cost_removed"] == 8400
    decisions = [d for d in scenario["decisions"] if d["kind"] == "service" and "qa_hours_allocated" in d]
    assert sum(d["qa_hours_allocated"] for d in decisions) == 56
    assert sum(d["vendor_minimum_allocated"] for d in decisions) == 61600
    records = book.records.model_dump(mode="json")
    records["service_months"][0].update(release_on=None, release_evidence=None)
    no_release = wrap(OperatingSourceBook.model_validate(records), case)
    challenged = base(source_forecast(no_release, case, plan))
    assert challenged["total"]["capacity_hours"] == 532
    assert challenged["total"]["cost_removed"] == 0
    records["service_months"] = []
    missing = wrap(OperatingSourceBook.model_validate(records), case)
    report = source_forecast(missing, case, plan)
    assert base(report)["total"]["capacity_hours"] == base(report)["total"]["cost_removed"] == 0
    assert len(report["unrepresented_pools"]) == 1
    assert len([d for d in base(report)["decisions"] if d["reason"] == "Missing service month"]) == 48


def test_invoice_share_retains_exact_reversal_and_never_creates_earnings():
    case, plan, book, _, _ = fixture("collections")
    result = base(source_forecast(book, case, plan))
    rows = [Entry.model_validate(e) for e in result["entries"] if e["reference"] == "invoice:one-invoice"]
    assert sum(e.amount for e in rows if e.amount > 0) == 105  # 1000 * .15 * .7
    assert sum(e.amount for e in rows) == 0
    assert all(e.component == "working_capital_cash" for e in rows)
    assert all(e.day == date(2027, 3, 15) for e in rows if e.amount < 0)


def test_exclusive_record_selection_and_subcent_pool_conservation():
    case, plan, book, parent, alternative = fixture(mode="exclusive")
    result = base(source_forecast(book, case, plan))
    assert not any(e["initiative_id"] == alternative for e in result["entries"])
    assert sum(
        Decimal(e["amount"])
        for e in result["entries"]
        if e["initiative_id"] == parent and e["component"] == "gross_price_benefit"
    ) == Decimal("294.50")
    case, plan, book, _, _ = fixture(shares=(".5", ".5"))
    raw = case.model_dump(mode="json")
    for scenario in raw["scenarios"]:
        for assumption in scenario["assumptions"]:
            if assumption["assumption_id"] == "churn":
                assumption["value"] = "0"
    case = InteractionCase.model_validate(raw)
    plan, book = rebound(case, plan, book)
    raw_book = book.records.model_dump(mode="json")
    raw_book["renewals"][0]["monthly_revenue"] = ".1"
    raw_book["renewal_monthly_revenue_control"] = ".1"
    book = wrap(OperatingSourceBook.model_validate(raw_book), case)
    scenario = base(source_forecast(book, case, plan))
    assert sum(
        Decimal(e["amount"])
        for e in scenario["entries"]
        if e["reference"] == "renewal:one-contract" and e["component"] == "gross_price_benefit"
    ) == Decimal(".01")


@pytest.mark.parametrize(
    "mutation,pattern",
    [
        ("duplicate", "exactly once"),
        ("missing", "exactly once"),
        ("hash", "exact source record"),
        ("pool", "undeclared pool"),
        ("kind", "economic mechanism"),
        ("manifest", "every economic pool"),
    ],
)
def test_source_pool_scope_cannot_be_inferred_or_duplicated(mutation, pattern):
    case, plan, book, _, _ = fixture()
    raw = book.model_dump(mode="json")
    if mutation == "duplicate":
        raw["assignments"].append(raw["assignments"][0])
    elif mutation == "missing":
        raw["assignments"].pop()
    elif mutation == "hash":
        raw["assignments"][0]["record_sha256"] = "0" * 64
    elif mutation == "pool":
        raw["assignments"][0]["pool_id"] = "made-up"
    elif mutation == "kind":
        raw["assignments"][0]["pool_id"] = raw["assignments"][1]["pool_id"]
    else:
        raw["pool_ids"].append("made-up")
    with pytest.raises(ValueError, match=pattern):
        source_forecast(AllocatedSourceBook.model_validate(raw), case, plan)
    with pytest.raises(ValueError, match="explicit source-pool adapter"):
        source_forecast(book.records, case, plan)


def test_saved_source_allocation_roundtrip_and_policy_cannot_be_dropped(repo):
    case, plan, book, parent, _ = fixture()
    with security.principal_scope(principal()):
        investment = setup(repo)
        original = repo.append_case_revision(investment.case_id, None, revision(case, plan))
        record = book.records.renewals[0]
        payload = SourceCasePayload.model_validate(
            {
                **original.draft.payload.model_dump(mode="json"),
                "schema_version": 2,
                "operating_sources": book.model_dump(mode="json"),
                "challenged_revision_id": original.revision_id,
                "challenged_revision_sha256": original.content_sha256,
                "lessons": [
                    {
                        "lesson_id": "scoped-record",
                        "initiative_id": parent,
                        "scenario_id": "base",
                        "assumption_ids": ["eligible-revenue"],
                        "source_records": [
                            {"kind": "renewal", "record_id": record.record_id, "record_sha256": fingerprint(record)}
                        ],
                        "finding": "One contract shared across choices",
                        "response": "Apply the authored shares once",
                        "follow_up_evidence": "Sponsor and company source reconciliation",
                    }
                ],
            }
        )
        saved = repo.append_case_revision(
            investment.case_id,
            original.revision_id,
            RevisionDraft(
                stage="ownership_review",
                effective_on=date(2027, 3, 1),
                reason="Bounded source challenge",
                payload=payload,
            ),
        )
        assert repo.get_case_revision(saved.revision_id) == saved
        financial = json.loads(saved.financial_result_json)
        assert financial["calculation_version"] == "operating-source-forecast/3"
        assert financial["interaction_policy"] == case.interaction_policy.model_dump(mode="json")
        assert all(s["valuation"] == [] for s in financial["scenarios"])
        raw = case.model_dump(mode="json")
        raw.update(schema_version=1)
        del raw["interaction_policy"]
        for scenario in raw["scenarios"]:
            for d in scenario["drivers"]:
                d["benefit_pool"] = d["initiative_id"]
        from pe_value_os.diligence.underwriting import UnderwritingCase

        with pytest.raises(ValueError, match="discard its interaction policy"):
            repo.append_case_revision(
                investment.case_id,
                saved.revision_id,
                revision(UnderwritingCase.model_validate(raw), stage="ownership_review").model_copy(
                    update={"effective_on": date(2027, 3, 1)}
                ),
            )


def test_allocation_source_cli_report_keeps_scope_visible(tmp_path):
    case, plan, book, _, _ = fixture()
    paths = [tmp_path / name for name in ("case.json", "plan.json", "book.json")]
    for path, model in zip(paths, (case, plan, book), strict=True):
        path.write_text(model.model_dump_json(), encoding="utf-8")
    page = build_sources_report(paths[2], paths[0], paths[1], tmp_path / "report")
    html = page.read_text(encoding="utf-8")
    assert "One record per economic pool" in html
    assert "member evaluations" in html
    assert "One economic pool, explicit choices" in html
    assert "pricing-renewals-alternative" in html
