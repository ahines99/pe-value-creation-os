"""Replay authored work receipts through repository contracts and expose their limits."""

from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from ..adapters.repositories import Conflict, Repository
from ..research.render import table
from .cases import InvestmentCase
from .close_baseline import CloseBaseline
from .execution import ExecutionEvent, ExecutionEvidence, ExecutionRequest
from .exhibit_style import exhibit_page
from .models import Record
from .realization import AttributionRequest, ObservationRequest
from .realization_render import ExerciseMonth, RealizationExercise, demonstrate_realization
from .scheduling import OperatingPlan, fingerprint
from .underwriting import UnderwritingCase
from .underwriting_render import amount


class ExecutionStep(Record):
    step_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    label: str = Field(min_length=1)
    effective_on: date
    payload: dict[str, Any]
    evidence: tuple[ExecutionEvidence, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    previous_step: str | None = None
    expected_error: str | None = None


class ExecutionExercise(Record):
    schema_version: Literal[1] = 1
    classification: Literal["constructed_operating_exercise"]
    realization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exercise_as_of: date
    observation_extensions: tuple[ExerciseMonth, ...]
    steps: tuple[ExecutionStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def identities(self) -> ExecutionExercise:
        if len({s.step_id for s in self.steps}) != len(self.steps):
            raise ValueError("execution step IDs must be unique")
        if any(s.effective_on > self.exercise_as_of for s in self.steps):
            raise ValueError("replay steps cannot follow its stated review date")
        return self


def replay_execution(
    repo: Repository, case: InvestmentCase, baseline: CloseBaseline, exercise: ExecutionExercise
) -> dict[str, Any]:
    revision = repo.get_case_revision(baseline.request.revision_id)
    for month in exercise.observation_extensions:
        observations = repo.list_case_observations(case.case_id)
        previous = next((o for o in observations if o.request.observed.source_id == month.corrects_source_id), None)
        if month.corrects_source_id and previous is None:
            raise ValueError("extended source correction must bind an existing snapshot")
        observation = repo.record_case_observation(
            case.case_id,
            ObservationRequest(
                ingestion_key=month.observed.source_id,
                baseline_id=baseline.baseline_id,
                baseline_sha256=baseline.content_sha256,
                observed=month.observed,
                counterfactual=month.counterfactual,
                observed_sha256=fingerprint(month.observed),
                counterfactual_sha256=fingerprint(month.counterfactual),
                initiative_ids=tuple(json.loads(revision.financial_result_json)["selected_initiatives"]),
                scope_mapping_rationale=month.observed.scope_explanation,
                reason=month.rationale,
                expected_previous_id=previous.observation_id if previous else None,
            ),
        )
        repo.record_case_attribution(
            case.case_id,
            AttributionRequest(
                ingestion_key="claim-" + month.observed.source_id,
                observation_id=observation.observation_id,
                observation_sha256=observation.content_sha256,
                mode="simulation",
                evidence=month.evidence,
                allocations=month.allocations,
                rationale=month.rationale,
            ),
        )
    records: dict[str, ExecutionEvent] = {}
    checkpoints = []

    def bound(alias: str) -> dict[str, str]:
        if not isinstance(alias, str) or alias not in records:
            raise ValueError("execution alias must reference a preceding successful step")
        record = records[alias]
        return {"event_id": record.event_id, "sha256": record.content_sha256}

    for step in exercise.steps:
        payload = step.payload.copy()
        for key in ("assignment", "delivery", "acceptance"):
            if key in payload:
                payload[key] = bound(payload[key])
        if "prerequisite_acceptances" in payload:
            if not isinstance(payload["prerequisite_acceptances"], list):
                raise ValueError("prerequisite aliases must be a list")
            payload["prerequisite_acceptances"] = [bound(alias) for alias in payload["prerequisite_acceptances"]]
        if payload.get("kind") == "claim_link":
            source_id = payload.pop("attribution_source_id")
            claim_observation = next(
                (o for o in repo.list_case_observations(case.case_id) if o.request.observed.source_id == source_id),
                None,
            )
            if claim_observation is None:
                raise ValueError("claim source snapshot is absent")
            claims = [
                a
                for a in repo.list_case_attributions(case.case_id)
                if a.request.observation_id == claim_observation.observation_id
            ]
            if not claims:
                raise ValueError("claim batch is absent")
            claim = max(claims, key=lambda a: a.sequence)
            payload.update(attribution_id=claim.attribution_id, attribution_sha256=claim.content_sha256)
        previous_id = bound(step.previous_step)["event_id"] if step.previous_step else None
        request = ExecutionRequest(
            ingestion_key=step.step_id,
            baseline_id=baseline.baseline_id,
            baseline_sha256=baseline.content_sha256,
            mode="simulation",
            effective_on=step.effective_on,
            payload=payload,
            evidence=step.evidence,
            rationale=step.rationale,
            expected_previous_id=previous_id,
        )
        audit_count = len(repo.list_audit(company_id=case.company_id))
        rejection = None
        try:
            record = repo.record_execution_event(case.case_id, request)
        except (ValueError, Conflict) as exc:
            if not step.expected_error or step.expected_error not in str(exc):
                raise ValueError("execution replay failed its receipt or predecessor contract") from exc
            rejection = str(exc)
            if len(repo.list_audit(company_id=case.company_id)) != audit_count:
                raise ValueError("rejected execution attempt changed the audit trail") from exc
        else:
            if step.expected_error:
                raise ValueError("expected execution rejection was incorrectly accepted")
            records[step.step_id] = record
        view = repo.case_execution(case.case_id, baseline.baseline_id, exercise.exercise_as_of)
        checkpoints.append(
            {
                "step_id": step.step_id,
                "label": step.label,
                "effective_on": str(step.effective_on),
                "result": "rejected" if rejection else "recorded",
                "reason": rejection or step.rationale,
                "accepted_tasks": sum(t["acceptance_valid"] for t in view["tasks"]),
                "supported_links": sum(link["delivery_support_valid"] for link in view["claim_links"]),
            }
        )
    view = repo.case_execution(case.case_id, baseline.baseline_id, exercise.exercise_as_of)
    return {"exercise_sha256": fingerprint(exercise), "checkpoints": checkpoints, "final": view}


def render_execution(report: dict[str, Any], json_name: str) -> str:
    execution = report["execution"]
    view = execution["final"]
    tasks = view["tasks"]
    coverage = view["claim_coverage"]

    def e(value: Any) -> str:
        return escape(str(value))

    accepted = sum(t["acceptance_valid"] for t in tasks)
    supported = sum(c["status"] == "delivery_supported" for c in coverage)
    invalid = sum(c["status"] == "delivery_support_invalidated" for c in coverage)
    body = f"<section class='hero'><div><p class='eyebrow'>Execution review / Constructed demonstration</p><h1>Delivery evidence changes what a claim can support.</h1><p class='page-subtitle'>Exercise review: {e(view['exercise_as_of'])} · {e(report['currency'])} · Simulated people and receipts</p><p>Follow the proposed plan through assignment, completed work, acceptance and steering decisions. Then challenge claims when dates or evidence fail.</p></div><aside class='hero-aside'><span class='metric-label'>Authority boundary</span><p>Every operating record, identity and decision here is constructed. No company intervention, actual human acceptance or causal outcome is represented.</p></aside></section><div class='metrics-grid'>"
    for label, value, note in [
        ("Currently accepted work", f"{accepted} / {len(tasks)}", "Exact submissions and prerequisite receipts"),
        ("Claims with delivery support", supported, "Delivery support still does not establish causality"),
        ("Invalidated support links", invalid, "Financial observations remain in the ledger"),
        ("Actual company execution", "Unavailable", "No sponsor or permissioned pilot"),
    ]:
        body += f"<div class='metric-card'><span class='metric-label'>{e(label)}</span><strong class='metric-value'>{e(value)}</strong><span class='metric-note'>{e(note)}</span></div>"
    body += "</div><section class='panel' id='decision'><p class='eyebrow'>Executive reading</p><h2>Completed, accepted and permitted are different states.</h2><p>A submitted deliverable can await acceptance. A technically accepted gate can remain on hold. A positive claim can lack a full month of delivery support. A later withdrawn review can invalidate support without changing the accounting record.</p><p>This is a dated exercise using the latest evidence corrections. It is not a historical information-cutoff replay, independent quality validation, or an actual-plus-remaining financial forecast.</p></section>"
    body += "<section class='panel' id='gates'><h2>Current initiative decisions</h2>"
    body += (
        table(
            ["Initiative", "Steering decision", "Gate acceptance"],
            [
                [
                    e(i["initiative_id"]),
                    e(i["steering_decision"]),
                    "Supported" if i["gate_acceptance_valid"] else "Not supported",
                ]
                for i in view["initiatives"]
            ],
            "Steering is explicit and mode-bound. It does not activate live KPIs or authorize a company operation.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='delivery'><h2>Compare the plan with submitted work</h2>"
    rows = []
    for task in tasks:
        assignment = task["assignment"]["request"]["payload"] if task["assignment"] else None
        delivery = task["delivery"]["request"]["payload"] if task["delivery"] else None
        rows.append(
            [
                e(task["title"]),
                e(
                    assignment["operator_subject"]
                    if assignment and assignment["status"] == "assigned"
                    else "No recorded assignment"
                ),
                e(task["planned_finish"] or "Blocked"),
                e(delivery["completed_on"] or delivery["state"]) if delivery else "Not submitted",
                "Accepted" if task["acceptance_valid"] else e(task["acceptance_limitation"]),
            ]
        )
    body += table(
        ["Work package", "Recorded operator", "Planned finish", "Reported completion", "Acceptance assessment"],
        rows,
        "Original plan dates remain unchanged. Submission is an operator representation backed by authored evidence, not automatic verification of quality or actual hours worked.",
    )
    for task in tasks:
        body += f"<details><summary>{e(task['title'])}: criteria and review receipts</summary><div class='detail-body'><p><strong>Proposed acceptance criteria:</strong> {e(task['acceptance_criteria'])}</p>"
        for label, record in [("Submission", task["delivery"]), ("Latest review", task["acceptance"])]:
            if record:
                body += f"<p><strong>{e(label)}</strong> · {e(record['actor'])} · {e(record['request']['effective_on'])}<br>{e(record['request']['rationale'])}</p>"
                for evidence in record["request"]["evidence"]:
                    body += f"<p>{e(evidence['content'])}</p>"
        body += "</div></details>"
    body += "</section><section class='panel' id='challenge'><h2>Watch acceptance change the claim assessment</h2>"
    interesting = [
        c
        for c in execution["checkpoints"]
        if c["result"] == "rejected"
        or "link" in c["step_id"]
        or "withdraw" in c["step_id"]
        or "changes" in c["step_id"]
    ]
    body += (
        table(
            ["Exercise date / step", "Result", "Reason", "Supported links afterward"],
            [
                [e(c["effective_on"]) + "<br>" + e(c["label"]), e(c["result"]), e(c["reason"]), e(c["supported_links"])]
                for c in interesting
            ],
            "Rejected attempts leave no execution receipt or audit mutation. This replay manifest separately preserves the expected challenge outcome.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='claims'><h2>Delivery support is narrower than a financial claim</h2>"
    linked = [c for c in coverage if c["link_event_id"]]
    body += table(
        ["Source month / initiative", "Posting", "Claim amount", "Delivery assessment"],
        [
            [
                e(c["period_start"][:7]) + "<br>" + e(c["initiative_id"]),
                e(c["row_id"]),
                e(amount(c["amount"])),
                e(c["status"].replace("_", " "))
                + "<br>"
                + e(c["limitation"] or "Exact delivery chain supports timing. Causality remains unvalidated."),
            ]
            for c in linked
        ],
        "Amounts use the case currency. A link cannot transfer to a corrected source or claim batch. Benefits need gate acceptance before the whole recorded month; partial months are not prorated.",
    )
    body += "<details><summary>Inspect every active allocation, including unlinked and adverse claims</summary><div class='detail-body'>"
    body += (
        table(
            ["Source / initiative", "Posting", "Claim", "State"],
            [
                [
                    e(c["source_id"]) + "<br>" + e(c["initiative_id"]),
                    e(c["row_id"]),
                    e(amount(c["amount"])),
                    e(c["status"].replace("_", " ")),
                ]
                for c in coverage
            ],
            "Signed adverse and cost claims remain visible regardless of readiness. Income and cash postings are distinct and must not be added together.",
        )
        + "</div></details>"
    )
    totals = report["aggregate_recorded_periods"]
    body += f"<p class='x-callout'>Across {e(report['submitted_periods'])} recorded months, the scoped accounting difference remains <strong>{e(amount(totals['measured_difference']['incremental_ebitda']))} EBITDA</strong> and <strong>{e(amount(totals['measured_difference']['pre_tax_cash_proxy']))} pre-tax cash</strong>. These totals do not become realized initiative value when a delivery link is recorded. The financial ledger preserves all source comparisons, costs, claims and residuals.</p>"
    body += f"<p>{e(view['limitation'])}</p><p><a href='{escape(json_name, quote=True)}' download>Download execution receipts, financial comparisons and audit JSON</a></p><p><a href='realization.html'>Inspect the initial accounting comparison</a> · <a href='operating-plan.html'>Review the original capacity plan</a> · <a href='decision-memo.html'>Read the executive memo</a></p></section>"
    return exhibit_page(
        title="Execution acceptance — Value Creation OS",
        kind="Execution review",
        provenance="Constructed demonstration",
        nav=[("#delivery", "Delivery"), ("#challenge", "Challenges"), ("#claims", "Claim support")],
        body=body,
    )


def build_execution_demo(
    underwriting: Path, operating_plan: Path, realization: Path, execution: Path, output: Path
) -> Path:
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if {p.resolve() for p in (underwriting, operating_plan, realization, execution)} & {
        html_path.resolve(),
        json_path.resolve(),
    }:
        raise ValueError("execution report must not overwrite its sources")
    financial = RealizationExercise.model_validate_json(realization.read_bytes())
    exercise = ExecutionExercise.model_validate_json(execution.read_bytes())
    if exercise.realization_sha256 != fingerprint(financial):
        raise ValueError("execution rehearsal must bind the exact realization exercise")
    report = demonstrate_realization(
        UnderwritingCase.model_validate_json(underwriting.read_bytes()),
        OperatingPlan.model_validate_json(operating_plan.read_bytes()),
        financial,
        lambda repo, case, baseline: replay_execution(repo, case, baseline, exercise),
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_execution(report, json_path.name), encoding="utf-8")
    return html_path
