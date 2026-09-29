"""Shared-pool lineage preserves measurement scopes and signed legacy history."""

import json
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest

from pe_value_os.diligence.allocation_kpis import AllocatedKpiBook, allocated_kpi_report
from pe_value_os.diligence.allocation_lineage_example import (
    CHILDREN,
    MERGED,
    PARENT,
    measure_allocated_lineage,
    merge_allocated_lineage,
    partition_allocated_lineage,
    seed_allocated_lineage,
    split_allocated_lineage,
)
from pe_value_os.diligence.cases import CaseRevision, RevisionDraft
from pe_value_os.diligence.interactions import population_shares
from pe_value_os.diligence.lineage import AllocatedLineageCasePayload, mapped_priority
from pe_value_os.diligence.memo_review import MemoReviewContext

from .test_initiative_lineage import advance


@pytest.fixture(scope="module")
def lifecycle():
    report = json.loads(Path("docs/portfolio/allocation-review.json").read_bytes())
    revisions = [CaseRevision.model_validate(r) for r in report["revisions"]]
    for builder in (
        seed_allocated_lineage,
        partition_allocated_lineage,
        split_allocated_lineage,
        measure_allocated_lineage,
        lambda p: measure_allocated_lineage(p, complete=True),
        merge_allocated_lineage,
    ):
        revisions.append(advance(revisions[-1], builder(revisions[-1])))
    return report, revisions


def test_shared_pool_lifecycle_preserves_scope_history_and_family_reconciliation(lifecycle):
    original, revisions = lifecycle
    assert [r.model_dump(mode="json") for r in revisions[:6]] == original["revisions"]
    seed, _partition, split, missing, corrected, merged = revisions[6:]
    assert isinstance(merged.draft.payload, AllocatedLineageCasePayload)
    assert population_shares(split.draft.payload.underwriting)[CHILDREN[0]] == Decimal(".24")
    assert population_shares(split.draft.payload.underwriting)[CHILDREN[1]] == Decimal(".36")
    assert population_shares(merged.draft.payload.underwriting)[MERGED] == Decimal(".6")
    for previous, current in pairwise(revisions[6:]):
        current.draft.payload.kpis.retain(previous.draft.payload.kpis)
        assert current.draft.payload.operating_plan.resources == previous.draft.payload.operating_plan.resources
        assert (
            current.draft.payload.source_basis.operating_sources.assignments
            == previous.draft.payload.source_basis.operating_sources.assignments
        )
    before = json.loads(seed.financial_result_json)["lineage_review"]["kpis"]
    assert PARENT + "-full-v1" in before["active_definition_ids"]
    assert "pricing-renewals-full-v1" not in before["active_definition_ids"]
    incomplete = json.loads(missing.financial_result_json)["lineage_review"]["kpis"]
    pricing = next(g for g in incomplete["current_population_observations"] if g["metric"] == "net_price_uplift")
    assert pricing["status"] == "missing_current_population" and pricing["value"] is None
    complete = json.loads(corrected.financial_result_json)["lineage_review"]["kpis"]
    pricing = next(g for g in complete["current_population_observations"] if g["metric"] == "net_price_uplift")
    assert Decimal(pricing["numerator"]) == 17000
    assert Decimal(pricing["denominator"]) == 500000
    assert Decimal(pricing["value"]) == Decimal(".034")  # Scoped counts, not a second .24/.36 weighting.
    assert pricing["value"] != ".035"  # Not an unweighted average of 4% and 3%.
    observations = {o["observation_id"]: o for o in complete["observations"]}
    assert observations["wave-a-march"]["numerator"] == "6000"
    assert observations["wave-a-march-correction"]["definition_id"] == CHILDREN[0] + "-v1"
    assert complete["financial_attribution"] is None
    for revision in revisions[6:]:
        financial = json.loads(revision.financial_result_json)
        assert financial["lineage_review"]["version"] == "initiative-lineage/2"
        for scenario, lineage in zip(financial["scenarios"], financial["lineage_review"]["scenarios"], strict=True):
            for period in ("day_100", "year_one"):
                for metric, value in scenario[period].items():
                    assert sum(Decimal(f["current"][period][metric]) for f in lineage["families"]) == Decimal(value)
    assert set(
        mapped_priority(merged.draft.payload, list(revisions[1].draft.payload.operating_plan.priority_order))
    ) == set(merged.draft.payload.operating_plan.priority_order)
    context = MemoReviewContext(
        classification="constructed_source_review_exercise", revisions=tuple(revisions), reviews=()
    )
    assert len(context.revisions) == 12
    assert CaseRevision.model_validate_json(merged.model_dump_json()) == merged


def test_targets_cannot_change_scope_and_shared_populations_cannot_double_count(lifecycle):
    _, revisions = lifecycle
    raw = revisions[10].draft.payload.kpis.model_dump(mode="json")
    raw["definitions"][-1]["allocation_scope"]["population_share"] = ".25"
    with pytest.raises(ValueError, match="scope correction"):
        AllocatedKpiBook.model_validate(raw)
    seed = revisions[6].draft.payload.kpis
    with pytest.raises(ValueError, match="exceed"):
        allocated_kpi_report(seed, {"pricing-renewals", PARENT})


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("scope", "exact pool"),
        ("history", "retain all prior"),
        ("predecessor", "predecessor initiative"),
        ("drop", "cannot discard"),
    ],
)
def test_reject_silent_scope_history_or_identity_changes(lifecycle, change, pattern):
    _, revisions = lifecycle
    parent = revisions[7]
    raw = split_allocated_lineage(parent).model_dump(mode="json")
    if change == "scope":
        raw["payload"]["kpis"]["definitions"][-1]["allocation_scope"]["population_share"] = ".35"
    elif change == "history":
        raw["payload"]["kpis"]["observations"][0]["numerator"] = "3"
    elif change == "predecessor":
        raw["payload"]["kpis"]["definitions"][-1]["predecessor_definition_ids"] = []
    else:
        # Same identity set: rejection must protect KPI history, not just the split mapping.
        raw = partition_allocated_lineage(revisions[6]).model_dump(mode="json")
        raw["payload"] = raw["payload"]["basis"]
        parent = revisions[6]
    with pytest.raises(ValueError, match=pattern):
        advance(parent, RevisionDraft.model_validate(raw))


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("allocation", "conserve each allocated"),
        ("cost_shares", "conserve explicit cost"),
        ("reference", "unrelated driver"),
        ("capacity", "create resource capacity"),
        ("effort", "conserve authored resource effort"),
    ],
)
def test_rehashed_identity_transition_cannot_change_economic_or_capacity_inputs(lifecycle, change, pattern):
    from pe_value_os.diligence.interactions import InteractionCase
    from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint

    _, revisions = lifecycle
    parent = revisions[7]
    raw = split_allocated_lineage(parent).model_dump(mode="json")
    source = raw["payload"]["basis"]
    if change == "allocation":
        pool = next(
            p for p in source["underwriting"]["interaction_policy"]["pools"] if CHILDREN[0] in p["initiative_ids"]
        )
        for share in pool["shares"]:
            if share["initiative_id"] == CHILDREN[0]:
                share["share"] = ".25"
            elif share["initiative_id"] == CHILDREN[1]:
                share["share"] = ".35"
        for definition in raw["payload"]["kpis"]["definitions"][-2:]:
            definition["allocation_scope"]["population_share"] = (
                ".25" if definition["initiative_id"] == CHILDREN[0] else ".35"
            )
    elif change == "cost_shares":
        cost = next(
            c
            for c in source["underwriting"]["interaction_policy"]["cost_allocations"]
            if any(s["initiative_id"] == CHILDREN[0] for s in c["shares"])
        )
        next(s for s in cost["shares"] if s["initiative_id"] == CHILDREN[0])["share"] = ".01"
    elif change == "reference":
        for scenario in source["underwriting"]["scenarios"]:
            keys = {d["monthly_eligible_revenue"] for d in scenario["drivers"] if d["kind"] == "pricing"}
            for assumption in scenario["assumptions"]:
                if assumption["assumption_id"] in keys:
                    assumption["value"] = str(Decimal(assumption["value"]) / 2)
    elif change == "capacity":
        source["operating_plan"]["resources"][0]["weekly_hours"][0] = "100"
    else:
        next(t for t in source["operating_plan"]["tasks"] if t["initiative_id"] == CHILDREN[0])["demands"][0][
            "hours_per_week"
        ] = ".1"
    case = InteractionCase.model_validate(source["underwriting"])
    source["operating_plan"]["underwriting_sha256"] = fingerprint(case)
    plan = OperatingPlan.model_validate(source["operating_plan"])
    source["operating_sources"]["records"].update(underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan))
    raw["payload"]["lineage_events"][-1]["revised_underwriting_sha256"] = fingerprint(case)
    with pytest.raises(ValueError, match=pattern):
        advance(parent, RevisionDraft.model_validate(raw))


def test_installed_demo_persistence_memo_and_api_preserve_authority(repo, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from scripts.build_allocation_example import examples

    from pe_value_os import security
    from pe_value_os.adapters.repositories import Conflict, NotFound
    from pe_value_os.api import app as api
    from pe_value_os.cli import main
    from pe_value_os.diligence import realization_render
    from pe_value_os.diligence.allocation_lineage_example import basis
    from pe_value_os.diligence.memo import assemble_memo
    from pe_value_os.diligence.memo_render import render_memo

    from .test_case_revisions import principal, request
    from .test_decision_memo import inputs

    monkeypatch.setattr(realization_render, "InMemoryRepository", lambda store: repo)
    args = ["allocation-demo", "--include-lineage", "--output", str(tmp_path / "allocation-lineage-review")]
    for flag, name in (
        ("underwriting", "underwriting"),
        ("operating-plan", "plan"),
        ("exercise", "realization"),
        ("sources", "sources"),
    ):
        args.extend(["--" + flag, f"data/constructed/progress/allocation-{name}.json"])
    assert main(args) == 0
    report = json.loads((tmp_path / "allocation-lineage-review.json").read_bytes())
    assert report["version"] == "constructed-realization/4"
    assert len(report["revisions"]) == 12
    assert report["actual_company_realized_value"] is None and report["human_review_count"] == 0
    assert all(c["preserved_accounting_and_claims"] for c in report["source_review"]["allocated_lineage_checkpoints"])
    assert report["allocation_comparability"]["financial_attribution"] is None
    context = MemoReviewContext.from_export(report)
    data, authored = list(inputs()), examples()
    data[0], data[4], data[5] = (
        authored["allocation-brief"],
        authored["allocation-underwriting"],
        authored["allocation-plan"],
    )
    memo = assemble_memo(*data, context)
    assert memo["memo_version"] == "executive-decision-packet/7"
    assert memo["source_review"]["current_revision_sha256"] == report["current_revision_sha256"]
    assert not memo["execution_authorized"] and memo["actual_realized_value"] is None
    assert "allocation-lineage-review.html" in render_memo(memo)
    html = (tmp_path / "allocation-lineage-review.html").read_text(encoding="utf-8")
    assert "Withheld: missing current population" in html and "3.40%" in html
    assert "Unavailable; needs a new scoped reading" in html
    parent = context.revisions[-1]
    with security.principal_scope(principal(report["company_id"])):
        assert repo.get_case_revision(parent.revision_id) == parent
        with pytest.raises(Conflict):
            repo.append_case_revision(parent.case_id, context.revisions[-2].revision_id, parent.draft)
        draft = RevisionDraft(
            stage="ownership_review",
            effective_on=parent.draft.effective_on,
            reason="Retain current measurement definitions pending a new scoped reading.",
            payload=AllocatedLineageCasePayload(
                schema_version=5,
                basis=basis(parent, parent.draft.payload.underwriting, parent.draft.payload.operating_plan),
                lineage_events=parent.draft.payload.lineage_events,
                kpis=parent.draft.payload.kpis,
            ),
        )
        audit = repo.list_audit(company_id=report["company_id"])
        with monkeypatch.context() as patch:

            def fail(*args, **kwargs):
                raise RuntimeError("audit unavailable")

            patch.setattr(repo, "append_audit", fail)
            with pytest.raises(RuntimeError, match="audit unavailable"):
                repo.append_case_revision(parent.case_id, parent.revision_id, draft)
        assert repo.list_audit(company_id=report["company_id"]) == audit
        assert repo.get_investment_case(parent.case_id).current_revision_id == parent.revision_id
    with security.principal_scope(principal("other")):
        with pytest.raises(NotFound):
            repo.get_case_revision(parent.revision_id)
    with security.principal_scope(security.system_principal(report["company_id"])):
        with pytest.raises(PermissionError):
            repo.review_case_revision(parent.revision_id, request(parent, mode="human"))
    monkeypatch.setenv(
        "PVC_DEV_TOKENS",
        json.dumps(
            {
                "writer": {
                    "sub": "service:test",
                    "pvc_companies": [report["company_id"]],
                    "pvc_principal_type": "service",
                    "scope": "pvc.read pvc.write",
                }
            }
        ),
    )
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    with TestClient(api.app) as client:
        response = client.post(
            f"/cases/{parent.case_id}/revisions",
            headers={"Authorization": "Bearer writer"},
            json={"expected_parent_revision_id": parent.revision_id, "draft": draft.model_dump(mode="json")},
        )
        assert response.status_code == 201, response.text
        saved = CaseRevision.model_validate(response.json())
        assert isinstance(saved.draft.payload, AllocatedLineageCasePayload)


def test_allocated_history_composes_with_exit_without_creating_proceeds(lifecycle):
    from pe_value_os.diligence.allocation_lineage_example import basis
    from pe_value_os.diligence.exit_demo import exit_draft
    from pe_value_os.diligence.exit_review import ExitAssumptions, ExitReviewPayload

    from .test_exit_review import inputs

    _, revisions = lifecycle
    parent = revisions[-1]
    facts, balances, valuation, assumptions = inputs()
    assumptions = ExitAssumptions.model_validate({**assumptions.model_dump(mode="json"), "case_id": parent.case_id})
    proposal = exit_draft(parent, facts, balances, valuation, assumptions)
    raw = proposal.payload.model_dump(mode="json")
    raw["source_basis"] = basis(
        parent, parent.draft.payload.underwriting, parent.draft.payload.operating_plan
    ).model_dump(mode="json")
    payload = AllocatedLineageCasePayload(
        schema_version=5,
        basis=ExitReviewPayload.model_validate(raw),
        lineage_events=parent.draft.payload.lineage_events,
        kpis=parent.draft.payload.kpis,
    )
    saved = advance(
        parent,
        RevisionDraft(stage="exit_review", effective_on=proposal.effective_on, reason=proposal.reason, payload=payload),
    )
    financial = json.loads(saved.financial_result_json)
    assert financial["lineage_review"]["version"] == "initiative-lineage/2"
    assert len(financial["exit_review"]["rows"]) == 12
    assert saved.draft.payload.kpis == parent.draft.payload.kpis
    assert all(s["valuation"] == [] for s in financial["scenarios"])
    assert financial["scenarios"] == json.loads(parent.financial_result_json)["scenarios"]


def test_published_allocated_history_reproduces():
    from scripts.check_allocation_review import check_allocation

    assert len(check_allocation(include_lineage=True)["checks"]) == 8
