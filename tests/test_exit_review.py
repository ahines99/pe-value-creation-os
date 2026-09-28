"""Exit marks cannot become operating attribution, cash proceeds or a rewritten baseline."""

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os import security
from pe_value_os.diligence.balances import BalanceBundle
from pe_value_os.diligence.cases import CaseRevision, RevisionDraft, digest
from pe_value_os.diligence.exit_demo import build_exit_demo, exit_draft, render_exit
from pe_value_os.diligence.exit_review import ExitAssumptions, ExitReviewPayload, evaluate_exit
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.operating_sources import source_forecast
from pe_value_os.diligence.scheduling import fingerprint
from pe_value_os.diligence.source_revisions import financial_snapshot
from pe_value_os.diligence.valuation import ValuationSpec

from .test_case_revisions import principal, request
from .test_realization import claim, ready
from .test_source_revisions import append, challenge

ROOT = Path(__file__).resolve().parents[1]
OPERATING = ROOT / "data/constructed/progress"
PUBLIC = ROOT / "data/public/progress"


def inputs():
    return (
        FactBundle.model_validate_json((PUBLIC / "financial-facts.json").read_bytes()),
        BalanceBundle.model_validate_json((PUBLIC / "balance-facts.json").read_bytes()),
        ValuationSpec.model_validate_json((OPERATING / "historical-valuation.json").read_bytes()),
        ExitAssumptions.model_validate_json((OPERATING / "exit-assumptions.json").read_bytes()),
    )


def example():
    raw = json.loads((ROOT / "docs/portfolio/source-review.json").read_bytes())
    parent = CaseRevision.model_validate(raw["revisions"][-1])
    draft = exit_draft(parent, *inputs())
    payload = draft.payload
    assert isinstance(payload, ExitReviewPayload)
    source = payload.source_basis
    financial = financial_snapshot(
        source, parent, source_forecast(source.operating_sources, source.underwriting, source.operating_plan)
    )
    return parent, draft, financial


def test_exit_decomposition_and_equity_bridge_reconcile():
    _, draft, financial = example()
    result = evaluate_exit(draft.payload, financial)
    assert len(result["rows"]) == 12
    assert result["entry_anchor"]["enterprise_value"] == Decimal("2433616000")
    assert result["entry_anchor"]["cash_added"] == Decimal("47403500")
    for row in result["rows"]:
        assert not row["blocked_by"]
        assert sum(row["decomposition"].values()) == row["ev_change"]
        assert row["equity_change"] == row["ev_change"]
        claims = row["claims"]
        assert row["equity_sensitivity"] == row["enterprise_value_sensitivity"] + claims["cash_added"] + claims[
            "nonoperating_assets_added"
        ] - sum(
            claims[k]
            for k in (
                "debt_principal_deducted",
                "lease_claim_deducted",
                "other_claims_deducted",
                "transaction_costs_deducted",
            )
        )
    adverse = next(r for r in result["rows"] if r["earnings_factor"] == Decimal("0.9") and r["multiple"] == 6)
    assert adverse["decomposition"] == {
        "earnings_change_at_entry_multiple": Decimal("-243361600"),
        "multiple_change_on_starting_earnings": Decimal("-608404000"),
        "earnings_multiple_interaction": Decimal("60840400"),
        "rounding_residual": Decimal(0),
    }
    assert adverse["ev_change"] == Decimal("-790925200")
    assert any(r["equity_sensitivity"] < 0 for r in result["rows"])
    for key in (
        "transaction_proceeds",
        "shareholder_distributions",
        "actual_exit_date",
        "current_company_valuation",
        "investment_return",
    ):
        assert result[key] is None


def test_operating_cash_and_kpi_capacity_never_become_exit_earnings():
    _, draft, financial = example()
    result = evaluate_exit(draft.payload, financial)
    before = deepcopy(financial)
    altered = deepcopy(financial)
    for scenario in altered["scenarios"]:
        scenario["monthly"][-1]["pre_tax_cash_proxy"] = Decimal("999999999")
        scenario["monthly"][-1]["capacity_hours"] = Decimal("99999")
    after = evaluate_exit(draft.payload, altered)
    assert after["rows"] == result["rows"]
    assert financial == before
    for review in result["operating_scope_review"]:
        assert review["maintainable_annual_uplift"] is None
        assert review["included_in_company_exit_earnings"] is False
        assert Decimal(review["terminal_month"]["cost_removed"]) == 0
        assert Decimal(review["terminal_month"]["incremental_ebitda"]) < 0
        if review["scenario_id"] == "base":
            assert Decimal(review["terminal_month"]["incremental_ebitda"]) == -8500


def test_multiple_change_preserves_operating_inputs_and_earnings():
    _, draft, financial = example()
    old = draft.payload
    raw = old.model_dump(mode="json")
    raw["exit_assumptions"]["terminal_multiples"] = ["7", "9"]
    new = ExitReviewPayload.model_validate(raw)
    before, after = evaluate_exit(old, financial), evaluate_exit(new, financial)
    assert before["assumptions_sha256"] != after["assumptions_sha256"]
    assert before["payload_sha256"] != after["payload_sha256"]
    assert before["operating_scope_review"] == after["operating_scope_review"]
    assert old.source_basis == new.source_basis
    assert old.public_facts == new.public_facts
    assert {r["terminal_ebitda_sensitivity"] for r in before["rows"]} == {
        r["terminal_ebitda_sensitivity"] for r in after["rows"]
    }


@pytest.mark.parametrize("factor", ["0", "-0.1"])
def test_nonpositive_earnings_withhold_multiple_values(factor):
    _, draft, financial = example()
    raw = draft.payload.model_dump(mode="json")
    raw["exit_assumptions"]["terminal_earnings_factors"] = [factor]
    result = evaluate_exit(ExitReviewPayload.model_validate(raw), financial)
    assert all(
        r["enterprise_value_sensitivity"] is None
        and r["equity_sensitivity"] is None
        and r["decomposition"] is None
        and r["blocked_by"]
        for r in result["rows"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "private",
        "fact_change",
        "reference",
        "currency",
        "exit_date",
        "claim",
        "duplicate_multiple",
        "zero_multiple",
        "nonfinite",
        "proceeds",
    ],
)
def test_mismatched_or_unclassified_exit_inputs_rejected(mutation):
    _, draft, _ = example()
    raw = draft.payload.model_dump(mode="json")
    if mutation == "private":
        raw["public_facts"]["documents"][0]["classification"] = "licensed_private"
    elif mutation == "fact_change":
        raw["public_facts"]["facts"][0]["reported_amount"] = "1"
    elif mutation == "reference":
        raw["exit_assumptions"]["public_entity_id"] = "wrong-company"
    elif mutation == "currency":
        raw["historical_valuation"]["currency"] = "EUR"
    elif mutation == "exit_date":
        raw["exit_assumptions"]["exit_on"] = "2029-01-01"
    elif mutation == "claim":
        raw["exit_assumptions"]["historical_claim_scenario"] = "unknown"
    elif mutation == "duplicate_multiple":
        raw["exit_assumptions"]["terminal_multiples"] = ["8", "8"]
    elif mutation == "zero_multiple":
        raw["exit_assumptions"]["terminal_multiples"] = ["0"]
    elif mutation == "nonfinite":
        raw["exit_assumptions"]["terminal_earnings_factors"] = ["NaN"]
    else:
        raw["exit_assumptions"]["actual_proceeds"] = "1000"
    with pytest.raises(ValueError):
        ExitReviewPayload.model_validate(raw)


def test_exit_stage_and_effective_date_require_explicit_contract():
    _, draft, _ = example()
    raw = draft.model_dump(mode="json")
    raw["stage"] = "ownership_review"
    with pytest.raises(ValueError, match="exit-review stage"):
        RevisionDraft.model_validate(raw)
    raw = draft.model_dump(mode="json")
    raw["effective_on"] = "2027-03-01"
    with pytest.raises(ValueError, match="effective date"):
        RevisionDraft.model_validate(raw)


def test_missing_earnings_component_blocks_every_exit_value():
    _, draft, financial = example()
    raw = draft.payload.model_dump(mode="json")
    raw["public_facts"]["facts"] = [
        f
        for f in raw["public_facts"]["facts"]
        if not (f["metric"] == "net_income" and f["period"]["end"] == "2025-11-30")
    ]
    facts = FactBundle.model_validate(raw["public_facts"])
    raw["historical_valuation"]["financial_sha256"] = fingerprint(facts)
    valuation = ValuationSpec.model_validate(raw["historical_valuation"])
    raw["exit_assumptions"].update(
        financial_sha256=fingerprint(facts), historical_valuation_sha256=fingerprint(valuation)
    )
    result = evaluate_exit(ExitReviewPayload.model_validate(raw), financial)
    assert all(
        r["enterprise_value_sensitivity"] is None and r["equity_sensitivity"] is None and r["blocked_by"]
        for r in result["rows"]
    )


def test_exit_persistence_preserves_frozen_sources_and_claims(repo):
    with security.principal_scope(principal()):
        case, close, _, baseline, req = ready(repo)
        observation = repo.record_case_observation(case.case_id, req)
        repo.record_case_attribution(case.case_id, claim(observation))
        parent = append(repo, case, close)
        corrected = append(repo, case, parent, correction=True)
        marker = corrected.draft.model_dump(mode="json")
        marker.update(stage="exit_review", effective_on="2028-09-30")
        with pytest.raises(ValueError, match="explicit exit payload"):
            repo.append_case_revision(case.case_id, corrected.revision_id, RevisionDraft.model_validate(marker))
        before = repo.case_realization(case.case_id, baseline.baseline_id)
        saved = repo.append_case_revision(case.case_id, corrected.revision_id, exit_draft(corrected, *inputs()))
        receipt = repo.review_case_revision(saved.revision_id, request(saved))
        after = repo.case_realization(case.case_id, baseline.baseline_id)
        for key in ("baseline", "observations", "attributions", "aggregate_recorded_periods"):
            assert before[key] == after[key]
        assert repo.get_case_revision(corrected.revision_id) == corrected
        assert saved.draft.stage == "exit_review" and saved.draft.payload.schema_version == 3
        assert repo.get_case_revision(saved.revision_id) == saved
        assert json.loads(saved.financial_result_json)["exit_review"]["transaction_proceeds"] is None
        assert receipt.mode == "simulation"
        assert repo.list_kpi_definitions("exercise") == repo.list_runs("exercise") == []
        # A new multiple creates a new signed snapshot, not a mutation of the old one.
        new_draft = exit_draft(saved, *inputs()).model_dump(mode="json")
        new_draft["payload"]["exit_assumptions"]["terminal_multiples"] = ["5", "9"]
        revised = repo.append_case_revision(case.case_id, saved.revision_id, RevisionDraft.model_validate(new_draft))
        old_result, new_result = json.loads(saved.financial_result_json), json.loads(revised.financial_result_json)
        assert old_result["scenarios"] == new_result["scenarios"]
        assert old_result["exit_review"]["rows"] != new_result["exit_review"]["rows"]
        assert repo.get_case_revision(saved.revision_id) == saved
        assert receipt.revision_sha256 != revised.content_sha256
        fallback = challenge(revised).model_dump(mode="json")
        fallback["effective_on"] = "2028-09-30"
        with pytest.raises(ValueError, match="discard its valuation basis"):
            repo.append_case_revision(case.case_id, revised.revision_id, RevisionDraft.model_validate(fallback))
    with security.principal_scope(principal("another-company")):
        from pe_value_os.adapters.repositories import NotFound

        with pytest.raises(NotFound):
            repo.get_case_revision(saved.revision_id)
    for kind in ("service", "model"):
        with security.principal_scope(principal(kind=kind)):
            with pytest.raises(security.ScopeError):
                repo.review_case_revision(revised.revision_id, request(revised, mode="human"))
    with security.principal_scope(principal()):
        count = len(repo.list_case_revisions(case.case_id))
        assert repo.delete_company_data("exercise")["case_revisions"] == count
        with pytest.raises(NotFound):
            repo.get_case_revision(saved.revision_id)


def test_exit_api_accepts_version_three_and_blocks_earlier_stage_bypass(repo, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from pe_value_os.api import app as api

    with security.principal_scope(principal()):
        case, close, _, _, _ = ready(repo)
        source = challenge(close).payload
        facts, balances, valuation, spec = inputs()
        forged = RevisionDraft(
            stage="exit_review",
            effective_on=spec.exit_on,
            reason="Bypass ownership history",
            payload=ExitReviewPayload(
                schema_version=3,
                source_basis=source,
                public_facts=facts,
                public_balances=balances,
                historical_valuation=valuation,
                exit_assumptions=spec,
            ),
        )
        with pytest.raises(ValueError, match="saved source-backed"):
            repo.append_case_revision(case.case_id, close.revision_id, forged)
        parent = append(repo, case, close)
        corrected = append(repo, case, parent, correction=True)
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
    body = {
        "expected_parent_revision_id": corrected.revision_id,
        "draft": exit_draft(corrected, *inputs()).model_dump(mode="json"),
    }
    response = client.post(f"/cases/{case.case_id}/revisions", json=body, headers={"Authorization": "Bearer writer"})
    assert response.status_code == 201, response.text
    saved = CaseRevision.model_validate(response.json())
    assert saved.draft.payload.schema_version == 3 and saved.draft.stage == "exit_review"
    reviewed = client.post(
        f"/case-revisions/{saved.revision_id}/reviews",
        headers={"Authorization": "Bearer writer"},
        json=request(saved).model_dump(mode="json"),
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["mode"] == "simulation" and reviewed.json()["actor_type"] == "service"


def test_saved_source_and_legacy_revisions_keep_their_hashes():
    for name in ("case-history", "source-review"):
        raw = json.loads((ROOT / f"docs/portfolio/{name}.json").read_bytes())
        for revision in raw["revisions"]:
            assert CaseRevision.model_validate(revision).model_dump(mode="json") == revision


def test_legacy_exit_stage_marker_remains_readable_without_invented_values():
    raw = json.loads((ROOT / "docs/portfolio/case-history.json").read_bytes())["revisions"][-1]
    raw["draft"]["stage"] = "exit_review"
    raw.pop("content_sha256")
    raw["content_sha256"] = digest(json.dumps(raw, sort_keys=True))
    loaded = CaseRevision.model_validate(raw)
    assert loaded.model_dump(mode="json") == raw
    assert loaded.draft.payload.schema_version == 1
    assert "exit_review" not in json.loads(loaded.financial_result_json)


def test_exit_replay_and_renderer(tmp_path):
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
    output = tmp_path / "exit"
    build_exit_demo(*paths, *rest, output)
    report = json.loads(output.with_suffix(".json").read_bytes())
    assert len(report["revisions"]) == 6
    assert report["actual_company_realized_value"] is None and report["human_review_count"] == 0
    latest = CaseRevision.model_validate(report["revisions"][-1])
    assert latest.draft.payload.exit_assumptions.exit_on == date(2028, 9, 30)
    assert report["source_review"]["exit_checkpoint"]["preserved_accounting_and_claims"] is True
    raw = json.loads(latest.financial_result_json)
    raw["exit_review"]["assumptions"]["earnings_rationale"] = "<script>alert(1)</script>"
    report["revisions"][-1]["financial_result_json"] = json.dumps(raw)
    assert "<script>alert" not in render_exit(report, "exit.json")
    with pytest.raises(ValueError, match="overwrite"):
        build_exit_demo(*paths, *rest, rest[-1])
