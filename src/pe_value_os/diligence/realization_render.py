"""Executive-facing constructed accounting and attribution walkthrough."""

from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from pydantic import Field, model_validator

from .. import security
from ..adapters.evidence_store import FileSystemEvidenceStore
from ..adapters.repositories import InMemoryRepository
from ..api.presentation import CSS
from ..domain.source_models import CompanyProfile
from ..research.render import table
from .cases import CasePayload, ReviewRequest, RevisionDraft
from .close_baseline import CloseBaselineRequest
from .models import Record
from .realization import Allocation, AttributionRequest, ClaimEvidence, ObservationRequest, SourceBook
from .scheduling import OperatingPlan, fingerprint
from .underwriting import UnderwritingCase
from .underwriting_render import amount


class ExerciseMonth(Record):
    observed: SourceBook
    counterfactual: SourceBook
    corrects_source_id: str | None = None
    evidence: tuple[ClaimEvidence, ...]
    allocations: tuple[Allocation, ...]
    rationale: str = Field(min_length=1)


class RealizationExercise(Record):
    schema_version: Literal[1] = 1
    classification: Literal["constructed_operating_exercise"]
    underwriting_sha256: str
    operating_plan_sha256: str
    months: tuple[ExerciseMonth, ...] = Field(min_length=1)
    current_forecast_capture: Decimal = Field(ge=0, le=1)
    current_forecast_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sources(self) -> RealizationExercise:
        ids = [m.observed.source_id for m in self.months]
        if len(ids) != len(set(ids)):
            raise ValueError("each source snapshot needs a unique identity")
        return self


def demonstrate_realization(
    case: UnderwritingCase, plan: OperatingPlan, exercise: RealizationExercise
) -> dict[str, Any]:
    if (exercise.underwriting_sha256, exercise.operating_plan_sha256) != (fingerprint(case), fingerprint(plan)):
        raise ValueError("exercise must bind the exact underwriting and operating plan")
    plan.bind(case)
    company_id = "progress-constructed-exercise"
    with TemporaryDirectory(prefix="pvc-realization-") as temporary:
        repo = InMemoryRepository(FileSystemEvidenceStore(temporary))
        with security.principal_scope(
            security.system_principal(company_id, subject="service:constructed-realization-demo")
        ):
            repo.upsert_company(
                CompanyProfile(
                    company_id=company_id,
                    name="Constructed operating exercise",
                    business_model="Method demonstration",
                    vertical="Software",
                    currency=case.currency,
                    fiscal_year_start_month=10,
                )
            )
            registered = repo.create_investment_case(
                company_id, case.case_id, "Underwriting to constructed accounting comparison", case.currency
            )
            payload = CasePayload(
                underwriting=case,
                decision_question="How much of the scoped financial difference has an explicit initiative claim?",
                counterevidence=(
                    "Constructed accounting records and an authored counterfactual cannot establish actual company impact.",
                ),
                unresolved_items=(
                    "Sponsor, actual records, work acceptance and independent attribution challenge remain absent.",
                ),
            )
            first = repo.append_case_revision(
                registered.case_id,
                None,
                RevisionDraft(
                    stage="underwriting",
                    effective_on=case.start,
                    reason="Preserve original constructed assumptions.",
                    payload=payload,
                ),
            )
            scheduled = CasePayload.model_validate(
                {**payload.model_dump(mode="json"), "operating_plan": plan.model_dump(mode="json")}
            )
            close = repo.append_case_revision(
                registered.case_id,
                first.revision_id,
                RevisionDraft(
                    stage="close_validation",
                    effective_on=case.start,
                    reason="Freeze capacity-tested hypothetical-close economics.",
                    payload=scheduled,
                ),
            )
            review = repo.review_case_revision(
                close.revision_id,
                ReviewRequest(
                    expected_revision_sha256=close.content_sha256,
                    mode="simulation",
                    decision="accept",
                    rationale="Simulated acceptance for a constructed comparison; no company execution authorized.",
                ),
            )
            baseline = repo.designate_close_baseline(
                registered.case_id,
                CloseBaselineRequest(
                    revision_id=close.revision_id,
                    revision_sha256=close.content_sha256,
                    review_id=review.review_id,
                    mode="simulation",
                    scenario_id="base",
                    rationale="Do not move the comparison anchor when a later forecast changes.",
                ),
            )
            ids: dict[str, str] = {}
            transitions = []
            for month in exercise.months:
                if month.corrects_source_id is not None and month.corrects_source_id not in ids:
                    raise ValueError("correction must refer to a previously imported source snapshot")
                observation = repo.record_case_observation(
                    registered.case_id,
                    ObservationRequest(
                        ingestion_key=month.observed.source_id,
                        baseline_id=baseline.baseline_id,
                        baseline_sha256=baseline.content_sha256,
                        observed=month.observed,
                        counterfactual=month.counterfactual,
                        observed_sha256=fingerprint(month.observed),
                        counterfactual_sha256=fingerprint(month.counterfactual),
                        initiative_ids=tuple(json.loads(close.financial_result_json)["selected_initiatives"]),
                        scope_mapping_rationale=month.observed.scope_explanation,
                        reason=month.rationale,
                        expected_previous_id=ids.get(month.corrects_source_id or ""),
                    ),
                )
                ids[month.observed.source_id] = observation.observation_id
                before = repo.case_realization(registered.case_id, baseline.baseline_id)
                period = next(p for p in before["periods"] if p["start"] == str(month.observed.start))
                if period["status"] != "reconciled":
                    raise ValueError("demonstration requires reconciled source controls before recording claims")
                transitions.append(
                    {
                        "source_id": month.observed.source_id,
                        "corrects_source_id": month.corrects_source_id,
                        "before_new_claims": period["attribution_status"],
                        "measured_ebitda": period["measured_difference"]["incremental_ebitda"],
                    }
                )
                repo.record_case_attribution(
                    registered.case_id,
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
            # A separate authored forecast challenge changes one named assumption.
            # It is never estimated automatically from the accounting differences.
            updated = case.model_dump(mode="json")
            for scenario in updated["scenarios"]:
                if scenario["scenario_id"] == "base":
                    next(a for a in scenario["assumptions"] if a["assumption_id"] == "capture").update(
                        value=str(exercise.current_forecast_capture), rationale=exercise.current_forecast_rationale
                    )
            current_case = UnderwritingCase.model_validate(updated)
            current_plan = OperatingPlan.model_validate(
                {**plan.model_dump(mode="json"), "underwriting_sha256": fingerprint(current_case)}
            )
            current_payload = CasePayload.model_validate(
                {
                    **payload.model_dump(mode="json"),
                    "underwriting": current_case.model_dump(mode="json"),
                    "operating_plan": current_plan.model_dump(mode="json"),
                }
            )
            repo.append_case_revision(
                registered.case_id,
                close.revision_id,
                RevisionDraft(
                    stage="ownership_review",
                    effective_on=max(m.observed.end for m in exercise.months),
                    reason=exercise.current_forecast_rationale,
                    payload=current_payload,
                ),
            )
            report = repo.case_realization(registered.case_id, baseline.baseline_id)
            report.update(
                revisions=[r.model_dump(mode="json") for r in repo.list_case_revisions(registered.case_id)],
                audit=[a.model_dump(mode="json") for a in repo.list_audit(company_id=company_id)],
                transitions=transitions,
                exercise_sha256=fingerprint(exercise),
                human_review_count=0,
            )
            return report


def render_realization(report: dict[str, Any], json_name: str) -> str:
    aggregate = report["aggregate_recorded_periods"]
    if aggregate is None:
        raise ValueError("executive replay requires at least one fully reconciled recorded period")
    submitted = [p for p in report["periods"] if p["status"] != "not_recorded"]
    currency = report["currency"]
    count = len(submitted)
    missing = len(report["periods"]) - count
    working_capital = sum(
        (Decimal(str(p["measured_difference"]["working_capital_cash"])) for p in submitted), Decimal(0)
    )
    early = [
        p["start"][:7]
        for p in submitted
        if Decimal(str(p["attributed_difference"]["revenue"])) > 0
        and Decimal(str(p["close_forecast"]["gross_price_benefit"])) == 0
    ]

    def e(value: Any) -> str:
        return escape(str(value))

    body = f"<section class='hero'><div><p class='eyebrow'>Operating review / Constructed demonstration</p><h1>Explain the result before claiming the value.</h1><p class='page-subtitle'>{count} recorded months · {e(currency)} · Simulated attribution</p><p>Keep the reviewed plan fixed. Reconcile scoped accounting records, challenge the counterfactual and show which differences remain unassigned.</p></div><aside class='hero-aside'><span class='metric-label'>Evidence boundary</span><p>All operating records and attribution claims here are authored examples. No Progress operating result or intervention is represented.</p></aside></section><div class='metrics-grid'>"
    for label, value, note in [
        (
            "Measured EBITDA difference",
            aggregate["measured_difference"]["incremental_ebitda"],
            "Observed-book less authored counterfactual",
        ),
        (
            "Claimed initiative EBITDA",
            aggregate["attributed_difference"]["incremental_ebitda"],
            "Explicit claims; not causal proof",
        ),
        (
            "Unassigned EBITDA",
            aggregate["unassigned_residual"]["incremental_ebitda"],
            "Retained outside initiative claims",
        ),
        (
            "Measured pre-tax cash",
            aggregate["measured_difference"]["pre_tax_cash_proxy"],
            "Operating, working-capital and capital cash",
        ),
    ]:
        body += f"<div class='metric-card'><span class='metric-label'>{e(label)}</span><strong class='metric-value'>{e(amount(value))}</strong><span class='metric-note'>{e(note)}</span></div>"
    timing_note = (
        "Positive revenue claims appear in months with no modeled pricing benefit: "
        + ", ".join(early)
        + ". Timing requires challenge. "
        if early
        else ""
    )
    body += f"</div><section class='panel' id='decision'><p class='eyebrow'>Executive reading</p><h2>Cash improvement is not earnings delivery.</h2><p>The recorded-period EBITDA difference is {e(amount(aggregate['measured_difference']['incremental_ebitda']))}. Working-capital cash contributes {e(amount(working_capital))} and has zero EBITDA effect. Missing later observations cannot confirm a modeled cash reversal.</p><p>No work-acceptance events are recorded. {e(timing_note)}Limited-confidence simulation does not validate initiative delivery. Reconciliation confirms that rows sum to declared controls. It does not validate the counterfactual or prove attribution. A source correction removes previous claims from the active comparison until they are reconsidered.</p></section>"
    body += "<section class='panel' id='comparison'><h2>Compare the same recorded months</h2><p>The current scenario is an authored re-estimate of the entire comparison horizon, including recorded months; it is not a locked actual-plus-remaining forecast. Original and close forecasts are preserved. No partial-period number is annualized.</p>"
    names = [
        ("original_forecast", "Original underwriting"),
        ("close_forecast", "Frozen hypothetical close"),
        ("current_forecast", "Current authored re-estimate"),
        ("measured_difference", "Measured accounting difference"),
        ("attributed_difference", "Explicit initiative claims"),
        ("unassigned_residual", "Unassigned remainder"),
    ]
    body += (
        table(
            ["View", "EBITDA / " + e(currency), "Pre-tax cash / " + e(currency)],
            [
                [
                    e(label),
                    e(amount(aggregate[key]["incremental_ebitda"])),
                    e(amount(aggregate[key]["pre_tax_cash_proxy"])),
                ]
                for key, label in names
            ],
            "Recorded months: "
            + ", ".join(e(p["start"][:7]) for p in submitted)
            + ". Forecasts and source differences use the same calendar, currency and disclosed initiative scope.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='months'><h2>Review each accounting close</h2>"
    body += table(
        ["Month", "Measured EBITDA", "Claimed EBITDA", "Unassigned EBITDA", "Measured cash"],
        [
            [
                e(p["start"][:7]),
                *[
                    e(amount(p[k]["incremental_ebitda"]))
                    for k in ("measured_difference", "attributed_difference", "unassigned_residual")
                ],
                e(amount(p["measured_difference"]["pre_tax_cash_proxy"])),
            ]
            for p in submitted
        ],
        f"Known zeros are recorded explicitly. {missing} forecast months have no observation; a day-100 actual is unavailable.",
    )
    for p in submitted:
        body += f"<details><summary>{e(p['start'][:7])}: inspect source reconciliation and claim residuals</summary><div class='detail-body'>"
        body += table(
            ["Component", "Observed book", "Counterfactual", "Difference", "Claimed", "Unassigned"],
            [
                [
                    e(r["label"]),
                    *[
                        e(amount(r[k]))
                        for k in ("observed", "counterfactual", "difference", "attributed", "unassigned")
                    ],
                ]
                for r in p["rows"]
            ],
            "Signed scoped income/cash movements, not consolidated Progress accounts. Operating expenses exclude D&A, interest and tax. Positive cash is inflow.",
        )
        body += (
            table(
                ["Book / control", "Declared", "Calculated", "Check"],
                [
                    [
                        e(kind + " / " + c["component"]),
                        e(amount(c["control"])),
                        e(amount(c["calculated"])),
                        e(c["status"]),
                    ]
                    for kind, checks in p["source_checks"].items()
                    for c in checks
                ],
                "Seven checks per source book. Controls are authored fixture values, not audited accounting statements.",
            )
            + "</div></details>"
        )
    body += "</section><section class='panel' id='correction'><h2>A correction does not inherit credit.</h2><p>A source correction retains both versions and leaves the new snapshot unassigned until a fresh claim is recorded. The replay history below shows each source and its measured earnings difference before new attribution.</p>"
    body += (
        table(
            ["Source snapshot", "Replaces", "Claim state before new review", "Measured EBITDA"],
            [
                [
                    e(t["source_id"]),
                    e(t["corrects_source_id"] or "Initial record"),
                    e(t["before_new_claims"]),
                    e(amount(t["measured_ebitda"])),
                ]
                for t in report["transitions"]
            ],
            "All claims in this replay use a service identity and simulation mode. No human review is invented.",
        )
        + "</section>"
    )
    body += "<section class='panel' id='claims'><h2>Inspect what each claim asserts</h2>"
    superseded = {o["request"]["expected_previous_id"] for o in report["observations"]}
    sources = {o["observation_id"]: o["request"]["observed"] for o in report["observations"]}
    for a in report["attributions"]:
        source = sources[a["request"]["observation_id"]]
        state = "Historical: source superseded" if a["request"]["observation_id"] in superseded else "Current snapshot"
        body += f"<details><summary>{e(source['source_id'])} · {e(state)}</summary><div class='detail-body'><p>{e(source['method_and_limits'])}</p>"
        body += table(
            ["Posting / initiative", "Claim", "Rationale", "Confidence / alternative"],
            [
                [
                    e(x["row_id"] + " / " + x["initiative_id"]),
                    e(amount(x["amount"])),
                    e(x["rationale"]),
                    e(x["confidence"] + " / " + x["alternative_explanation"]),
                ]
                for x in a["request"]["allocations"]
            ],
            "Allocation caps prevent claiming more than the row difference. They do not establish causality.",
        )
        for evidence in a["request"]["evidence"]:
            body += f"<p><strong>{e(evidence['evidence_id'])}</strong>: {e(evidence['content'])}</p>"
        body += "</div></details>"
    body += f"<p>{e(report['limitation'])}</p><p><a href='{escape(json_name, quote=True)}' download>Download source snapshots, claims, forecasts and audit JSON</a></p><p><a href='case-history.html'>Review the versioning method</a> · <a href='decision-memo.html'>Return to the executive memo</a> · <a href='../pilot/permissioned/README.md'>Read the permissioned pilot package</a></p></section>"
    css = ".detail-body{padding:1rem;overflow-wrap:anywhere}.primary-nav{flex-wrap:wrap}.hero h1{max-width:22ch}"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Constructed realization review — Value Creation OS</title><style>"
        + CSS
        + css
        + "</style></head><body><a class='skip-link' href='#main'>Skip to content</a><header class='topbar'><div class='topbar-inner'><a class='brand' href='#main'>Value Creation OS · Operating review</a><nav class='primary-nav' aria-label='Sections'><a class='nav-link' href='#comparison'>Comparison</a><a class='nav-link' href='#months'>Monthly close</a><a class='nav-link' href='#claims'>Attribution</a></nav></div></header><main class='app-shell' id='main' tabindex='-1'>"
        + body
        + "</main></body></html>"
    )


def build_realization_demo(underwriting: Path, operating_plan: Path, exercise_path: Path, output: Path) -> Path:
    sources = {p.resolve() for p in (underwriting, operating_plan, exercise_path)}
    html_path, json_path = output.with_suffix(".html"), output.with_suffix(".json")
    if sources & {html_path.resolve(), json_path.resolve()}:
        raise ValueError("report must not overwrite its sources")
    report = demonstrate_realization(
        UnderwritingCase.model_validate_json(underwriting.read_bytes()),
        OperatingPlan.model_validate_json(operating_plan.read_bytes()),
        RealizationExercise.model_validate_json(exercise_path.read_bytes()),
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, default=str, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_realization(report, json_path.name), encoding="utf-8")
    return html_path
