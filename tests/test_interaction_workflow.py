"""Selected operating work and saved financial policies must describe the same decision."""

import json
from copy import deepcopy
from datetime import date

import pytest
from scripts.build_operating_plan_example import example as original_plan

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.cases import CasePayload, CaseRevision, RevisionDraft
from pe_value_os.diligence.close_baseline import CloseBaselineRequest
from pe_value_os.diligence.interactions import InteractionCase
from pe_value_os.diligence.scheduling import OperatingPlan, evaluate_plan, fingerprint, schedule
from pe_value_os.diligence.underwriting_models import parse_underwriting

from .test_benefit_interactions import paired
from .test_case_revisions import principal, request, setup
from .test_realization import claim, observation_request


def plan_for(case, parent, alternative):
    raw = original_plan().model_dump(mode="json")
    raw["underwriting_sha256"] = fingerprint(case)
    source = [t for t in raw["tasks"] if t["initiative_id"] == parent]
    names = {t["task_id"] for t in source}
    for task in source:
        copy = deepcopy(task)
        copy.update(task_id=task["task_id"] + "-alternative", initiative_id=alternative, workstream_id=alternative)
        copy["prerequisites"] = [p + "-alternative" if p in names else p for p in task["prerequisites"]]
        raw["tasks"].append(copy)
        raw["priority_order"].append(copy["task_id"])
    gate = next(g for g in raw["benefit_gates"] if g["initiative_id"] == parent)
    raw["benefit_gates"].append({"initiative_id": alternative, "task_id": gate["task_id"] + "-alternative"})
    return OperatingPlan.model_validate(raw)


def revision(case, plan=None, *, stage="underwriting"):
    return RevisionDraft(
        stage=stage,
        effective_on=date(2026, 10, 1),
        reason="Constructed pool allocation review",
        payload=CasePayload(
            underwriting=case,
            operating_plan=plan,
            decision_question="Which explicitly scoped intervention should be modeled?",
            counterevidence=("Constructed assumptions only",),
            unresolved_items=("No company sponsor or actual intervention",),
        ),
    )


def test_allocation_reports_cli_selection_and_safe_rendering(tmp_path):
    from pe_value_os.cli import main
    from pe_value_os.diligence.scheduling_render import build_operating_report
    from pe_value_os.diligence.underwriting_render import build_underwriting_report

    raw, parent, alternative, _ = paired(mode="exclusive")
    raw["interaction_policy"]["selection_rationale"] = "<script>policy</script>"
    case = InteractionCase.model_validate(raw)
    source = tmp_path / "case.json"
    source.write_text(case.model_dump_json(), encoding="utf-8")
    output = tmp_path / "report"
    assert main(["underwriting", "--input", str(source), "--output", str(output)]) == 0
    saved = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert saved["selection_basis"]["mode"] == "recorded_policy"
    assert alternative not in saved["selected_initiatives"]
    html = output.with_suffix(".html").read_text(encoding="utf-8")
    assert "One economic pool, explicit choices" in html
    assert "&lt;script&gt;policy&lt;/script&gt;" in html and "<script>policy" not in html
    assert "combined driver before aggregation" not in html
    selected = tmp_path / "selected"
    assert main(["underwriting", "--input", str(source), "--output", str(selected), "--select", alternative]) == 0
    changed = json.loads(selected.with_suffix(".json").read_text(encoding="utf-8"))
    assert changed["selection_basis"]["mode"] == "hypothetical_override"
    assert changed["selected_initiatives"] == [alternative]
    assert changed["interaction_policy"] == saved["interaction_policy"]
    assert "hypothetical override" in selected.with_suffix(".html").read_text(encoding="utf-8")
    assert (
        main(
            [
                "underwriting",
                "--input",
                str(source),
                "--output",
                str(tmp_path / "bad"),
                "--select",
                parent,
                "--select",
                alternative,
            ]
        )
        == 2
    )
    assert not (tmp_path / "bad.json").exists()
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_underwriting_report(source, output, frozenset({parent}), selected=frozenset({alternative}))
    excluded = tmp_path / "excluded"
    build_underwriting_report(source, excluded, frozenset({parent}))
    assert alternative not in json.loads(excluded.with_suffix(".json").read_text())["selected_initiatives"]
    plan = plan_for(case, parent, alternative)
    plan_source = tmp_path / "plan.json"
    plan_source.write_text(plan.model_dump_json(), encoding="utf-8")
    page = build_operating_report(plan_source, source, tmp_path / "operating")
    plan_html = page.read_text(encoding="utf-8")
    assert "Work excluded from this selection" in plan_html
    assert "One economic pool, explicit choices" in plan_html
    assert "Excluded work consumes no capacity" in plan_html


def test_unselected_alternative_uses_no_capacity_and_empty_selection_starts_no_work():
    raw, parent, alternative, _ = paired(mode="exclusive")
    case = InteractionCase.model_validate(raw)
    plan = plan_for(case, parent, alternative)
    result = evaluate_plan(plan, case)
    assert result["schedule_version"] == "capacity-schedule/2"
    assert len(result["excluded_tasks"]) == 2
    assert all(t["initiative_id"] != alternative for t in result["tasks"])
    assert result["capacity"] == schedule(original_plan())["capacity"]
    switched = evaluate_plan(
        plan, case, selected=frozenset(case.interaction_policy.selected_initiatives) - {parent} | {alternative}
    )
    assert all(t["initiative_id"] != parent for t in switched["tasks"])
    assert alternative in switched["scheduled_financials"]["selected_initiatives"]
    empty = evaluate_plan(plan, case, selected=frozenset())
    assert empty["tasks"] == [] and len(empty["excluded_tasks"]) == len(plan.tasks)
    assert all(w["used_hours"] == 0 for r in empty["capacity"] for w in r["weeks"])
    assert all(s["total"]["incremental_ebitda"] == 0 for s in empty["scheduled_financials"]["scenarios"])


def test_selection_cannot_silently_authorize_an_excluded_prerequisite():
    raw, parent, alternative, _ = paired(mode="exclusive")
    case = InteractionCase.model_validate(raw)
    raw_plan = plan_for(case, parent, alternative).model_dump(mode="json")
    gate = next(g["task_id"] for g in raw_plan["benefit_gates"] if g["initiative_id"] == alternative)
    next(t for t in raw_plan["tasks"] if t["task_id"] == "pricing-review")["prerequisites"].append(gate)
    with pytest.raises(ValueError, match="unselected initiative"):
        evaluate_plan(OperatingPlan.model_validate(raw_plan), case)


def test_blocked_selected_work_keeps_costs_and_does_not_reallocate_population():
    raw, parent, alternative, _ = paired(setup="100")
    for scenario in raw["scenarios"]:
        scenario["costs"] = [
            {
                "cost_id": "selected-commitment",
                "initiative_ids": [alternative],
                "kind": "implementation",
                "amount": "setup",
                "recognized_on": "2026-10-02",
                "paid_on": "2026-10-02",
                "retained_if_excluded": False,
            }
        ]
    case = InteractionCase.model_validate(raw)
    plan = plan_for(case, parent, alternative)
    # Isolate the explicit gate delay from competing-resource constraints in
    # this test; these larger budgets are not proposed company capacity.
    ample = plan.model_dump(mode="json")
    ample["maximum_active_workstreams"] = 4
    for resource in ample["resources"]:
        resource["weekly_hours"] = ["100"] * 15
    plan = OperatingPlan.model_validate(ample)
    before = evaluate_plan(plan, case)
    assert all(t["status"] == "scheduled" for t in before["tasks"] if t["initiative_id"] == alternative)
    raw_plan = plan.model_dump(mode="json")
    for task in raw_plan["tasks"]:
        if task["initiative_id"] == alternative:
            task["earliest_start"] = "2027-02-01"
    after = evaluate_plan(OperatingPlan.model_validate(raw_plan), case)
    for old, new in zip(
        before["scheduled_financials"]["scenarios"], after["scheduled_financials"]["scenarios"], strict=True
    ):
        assert old["year_one"]["implementation_expense"] == new["year_one"]["implementation_expense"] == -100
        assert new["year_one"]["gross_price_benefit"] < old["year_one"]["gross_price_benefit"]
        assert new["interaction"]["pools"][0]["blocked_members"] == [alternative]
        assert (
            new["interaction"]["pools"][0]["members"][0]["population_share"]
            == old["interaction"]["pools"][0]["members"][0]["population_share"]
        )


def test_saved_allocation_selection_keeps_close_accounting_claims_and_authority(repo, monkeypatch):
    raw, parent, alternative, _ = paired(mode="exclusive")
    model = InteractionCase.model_validate(raw)
    with security.principal_scope(principal()):
        case = setup(repo)
        original = repo.append_case_revision(case.case_id, None, revision(model))
        close = repo.append_case_revision(
            case.case_id,
            original.revision_id,
            revision(model, plan_for(model, parent, alternative), stage="close_validation"),
        )
        receipt = repo.review_case_revision(close.revision_id, request(close))
        frozen = repo.designate_close_baseline(
            case.case_id,
            CloseBaselineRequest(
                revision_id=close.revision_id,
                revision_sha256=close.content_sha256,
                review_id=receipt.review_id,
                mode="simulation",
                scenario_id="base",
                rationale="Freeze the explicit selected alternative",
            ),
        )
        observed = repo.record_case_observation(case.case_id, observation_request(case, frozen, close))
        attributed = repo.record_case_attribution(case.case_id, claim(observed))
        before = repo.case_realization(case.case_id, frozen.baseline_id)
        changed = deepcopy(raw)
        changed["interaction_policy"]["selected_initiatives"] = [
            alternative if i == parent else i for i in changed["interaction_policy"]["selected_initiatives"]
        ]
        changed["interaction_policy"]["selection_rationale"] = (
            "Explicit later alternative; prior claim is not transferred"
        )
        revised = InteractionCase.model_validate(changed)
        draft = revision(revised, plan_for(revised, parent, alternative), stage="ownership_review")
        current = repo.append_case_revision(case.case_id, close.revision_id, draft)
        assert repo.get_case_revision(current.revision_id) == current
        assert isinstance(current.draft.payload.underwriting, InteractionCase)
        assert json.loads(current.schedule_result_json)["selected_initiatives"] == sorted(
            revised.interaction_policy.selected_initiatives
        )
        after = repo.case_realization(case.case_id, frozen.baseline_id)
        for key in ("baseline", "observations", "attributions"):
            assert before[key] == after[key]
        assert repo.list_case_attributions(case.case_id) == [attributed]
        assert after["version"] == "constructed-realization/3"
        assert parent in after["allocation_comparability"]["frozen_selected_initiatives"]
        assert alternative in after["allocation_comparability"]["current_selected_initiatives"]
        assert after["allocation_comparability"]["financial_attribution"] is None
        with pytest.raises(Conflict):
            repo.append_case_revision(case.case_id, close.revision_id, draft)
        audit = repo.list_audit(company_id="exercise")

        def fail(*args, **kwargs):
            raise RuntimeError("injected allocation audit failure")

        with monkeypatch.context() as patch:
            patch.setattr(repo, "append_audit", fail)
            with pytest.raises(RuntimeError, match="audit failure"):
                repo.append_case_revision(case.case_id, current.revision_id, draft)
        assert repo.list_audit(company_id="exercise") == audit
        assert repo.get_investment_case(case.case_id).current_revision_id == current.revision_id
    for kind in ("model", "service"):
        with security.principal_scope(principal(kind=kind)):
            with pytest.raises(security.ScopeError):
                repo.review_case_revision(current.revision_id, request(current, mode="human"))
    with security.principal_scope(principal("outsider")):
        with pytest.raises(NotFound):
            repo.get_case_revision(current.revision_id)
    with security.principal_scope(principal()):
        assert repo.delete_company_data("exercise")["case_revisions"] == 3


def test_saved_legacy_versions_and_missing_default_version_remain_readable():
    for name in ("case-history", "source-review", "exit-review", "lineage-review"):
        for raw in json.loads(open(f"docs/portfolio/{name}.json", encoding="utf-8").read())["revisions"]:
            assert CaseRevision.model_validate(raw).model_dump(mode="json") == raw
    legacy = json.loads(open("data/constructed/progress/underwriting.json", encoding="utf-8").read())
    legacy.pop("schema_version")
    assert parse_underwriting(legacy).schema_version == 1
