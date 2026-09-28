"""Identity changes preserve sources, historical authority and the measurement perimeter."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.cases import CaseRevision, InvestmentCase, RevisionDraft, prepare_revision
from pe_value_os.diligence.lineage import LineageCasePayload, mapped_priority
from pe_value_os.diligence.lineage_example import (
    CHILDREN,
    MERGED,
    merge_lineage,
    revise_kpi_target,
    seed_lineage,
    split_lineage,
)
from pe_value_os.diligence.lineage_kpis import LineageKpiBook, kpi_report

from .test_case_revisions import principal, request
from .test_realization import claim, ready
from .test_source_revisions import append


def saved_parent():
    raw = json.loads(Path("docs/portfolio/source-review.json").read_bytes())
    return CaseRevision.model_validate(raw["revisions"][-1])


def advance(parent, draft):
    case = InvestmentCase(
        case_id=parent.case_id,
        company_id=parent.company_id,
        label="Constructed lineage test",
        currency=parent.draft.payload.underwriting.currency,
        created_by="test",
        created_at=parent.recorded_at,
        version=parent.sequence,
        current_revision_id=parent.revision_id,
        original_revision_id=parent.revision_id,
    )
    with security.principal_scope(principal(parent.company_id)):
        return prepare_revision(case, draft, parent)


def history():
    original = saved_parent()
    seed = advance(original, seed_lineage(original))
    split = advance(seed, split_lineage(seed))
    return original, seed, split


def test_lineage_sequence_preserves_targets_readings_costs_and_family_totals():
    original, seed, split = history()
    snapshots = [r.model_dump_json() for r in (original, seed, split)]
    revised = advance(split, revise_kpi_target(split))
    merged = advance(revised, merge_lineage(revised))
    assert [r.model_dump_json() for r in (original, seed, split)] == snapshots
    assert seed.draft.payload.kpis.observations[0].definition_id == "pricing-kpi-v1"
    assert (
        revised.draft.payload.kpis.observations[: len(split.draft.payload.kpis.observations)]
        == split.draft.payload.kpis.observations
    )
    assert len(merged.draft.payload.lineage_events) == 2
    assert len(merged.draft.payload.kpis.definitions) == 7
    assert len(merged.draft.payload.kpis.observations) == 15
    definitions = {d.definition_id: d for d in merged.draft.payload.kpis.definitions}
    assert definitions[CHILDREN[0] + "-kpi-v1"].target == Decimal("0.025")
    assert definitions[CHILDREN[0] + "-kpi-v2"].target == Decimal("0.04")
    for revision in (seed, split, revised, merged):
        financial = json.loads(revision.financial_result_json)
        lineage = financial["lineage_review"]
        for scenario, comparison in zip(financial["scenarios"], lineage["scenarios"], strict=True):
            for metric in ("incremental_ebitda", "pre_tax_cash_proxy", "implementation_expense", "recurring_cost"):
                assert sum(Decimal(f["current"]["year_one"][metric]) for f in comparison["families"]) == Decimal(
                    scenario["year_one"][metric]
                )
        assert lineage["kpis"]["historical_child_actuals"] is None
        assert lineage["kpis"]["financial_attribution"] is None
    report = json.loads(split.financial_result_json)["lineage_review"]["kpis"]
    pricing = next(g for g in report["current_population_observations"] if g["metric"] == "net_price_uplift")
    assert Decimal(pricing["value"]) == Decimal("0.0175")  # 17,500 / 1m, not mean(4%, 1%).
    assert pricing["value"] != "0.025"
    merged_financials = json.loads(merged.financial_result_json)
    family = next(f for f in merged_financials["lineage_review"]["families"] if MERGED in f["current_ids"])
    assert family["original_ids"] == ["pricing-renewals"]
    assert set(family["all_identities"]) == {"pricing-renewals", *CHILDREN, MERGED}
    original_order = list(original.draft.payload.operating_plan.priority_order)
    assert set(mapped_priority(merged.draft.payload, original_order)) == {
        t.task_id for t in merged.draft.payload.operating_plan.tasks
    }


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("shares", "conserve"),
        ("parent", "exact prior"),
        ("record", "preserve source"),
        ("cost", "cost amount"),
        ("extent", "reference population"),
        ("unit_economics", "unit economics"),
        ("tasks", "every retired package"),
        ("target_history", "retain all prior"),
        ("kpi_predecessor", "predecessor initiative"),
        ("future_reading", "future evidence"),
    ],
)
def test_split_rejects_silent_economic_or_historical_changes(change, pattern):
    parent = saved_parent()
    seed = advance(parent, seed_lineage(parent))
    raw = split_lineage(seed).model_dump(mode="json")
    payload, source = raw["payload"], raw["payload"]["basis"]
    if change == "shares":
        payload["lineage_events"][-1]["edges"][0]["reference_allocation"] = "0.5"
    elif change == "parent":
        payload["lineage_events"][-1]["parent_revision_sha256"] = "a" * 64
    elif change == "tasks":
        payload["lineage_events"][-1]["task_edges"].pop()
    elif change == "target_history":
        payload["kpis"]["observations"][0]["numerator"] = "9999"
    elif change == "kpi_predecessor":
        payload["kpis"]["definitions"][-1]["predecessor_definition_ids"] = []
    elif change == "future_reading":
        raw["effective_on"] = "2027-04-29"
        payload["lineage_events"][-1]["effective_on"] = raw["effective_on"]
    else:
        # Rebind envelopes: the semantic conservation checks must still reject a
        # tampered but internally rehashed proposal.
        from pe_value_os.diligence.operating_sources import (
            OperatingSourceBook,
            PartitionedSourceBook,
            operating_records,
        )
        from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
        from pe_value_os.diligence.underwriting import UnderwritingCase

        if change == "record":
            source["operating_sources"]["records"]["renewals"][0]["notice_days"] = 89
            records = OperatingSourceBook.model_validate(source["operating_sources"]["records"])
            for assignment in source["operating_sources"]["assignments"]:
                assignment["record_sha256"] = fingerprint(
                    operating_records(records)[(assignment["kind"], assignment["record_id"])]
                )
            for definition in payload["kpis"]["definitions"][-2:]:
                for ref in definition["population"]:
                    ref["record_sha256"] = fingerprint(operating_records(records)[(ref["kind"], ref["record_id"])])
            for lesson in source["lessons"]:
                for ref in lesson["source_records"]:
                    ref["record_sha256"] = fingerprint(operating_records(records)[(ref["kind"], ref["record_id"])])
        else:
            scenario = source["underwriting"]["scenarios"][1]
            driver = next(d for d in scenario["drivers"] if d["initiative_id"] == CHILDREN[0])
            key = (
                scenario["costs"][0]["amount"]
                if change == "cost"
                else driver["monthly_eligible_revenue"]
                if change == "extent"
                else driver["capture"]
            )
            assumption = next(a for a in scenario["assumptions"] if a["assumption_id"] == key)
            assumption["value"] = str(Decimal(assumption["value"]) / 2)
        source["operating_plan"]["underwriting_sha256"] = fingerprint(
            UnderwritingCase.model_validate(source["underwriting"])
        )
        source["operating_sources"]["records"].update(
            underwriting_sha256=source["operating_plan"]["underwriting_sha256"],
            plan_sha256=fingerprint(OperatingPlan.model_validate(source["operating_plan"])),
        )
        payload["lineage_events"][-1]["revised_underwriting_sha256"] = source["operating_plan"]["underwriting_sha256"]
        PartitionedSourceBook.model_validate(source["operating_sources"])
    with pytest.raises(ValueError, match=pattern):
        advance(seed, RevisionDraft.model_validate(raw))


def test_missing_child_observation_is_not_filled_from_parent_or_sibling():
    _, _, split = history()
    raw = split.draft.payload.kpis.model_dump(mode="json")
    raw["observations"] = [o for o in raw["observations"] if o["observation_id"] != "other-april"]
    report = kpi_report(
        LineageKpiBook.model_validate(raw),
        {d.initiative_id for d in split.draft.payload.underwriting.scenarios[0].drivers},
    )
    group = next(g for g in report["current_population_observations"] if g["metric"] == "net_price_uplift")
    assert group["value"] is None and group["status"] == "missing_current_population"
    assert report["historical_child_actuals"] is None


def test_repository_lineage_preserves_frozen_accounting_and_scope(repo, monkeypatch):
    with security.principal_scope(principal()):
        case, close, _, baseline, req = ready(repo)
        observation = repo.record_case_observation(case.case_id, req)
        attribution = repo.record_case_attribution(case.case_id, claim(observation))
        source = append(repo, case, close)
        before = repo.case_realization(case.case_id, baseline.baseline_id)
        parent = source
        revisions = []
        for builder in (seed_lineage, split_lineage, revise_kpi_target, merge_lineage):
            revision = repo.append_case_revision(case.case_id, parent.revision_id, builder(parent))
            repo.review_case_revision(revision.revision_id, request(revision))
            assert repo.get_case_revision(revision.revision_id) == revision
            revisions.append(revision)
            parent = revision
        after = repo.case_realization(case.case_id, baseline.baseline_id)
        for key in ("baseline", "observations", "attributions"):
            assert before[key] == after[key]
        for key in ("measured_difference", "attributed_difference", "unassigned_residual"):
            assert before["aggregate_recorded_periods"][key] == after["aggregate_recorded_periods"][key]
        assert repo.list_case_observations(case.case_id) == [observation]
        assert repo.list_case_attributions(case.case_id) == [attribution]
        assert after["version"] == "constructed-realization/2"
        comparison = after["initiative_comparability"]
        assert comparison["historical_child_allocations"] is None
        assert next(x for x in comparison["frozen_to_current"] if x["frozen_initiative_id"] == "pricing-renewals")[
            "current_ids"
        ] == [MERGED]
        audit = repo.list_audit(company_id="exercise")
        from pe_value_os.diligence.lineage_demo import lineage_exit_draft

        from .test_exit_review import inputs

        def fail(*args, **kwargs):
            raise RuntimeError("injected audit failure")

        with monkeypatch.context() as patch:
            patch.setattr(repo, "append_audit", fail)
            with pytest.raises(RuntimeError, match="audit failure"):
                repo.append_case_revision(case.case_id, parent.revision_id, lineage_exit_draft(parent, *inputs()))
        assert repo.list_audit(company_id="exercise") == audit
        assert repo.get_investment_case(case.case_id).current_revision_id == parent.revision_id
        with pytest.raises(Conflict):
            repo.append_case_revision(case.case_id, revisions[0].revision_id, split_lineage(revisions[0]))
        drop = parent.draft.payload.source_basis.model_dump(mode="json")
        drop.update(challenged_revision_id=parent.revision_id, challenged_revision_sha256=parent.content_sha256)
        with pytest.raises(ValueError, match="cannot discard"):
            repo.append_case_revision(
                case.case_id,
                parent.revision_id,
                RevisionDraft(
                    stage="ownership_review", effective_on=date(2027, 6, 30), reason="Invalid discard", payload=drop
                ),
            )
    with security.principal_scope(principal("outsider")):
        with pytest.raises(NotFound):
            repo.get_case_revision(parent.revision_id)
    for kind in ("service", "model"):
        with security.principal_scope(principal(kind=kind)):
            with pytest.raises(security.ScopeError):
                repo.review_case_revision(parent.revision_id, request(parent, mode="human"))
    with security.principal_scope(principal()):
        count = len(repo.list_case_revisions(case.case_id))
        assert repo.delete_company_data("exercise")["case_revisions"] == count
        with pytest.raises(NotFound):
            repo.get_case_revision(parent.revision_id)


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("definition_rewrite", "population"),
        ("duplicate_reading", "latest same-definition"),
        ("wrong_correction", "latest same-definition"),
        ("bad_evidence", "evidence hash"),
        ("beyond_calendar", "case calendar"),
        ("stale_definition", "current definition"),
    ],
)
def test_kpi_revisions_reject_ambiguous_or_unbound_measurements(change, pattern):
    _, _, split = history()
    raw = revise_kpi_target(split).model_dump(mode="json")
    book = raw["payload"]["kpis"]
    if change == "definition_rewrite":
        book["definitions"][-1]["baseline_numerator"] = "25000"
    elif change == "duplicate_reading":
        item = dict(book["observations"][0], observation_id="duplicate")
        book["observations"].append(item)
    elif change == "wrong_correction":
        book["observations"][-5]["supersedes_observation_id"] = "other-april"
    elif change == "bad_evidence":
        book["observations"][-1]["evidence"] = "Unbound substitution"
    elif change == "beyond_calendar":
        book["definitions"][-1]["target_on"] = "2030-01-01"
    else:
        from pe_value_os.diligence.lineage_example import reading

        book["observations"].append(
            reading("retired-may", "pricing-kpi-v1", date(2027, 5, 1), "1", "100").model_dump(mode="json")
        )
    with pytest.raises(ValueError, match=pattern):
        advance(split, RevisionDraft.model_validate(raw))


def test_target_and_population_corrections_are_distinct_and_retain_prior_readings():
    _, _, split = history()
    raw = revise_kpi_target(split).model_dump(mode="json")
    target = raw["payload"]["kpis"]["definitions"][-1]
    target.update(
        revision_kind="scope_correction",
        baseline_numerator="2500",
        rationale="Explicit corrected baseline; original remains inspectable",
    )
    revised = advance(split, RevisionDraft.model_validate(raw))
    assert revised.draft.payload.kpis.definitions[-1].baseline_numerator == Decimal("2500")
    assert revised.draft.payload.kpis.definitions[:5] == split.draft.payload.kpis.definitions
    assert revised.draft.payload.kpis.observations[:7] == split.draft.payload.kpis.observations


def test_merge_rejects_incomplete_population_and_identity_reuse():
    _, _, split = history()
    target = advance(split, revise_kpi_target(split))
    raw = merge_lineage(target).model_dump(mode="json")
    raw["payload"]["lineage_events"][-1]["edges"].pop()
    with pytest.raises(ValueError, match="every retired identity"):
        advance(target, RevisionDraft.model_validate(raw))
    raw = merge_lineage(target).model_dump(mode="json")
    for edge in raw["payload"]["lineage_events"][-1]["edges"]:
        edge["successor_id"] = "pricing-renewals"
    with pytest.raises(ValueError, match="cannot be reused"):
        RevisionDraft.model_validate(raw)


def test_lineage_api_roundtrip(repo, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    with security.principal_scope(principal()):
        case, close, _, _, _ = ready(repo)
        parent = append(repo, case, close)
    monkeypatch.setenv(
        "PVC_DEV_TOKENS",
        json.dumps(
            {
                "writer": {
                    "sub": "service:test",
                    "pvc_companies": ["exercise"],
                    "pvc_principal_type": "service",
                    "scope": "pvc.read pvc.write",
                }
            }
        ),
    )
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    client = TestClient(api.app)
    for builder in (seed_lineage, split_lineage):
        response = client.post(
            f"/cases/{case.case_id}/revisions",
            headers={"Authorization": "Bearer writer"},
            json={
                "expected_parent_revision_id": parent.revision_id,
                "draft": builder(parent).model_dump(mode="json"),
            },
        )
        assert response.status_code == 201, response.text
        parent = CaseRevision.model_validate(response.json())
        assert isinstance(parent.draft.payload, LineageCasePayload)
    response = client.get(f"/cases/{case.case_id}", headers={"Authorization": "Bearer writer"})
    assert response.status_code == 200
    assert response.json()["revisions"][-1] == parent.model_dump(mode="json")


def test_full_lineage_replay_exit_and_memo_reproduction(tmp_path):
    from pe_value_os.diligence.cases import digest
    from pe_value_os.diligence.exit_demo import build_exit_demo
    from pe_value_os.diligence.lineage_demo import render_lineage
    from pe_value_os.diligence.memo import assemble_memo
    from pe_value_os.diligence.memo_review import MemoReviewContext

    from .test_decision_memo import inputs
    from .test_exit_review import OPERATING, PUBLIC

    paths = [
        OPERATING / f"{n}.json"
        for n in ("underwriting", "operating-plan", "realization", "execution", "operating-sources")
    ]
    rest = [
        PUBLIC / "financial-facts.json",
        PUBLIC / "balance-facts.json",
        OPERATING / "historical-valuation.json",
        OPERATING / "exit-assumptions.json",
    ]
    output = tmp_path / "lineage"
    build_exit_demo(*paths, *rest, output, include_lineage=True)
    raw = json.loads(output.with_suffix(".json").read_bytes())
    assert len(raw["revisions"]) == 10 and raw["human_review_count"] == 0
    assert raw["actual_company_realized_value"] is None
    context = MemoReviewContext.from_export(raw)
    result = assemble_memo(*inputs(), context)
    assert result["memo_version"] == "executive-decision-packet/5"
    assert result["source_review"]["latest_financials"]["exit_review"]["transaction_proceeds"] is None
    assert "task ancestry" in result["source_review"]["source_treatment"]
    for option in result["source_review"]["options"]:
        assert set(option["plan"]["priority_order"]) == {t["task_id"] for t in option["plan"]["tasks"]}
    for revision in raw["revisions"]:
        assert CaseRevision.model_validate(revision).model_dump(mode="json") == revision
    financial = json.loads(raw["revisions"][-1]["financial_result_json"])
    financial["lineage_review"]["kpis"]["definitions"][0]["rationale"] = "<script>alert(1)</script>"
    raw["revisions"][-1]["financial_result_json"] = json.dumps(financial)
    assert "<script>alert" not in render_lineage(raw, "lineage.json")
    last = raw["revisions"][-1]
    last["content_sha256"] = digest(
        json.dumps({k: v for k, v in last.items() if k != "content_sha256"}, sort_keys=True)
    )
    raw["source_review"]["reviews"][-1]["revision_sha256"] = last["content_sha256"]
    with pytest.raises(ValueError, match="reproduced"):
        assemble_memo(*inputs(), MemoReviewContext.from_export(raw))
