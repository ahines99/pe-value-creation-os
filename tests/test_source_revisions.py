"""Source challenges retain exact-version authority and frozen accounting comparisons."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from scripts.build_operating_sources_example import example as source_example

from pe_value_os import security
from pe_value_os.adapters.repositories import Conflict, NotFound
from pe_value_os.diligence.cases import CaseRevision, RevisionDraft
from pe_value_os.diligence.close_baseline import CloseBaselineRequest
from pe_value_os.diligence.scheduling import fingerprint
from pe_value_os.diligence.source_review_demo import build_source_review_demo, render_source_review, source_draft
from pe_value_os.diligence.source_revisions import SourceCasePayload

from .test_case_revisions import draft, principal, request, setup
from .test_realization import claim, observation_request, ready


def challenge(parent, *, correction=False):
    return source_draft(parent, source_example(), date(2027, 3, 4), correction=correction)


def append(repo, case, parent, *, correction=False):
    return repo.append_case_revision(case.case_id, parent.revision_id, challenge(parent, correction=correction))


@pytest.mark.parametrize("name", ["case-history", "realization", "execution"])
def test_published_v1_signed_revisions_roundtrip_without_hash_drift(name):
    report = json.loads(Path(f"docs/portfolio/{name}.json").read_text(encoding="utf-8"))
    for raw in report["revisions"]:
        revision = CaseRevision.model_validate(raw)
        assert revision.model_dump(mode="json") == raw
        assert revision.draft.payload.schema_version == 1
    raw = draft().model_dump(mode="json")
    del raw["payload"]["schema_version"]
    assert RevisionDraft.model_validate(raw).payload.schema_version == 1


def test_source_revisions_preserve_baseline_sources_claims_and_review_receipts(repo, monkeypatch):
    with security.principal_scope(principal()):
        case, close, receipt, baseline, req = ready(repo)
        observation = repo.record_case_observation(case.case_id, req)
        attribution = repo.record_case_attribution(case.case_id, claim(observation))
        before = repo.case_realization(case.case_id, baseline.baseline_id)
        source = append(repo, case, close)
        rejected = repo.review_case_revision(source.revision_id, request(source, decision="request_changes"))
        corrected = append(repo, case, source, correction=True)
        accepted = repo.review_case_revision(corrected.revision_id, request(corrected))
        after = repo.case_realization(case.case_id, baseline.baseline_id)
        assert before["baseline"] == after["baseline"]
        for key in (
            "original_forecast",
            "close_forecast",
            "measured_difference",
            "attributed_difference",
            "unassigned_residual",
        ):
            assert before["aggregate_recorded_periods"][key] == after["aggregate_recorded_periods"][key]
        assert before["observations"] == after["observations"]
        assert before["attributions"] == after["attributions"]
        for old, new in zip(before["periods"], after["periods"], strict=True):
            for key in (
                "original_forecast",
                "close_forecast",
                "measured_difference",
                "attributed_difference",
                "unassigned_residual",
            ):
                assert old[key] == new[key]
        assert before["periods"][5]["current_forecast"] != after["periods"][5]["current_forecast"]
        assert repo.get_case_revision(close.revision_id) == close
        assert repo.list_case_reviews(case.case_id) == [receipt, rejected, accepted]
        assert repo.list_case_observations(case.case_id) == [observation]
        assert repo.list_case_attributions(case.case_id) == [attribution]
        financial = json.loads(source.financial_result_json)
        revised = json.loads(corrected.financial_result_json)
        assert financial["scenarios"][1]["year_one"]["incremental_ebitda"] == "-18314.50"
        assert Decimal(financial["scenarios"][1]["year_one"]["incremental_ebitda"]) - Decimal(
            revised["scenarios"][1]["year_one"]["incremental_ebitda"]
        ) == Decimal("135000")
        assert revised["input_sha256"] == fingerprint(corrected.draft.payload)
        lesson = revised["learning_context"][0]
        assert lesson["prior_revision_sha256"] == source.content_sha256
        assert lesson["prior_assumptions"][0]["assumption_id"] == "cost-action"
        for row in lesson["source_comparison"]:
            assert row["prior_record"]["release_on"] == "2027-02-15"
            assert row["current_record"]["release_on"] is None
            assert row["prior_record_sha256"] != row["current_record_sha256"]
        assert after["actual_company_realized_value"] is None
        assert repo.list_kpi_definitions("exercise") == repo.list_runs("exercise") == []

        def fail(*args, **kwargs):
            raise AssertionError("reading saved financial results must not recompute them")

        monkeypatch.setattr("pe_value_os.diligence.cases.source_forecast", fail)
        assert repo.get_case_revision(corrected.revision_id) == corrected
        assert repo.case_realization(case.case_id, baseline.baseline_id) == after


@pytest.mark.parametrize(
    "mutation,pattern",
    [
        ("record_hash", "exact record"),
        ("record_value", "exact record"),
        ("foreign_assumption", "prior initiative"),
        ("source_kind", "mechanism"),
        ("parent_hash", "exact stored parent"),
        ("unknown_initiative", "unknown prior initiative"),
        ("duplicate_lesson", "lesson IDs"),
        ("duplicate_ref", "source references"),
        ("private", "private"),
    ],
)
def test_source_and_lesson_binding_rejects_tampering(repo, mutation, pattern):
    with security.principal_scope(principal()):
        case = setup(repo)
        first = repo.append_case_revision(case.case_id, None, draft(scheduled=True))
        raw = challenge(first).model_dump(mode="json")
        payload = raw["payload"]
        lesson = payload["lessons"][0]
        if mutation == "record_hash":
            lesson["source_records"][0]["record_sha256"] = "a" * 64
        elif mutation == "record_value":
            payload["operating_sources"]["service_months"][0]["qa_hours"] = "81"
        elif mutation == "foreign_assumption":
            lesson["assumption_ids"] = ["capture"]
        elif mutation == "source_kind":
            lesson["source_records"] = payload["lessons"][1]["source_records"]
        elif mutation == "parent_hash":
            payload["challenged_revision_sha256"] = "a" * 64
        elif mutation == "unknown_initiative":
            lesson["initiative_id"] = "not-present"
        elif mutation == "duplicate_lesson":
            payload["lessons"].append(lesson)
        elif mutation == "duplicate_ref":
            lesson["source_records"].append(lesson["source_records"][0])
        else:
            payload["underwriting"]["evidence"][1]["classification"] = "licensed_private"
        with pytest.raises(ValueError, match=pattern):
            repo.append_case_revision(case.case_id, first.revision_id, RevisionDraft.model_validate(raw))
        assert repo.get_investment_case(case.case_id).version == 1


def test_source_v2_keeps_stale_version_authority_scope_and_rollback_controls(repo, monkeypatch):
    with security.principal_scope(principal()):
        case = setup(repo)
        initial = repo.append_case_revision(case.case_id, None, draft(scheduled=True))
        source = append(repo, case, initial)
        with pytest.raises(Conflict):
            append(repo, case, initial)
        drop = draft(scheduled=True).model_dump(mode="json")
        drop["effective_on"] = "2027-03-04"
        with pytest.raises(ValueError, match="silently discard"):
            repo.append_case_revision(case.case_id, source.revision_id, RevisionDraft.model_validate(drop))
        with pytest.raises(ValueError, match="exact stored parent"):
            repo.append_case_revision(case.case_id, source.revision_id, challenge(initial))
        before = repo.list_audit(company_id="exercise")

        def fail(*args, **kwargs):
            raise RuntimeError("injected audit failure")

        with monkeypatch.context() as context:
            context.setattr(repo, "append_audit", fail)
            with pytest.raises(RuntimeError, match="audit failure"):
                append(repo, case, source, correction=True)
        assert repo.list_audit(company_id="exercise") == before
        assert repo.get_investment_case(case.case_id).current_revision_id == source.revision_id
    for kind in ("service", "model"):
        with security.principal_scope(principal(kind=kind)):
            with pytest.raises(security.ScopeError):
                repo.review_case_revision(source.revision_id, request(source, mode="human"))
    with security.principal_scope(principal("outsider")):
        with pytest.raises(NotFound):
            repo.get_case_revision(source.revision_id)
    with security.principal_scope(principal()):
        assert repo.delete_company_data("exercise")["case_revisions"] == 2


def test_source_cannot_be_original_and_can_be_explicitly_frozen_after_review(repo):
    with security.principal_scope(principal()):
        case = setup(repo)
        original = repo.append_case_revision(case.case_id, None, draft(scheduled=True))
        raw = challenge(original).model_dump(mode="json")
        raw["stage"] = "close_validation"
        source = repo.append_case_revision(case.case_id, original.revision_id, RevisionDraft.model_validate(raw))
        receipt = repo.review_case_revision(source.revision_id, request(source))
        baseline = repo.designate_close_baseline(
            case.case_id,
            CloseBaselineRequest(
                revision_id=source.revision_id,
                revision_sha256=source.content_sha256,
                review_id=receipt.review_id,
                mode="simulation",
                scenario_id="base",
                rationale="Explicitly freeze the adverse source case.",
            ),
        )
        repo.record_case_observation(case.case_id, observation_request(case, baseline, source))
        report = repo.case_realization(case.case_id, baseline.baseline_id)
        assert report["submitted_periods"] == 1
        assert report["periods"][5]["close_forecast"] == report["periods"][5]["current_forecast"]
        from pe_value_os.diligence.cases import prepare_revision

        raw["stage"] = "underwriting"
        with pytest.raises(ValueError, match="existing original"):
            prepare_revision(case, RevisionDraft.model_validate(raw), None)


def test_source_v2_api_roundtrip_and_forged_authority_rejected(repo, monkeypatch):
    from pe_value_os.api import app as api

    tokens = {
        "writer": {
            "sub": "service:test",
            "pvc_companies": ["exercise"],
            "pvc_principal_type": "service",
            "scope": "pvc.read pvc.write",
        }
    }
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.delenv("PVC_API_CLIENT_IDS", raising=False)
    monkeypatch.setattr(api, "get_ctx", lambda: SimpleNamespace(repo=repo))
    with security.principal_scope(principal()):
        case = setup(repo)
        parent = repo.append_case_revision(case.case_id, None, draft(scheduled=True))
    client = TestClient(api.app)
    path = f"/cases/{case.case_id}"
    body = {"expected_parent_revision_id": parent.revision_id, "draft": challenge(parent).model_dump(mode="json")}
    client.cookies.set("pvc_dev_session", "writer")
    assert client.post(path + "/revisions", json=body).status_code == 403
    headers = {"Authorization": "Bearer writer"}
    saved = client.post(path + "/revisions", json=body, headers=headers)
    assert saved.status_code == 201, saved.text
    revision = CaseRevision.model_validate(saved.json())
    assert isinstance(revision.draft.payload, SourceCasePayload)
    reviews = f"/case-revisions/{revision.revision_id}/reviews"
    assert (
        client.post(
            reviews, headers=headers, json={**request(revision).model_dump(mode="json"), "actor": "human:forged"}
        ).status_code
        == 422
    )
    assert (
        client.post(reviews, headers=headers, json=request(revision, mode="human").model_dump(mode="json")).status_code
        == 404
    )
    assert client.post(reviews, headers=headers, json=request(revision).model_dump(mode="json")).status_code == 201
    view = client.get(path, headers=headers).json()
    assert view["comparison"]["current_financials"]["source_classification"] == "constructed_operating_records"


def test_complete_source_replay_preserves_latest_capture_and_observations(tmp_path):
    from pe_value_os.cli import main

    root = Path("data/constructed/progress")
    output = tmp_path / "source-review"
    paths = [
        root / f"{name}.json"
        for name in ("underwriting", "operating-plan", "realization", "execution", "operating-sources")
    ]
    args = ["source-review-demo"]
    for flag, path in zip(
        ("underwriting", "operating-plan", "realization", "execution", "sources"), paths, strict=True
    ):
        args.extend(["--" + flag, str(path)])
    assert main([*args, "--output", str(output)]) == 0
    report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert len(report["revisions"]) == 5
    assert report["submitted_periods"] == 5
    for raw in report["revisions"]:
        CaseRevision.model_validate(raw)
    current = json.loads(report["revisions"][-1]["financial_result_json"])
    base = current["scenarios"][1]
    assert Decimal(next(a["value"] for a in base["assumptions"] if a["assumption_id"] == "capture")) == Decimal("0.5")
    assert base["year_one"]["incremental_ebitda"] == "-163165.00"
    assert base["year_one"]["pre_tax_cash_proxy"] == "-181890.00"
    assert base["total"]["working_capital_cash"] == "0.00"
    review = report["source_review"]
    assert [c["review"]["decision"] for c in review["checkpoints"]] == ["request_changes", "accept"]
    for checkpoint in review["checkpoints"]:
        for key in (
            "original_forecast",
            "close_forecast",
            "measured_difference",
            "attributed_difference",
            "unassigned_residual",
        ):
            assert (
                checkpoint["aggregate_recorded_periods"][key]
                == review["before_aggregate_recorded_periods"][key]
                == report["aggregate_recorded_periods"][key]
            )
    assert (
        review["before_aggregate_recorded_periods"]["current_forecast"]
        != report["aggregate_recorded_periods"]["current_forecast"]
    )
    assert report["human_review_count"] == 0 and report["actual_company_realized_value"] is None
    assert sum(c["delivery_support_valid"] for c in report["execution"]["final"]["claim_links"]) == 2
    assert "href='source-review.json' download" in output.with_suffix(".html").read_text(encoding="utf-8")
    report["revisions"][-1]["draft"]["reason"] = "<script>injection</script>"
    html = render_source_review(report, "review.json")
    assert "<script>injection</script>" not in html and "&lt;script&gt;" in html
    close_financial = json.loads(report["revisions"][1]["financial_result_json"])
    close_financial["scenarios"].reverse()
    close_financial["scenarios"] = close_financial["scenarios"][1:] + close_financial["scenarios"][:1]
    report["revisions"][1]["financial_result_json"] = json.dumps(close_financial)
    assert render_source_review(report, "review.json") == html
    for source in paths:
        with pytest.raises(ValueError, match="overwrite"):
            build_source_review_demo(*paths, source)
    assert main([*args, "--output", str(paths[0])]) == 2
