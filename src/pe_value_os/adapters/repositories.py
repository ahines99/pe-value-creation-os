"""Repository interface and in-memory implementation (PVC-031).

Scope rules (both implementations):
- Methods that take `company_id` raise `ScopeError` when the current principal may not access it.
- Lookups by id return `NotFound` for rows outside the principal's scope, exactly as PostgreSQL row-level
  security hides them, so callers cannot probe for other companies' ids.
"""

from __future__ import annotations

import copy
import hashlib
import os
import threading
import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from .. import security
from ..diligence import private_attribution, private_review
from ..diligence.cases import (
    CaseReview,
    CaseRevision,
    InvestmentCase,
    ReviewRequest,
    RevisionDraft,
    new_case,
    prepare_review,
    prepare_revision,
    writer,
)
from ..diligence.close_baseline import CloseBaseline, CloseBaselineRequest, prepare_close_baseline
from ..diligence.execution import (
    ExecutionEvent,
    ExecutionRequest,
    execution_report,
    prepare_execution,
    stream_key,
)
from ..diligence.private_baselines import (
    BaselineRequest,
    PlanReviewRequest,
    PrivateBaseline,
    PrivatePlanReview,
)
from ..diligence.private_baselines import (
    baseline_view as private_baseline_view,
)
from ..diligence.private_baselines import (
    prepare_baseline as prepare_private_baseline,
)
from ..diligence.private_baselines import (
    prepare_review as prepare_private_plan_review,
)
from ..diligence.private_baselines import (
    require_baseline_author as require_private_baseline_author,
)
from ..diligence.private_baselines import (
    require_reviewer as require_private_plan_reviewer,
)
from ..diligence.private_baselines import (
    review_heads as private_review_heads,
)
from ..diligence.private_capacity import (
    CapacityPlanRequest,
    PrivateCapacityRevision,
)
from ..diligence.private_capacity import (
    prepare_revision as prepare_private_capacity,
)
from ..diligence.private_capacity import (
    verify_revision as verify_private_capacity,
)
from ..diligence.private_execution import PrivateExecutionEvent, PrivateExecutionRequest
from ..diligence.private_execution import execution_view as private_execution_view
from ..diligence.private_execution import prepare_event as prepare_private_execution
from ..diligence.private_execution import reducing_support as execution_reducing_support
from ..diligence.private_execution import require_author as require_private_execution_author
from ..diligence.private_financials import (
    FinancialSnapshotRequest,
    PrivateFinancialSnapshot,
    prepare_snapshot,
    require_current_snapshot,
    require_snapshot_writer,
)
from ..diligence.private_financials import (
    verify_snapshot as verify_private_financial_snapshot,
)
from ..diligence.private_grants import (
    GrantEvent,
    GrantRequest,
)
from ..diligence.private_grants import (
    prepare_event as prepare_grant_event,
)
from ..diligence.private_grants import (
    require_author as require_grant_author,
)
from ..diligence.private_grants import (
    require_reader as require_grant_reader,
)
from ..diligence.private_grants import (
    validate_key as validate_grant_key,
)
from ..diligence.private_observations import (
    CounterfactualRequest,
    CounterfactualReview,
    CounterfactualReviewRequest,
    PrivateCounterfactual,
    PrivateObservation,
    PrivateObservationRequest,
    counterfactual_review_head,
    prepare_counterfactual,
    prepare_counterfactual_review,
    verify_counterfactual,
    verify_observation,
)
from ..diligence.private_observations import prepare_observation as prepare_private_observation
from ..diligence.private_records import (
    FinanceReview,
    FinanceReviewRequest,
    IntakeRequest,
    PrivateIntake,
    authorize_source,
    prepare_intake,
    require_finance_reviewer,
    require_intake_writer,
)
from ..diligence.private_records import prepare_review as prepare_private_review
from ..diligence.private_underwriting import (
    PrivateUnderwritingRevision,
    UnderwritingRequest,
)
from ..diligence.private_underwriting import (
    prepare_revision as prepare_private_underwriting,
)
from ..diligence.private_underwriting import (
    verify_revision as verify_private_underwriting,
)
from ..diligence.realization import (
    Attribution,
    AttributionRequest,
    Observation,
    ObservationRequest,
    prepare_attribution,
    prepare_observation,
    realization_report,
)
from ..domain.kpi_models import KpiAlert, KpiDefinition, KpiObservation, Notification
from ..domain.models import AuditEvent, EvidenceRef, Finding
from ..domain.project_models import Opportunity, PriorityScore, ValueCase
from ..domain.runs import ApprovalDecision, ApprovalRecord, PlanRecord, RunRecord, RunState, Status
from ..domain.source_models import CompanyProfile
from .base import EvidenceRecord
from .evidence_store import EvidenceStore, FileSystemEvidenceStore


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


class LeaseLost(Conflict):
    """An execution no longer owns its database lease."""


LEASE: ContextVar[tuple[str, str] | None] = ContextVar("pvc_execution_lease", default=None)


class FencedRepository:
    """Bind every operation to a unique claim; checks and mutations share a transaction/lock."""

    def __init__(self, repo: Any, run_id: str, owner: str):
        self._repo, self._run_id, self._owner = repo, run_id, owner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._repo, name)
        if not callable(attr):
            return attr

        def fenced(*args: Any, **kwargs: Any) -> Any:
            token = LEASE.set((self._run_id, self._owner))
            try:
                if isinstance(self._repo, InMemoryRepository):
                    with self._repo._lock:
                        if not self._repo.lease_valid(self._run_id, self._owner):
                            raise LeaseLost(self._run_id)
                        return attr(*args, **kwargs)
                return attr(*args, **kwargs)
            finally:
                LEASE.reset(token)

        return fenced


def now() -> datetime:
    return datetime.now(UTC)


class Repository(Protocol):
    def private_review_index(self, company_id: str) -> list[dict[str, Any]]: ...
    def private_attribution_review_packet(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> dict[str, Any]: ...
    def list_private_attributions(
        self, company_id: str, case_key: str, key: str
    ) -> list[private_attribution.PrivateAttribution]: ...
    def record_private_attribution(
        self,
        company_id: str,
        case_key: str,
        key: str,
        request: private_attribution.AttributionRequest,
        environment_id: str,
    ) -> private_attribution.PrivateAttribution: ...
    def list_private_attribution_reviews(
        self, company_id: str, revision_id: str
    ) -> list[private_attribution.AttributionReview]: ...
    def review_private_attribution(
        self,
        company_id: str,
        revision_id: str,
        request: private_attribution.AttributionReviewRequest,
        environment_id: str,
    ) -> private_attribution.AttributionReview: ...
    def usable_private_attribution(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> tuple[private_attribution.PrivateAttribution, private_attribution.AttributionReview]: ...
    def list_private_execution_events(self, company_id: str, baseline_id: str) -> list[PrivateExecutionEvent]: ...
    def record_private_execution(
        self, company_id: str, baseline_id: str, request: PrivateExecutionRequest, environment_id: str
    ) -> PrivateExecutionEvent: ...
    def private_execution_status(self, company_id: str, baseline_id: str, environment_id: str) -> dict[str, Any]: ...
    def list_private_counterfactuals(self, company_id: str, case_key: str, key: str) -> list[PrivateCounterfactual]: ...
    def record_private_counterfactual(
        self, company_id: str, case_key: str, key: str, request: CounterfactualRequest, environment_id: str
    ) -> PrivateCounterfactual: ...
    def list_private_counterfactual_reviews(self, company_id: str, revision_id: str) -> list[CounterfactualReview]: ...
    def review_private_counterfactual(
        self, company_id: str, revision_id: str, request: CounterfactualReviewRequest, environment_id: str
    ) -> CounterfactualReview: ...
    def usable_private_counterfactual(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> tuple[PrivateCounterfactual, CounterfactualReview]: ...
    def list_private_observations(self, company_id: str, case_key: str, key: str) -> list[PrivateObservation]: ...
    def record_private_observation(
        self, company_id: str, case_key: str, key: str, request: PrivateObservationRequest, environment_id: str
    ) -> PrivateObservation: ...
    def usable_private_observation(
        self, company_id: str, observation_id: str, environment_id: str
    ) -> PrivateObservation: ...
    def list_private_plan_reviews(self, company_id: str, revision_id: str) -> list[PrivatePlanReview]: ...
    def review_private_capacity(
        self, company_id: str, revision_id: str, request: PlanReviewRequest, environment_id: str
    ) -> PrivatePlanReview: ...
    def list_private_baselines(self, company_id: str, case_key: str) -> list[PrivateBaseline]: ...
    def freeze_private_baseline(
        self, company_id: str, case_key: str, request: BaselineRequest, environment_id: str
    ) -> PrivateBaseline: ...
    def private_baseline_status(self, company_id: str, baseline_id: str, environment_id: str) -> dict[str, Any]: ...
    def list_private_capacity_plans(self, company_id: str, case_key: str) -> list[PrivateCapacityRevision]: ...
    def record_private_capacity_plan(
        self, company_id: str, case_key: str, request: CapacityPlanRequest, environment_id: str
    ) -> PrivateCapacityRevision: ...
    def usable_private_capacity_plan(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> PrivateCapacityRevision: ...
    def list_private_underwriting(self, company_id: str, case_key: str) -> list[PrivateUnderwritingRevision]: ...
    def record_private_underwriting(
        self, company_id: str, case_key: str, request: UnderwritingRequest, environment_id: str
    ) -> PrivateUnderwritingRevision: ...
    def usable_private_underwriting(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> PrivateUnderwritingRevision: ...
    def list_private_financial_snapshots(self, company_id: str, case_key: str) -> list[PrivateFinancialSnapshot]: ...
    def record_private_financial_snapshot(
        self, company_id: str, case_key: str, request: FinancialSnapshotRequest, environment_id: str
    ) -> PrivateFinancialSnapshot: ...
    def usable_private_financial_snapshot(
        self, company_id: str, snapshot_id: str, environment_id: str
    ) -> PrivateFinancialSnapshot: ...
    def list_private_intakes(self, company_id: str, dataset_key: str) -> list[PrivateIntake]: ...
    def list_private_finance_reviews(self, company_id: str, intake_id: str) -> list[FinanceReview]: ...
    def record_private_intake(
        self, company_id: str, dataset_key: str, request: IntakeRequest, raw: bytes, environment_id: str
    ) -> PrivateIntake: ...
    def review_private_intake(
        self, company_id: str, intake_id: str, request: FinanceReviewRequest, environment_id: str
    ) -> FinanceReview: ...
    def private_intake_source(
        self, company_id: str, intake_id: str, environment_id: str, *, accepted_only: bool = False
    ) -> bytes: ...

    def list_private_grants(self, company_id: str, grant_key: str) -> list[GrantEvent]: ...

    def record_private_grant(self, company_id: str, grant_key: str, request: GrantRequest) -> GrantEvent: ...

    evidence_store: EvidenceStore

    def create_investment_case(self, company_id: str, case_id: str, label: str, currency: str) -> InvestmentCase: ...
    def get_investment_case(self, case_id: str) -> InvestmentCase: ...
    def append_case_revision(self, case_id: str, expected_parent: str | None, draft: RevisionDraft) -> CaseRevision: ...
    def get_case_revision(self, revision_id: str) -> CaseRevision: ...
    def list_case_revisions(self, case_id: str) -> list[CaseRevision]: ...
    def review_case_revision(self, revision_id: str, request: ReviewRequest) -> CaseReview: ...
    def list_execution_events(self, case_id: str) -> list[ExecutionEvent]: ...
    def record_execution_event(self, case_id: str, request: ExecutionRequest) -> ExecutionEvent: ...
    def case_execution(self, case_id: str, baseline_id: str, as_of: date) -> dict[str, Any]: ...
    def list_case_observations(self, case_id: str) -> list[Observation]: ...
    def list_case_attributions(self, case_id: str) -> list[Attribution]: ...
    def record_case_observation(self, case_id: str, request: ObservationRequest) -> Observation: ...
    def record_case_attribution(self, case_id: str, request: AttributionRequest) -> Attribution: ...
    def case_realization(self, case_id: str, baseline_id: str) -> dict[str, Any]: ...
    def list_close_baselines(self, case_id: str) -> list[CloseBaseline]: ...
    def designate_close_baseline(self, case_id: str, request: CloseBaselineRequest) -> CloseBaseline: ...
    def list_case_reviews(self, case_id: str) -> list[CaseReview]: ...

    # companies
    def upsert_company(self, profile: CompanyProfile) -> None: ...
    def get_company(self, company_id: str) -> CompanyProfile: ...
    def list_companies(self) -> list[str]: ...

    # evidence
    def add_evidence(self, record: EvidenceRecord) -> str: ...
    def get_evidence(self, evidence_id: str) -> EvidenceRef: ...
    def list_evidence(self, company_id: str, evidence_ids: list[str] | None = None) -> list[EvidenceRef]: ...
    def evidence_for_opportunity(self, company_id: str, opportunity_id: str) -> list[EvidenceRef]: ...
    def evidence_content(self, evidence_id: str) -> bytes: ...

    # runs
    def create_run(
        self,
        company_id: str,
        requested_by: str,
        *,
        project_type: str = "value_creation_diagnostic",
        idempotency_key: str | None = None,
        reference_date: date | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[RunRecord, bool]: ...
    def get_run(self, run_id: str) -> RunRecord: ...
    def save_run_state(self, state: RunState) -> None: ...
    def list_runs(self, company_id: str | None = None, status: Status | None = None) -> list[RunRecord]: ...
    def request_resume(self, run_id: str) -> None: ...
    def claim_runnable(self, worker_id: str, limit: int = 5) -> list[RunRecord]: ...
    def acquire_run(self, run_id: str, worker_id: str) -> bool: ...
    def renew_lease(self, run_id: str, worker_id: str) -> bool: ...
    def release_run(self, run_id: str, worker_id: str | None = None) -> None: ...

    def fenced_run(self, run_id: str, owner: str) -> Any: ...

    # findings, opportunities, value cases, priorities
    def add_finding(self, finding: Finding) -> None: ...
    def list_findings(self, run_id: str) -> list[Finding]: ...
    def add_opportunity(self, opp: Opportunity, proposer: str, flow_through_rule: str = "") -> None: ...
    def get_opportunity(self, company_id: str, opportunity_id: str) -> Opportunity: ...
    def list_opportunities(self, run_id: str) -> list[Opportunity]: ...
    def save_value_case(self, company_id: str, run_id: str, vc: ValueCase, policy_version: str) -> None: ...
    def get_value_case(self, company_id: str, opportunity_id: str) -> ValueCase: ...
    def list_value_cases(self, run_id: str) -> list[ValueCase]: ...
    def save_priorities(self, run_id: str, company_id: str, scores: list[PriorityScore]) -> None: ...
    def list_priorities(self, run_id: str) -> list[PriorityScore]: ...

    # plans and approvals
    def approval_transaction(self) -> AbstractContextManager[None]: ...
    def save_plan(self, record: PlanRecord) -> None: ...
    def get_plan(self, plan_id: str) -> PlanRecord: ...
    def latest_plan(self, run_id: str) -> PlanRecord | None: ...
    def update_plan_status(self, plan_id: str, status: str, approved_plan: dict[str, Any] | None = None) -> None: ...
    def create_approval_request(
        self, run_id: str, company_id: str, artifact_type: str, artifact_id: str
    ) -> ApprovalRecord: ...
    def record_decision(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        rationale: str | None,
        edits: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
    ) -> ApprovalRecord: ...
    def latest_approval(self, run_id: str) -> ApprovalRecord | None: ...
    def list_approvals(self, run_id: str) -> list[ApprovalRecord]: ...
    def pending_approvals(self) -> list[ApprovalRecord]: ...
    def mark_escalated(self, approval_id: str) -> None: ...

    # audit
    def append_audit(self, event: AuditEvent) -> None: ...
    def list_audit(self, *, run_id: str | None = None, company_id: str | None = None) -> list[AuditEvent]: ...

    # KPI monitoring (PVC-120..124)
    def save_kpi_definitions(self, defs: list[KpiDefinition]) -> None: ...
    def list_kpi_definitions(self, company_id: str, active_only: bool = True) -> list[KpiDefinition]: ...
    def add_kpi_observation(self, obs: KpiObservation) -> None: ...
    def list_kpi_observations(self, company_id: str, kpi_id: str | None = None) -> list[KpiObservation]: ...
    def add_kpi_alert(self, alert: KpiAlert) -> None: ...
    def list_kpi_alerts(self, company_id: str) -> list[KpiAlert]: ...
    def add_notification(self, n: Notification) -> None: ...
    def list_notifications(self, company_id: str) -> list[Notification]: ...
    def claim_notification(self, n: Notification, owner: str) -> bool: ...
    def finish_notification(self, notification_id: str, owner: str, *, delivered: bool) -> None: ...

    # retention and deletion (PVC-144)
    def delete_company_data(self, company_id: str) -> dict[str, int]: ...


def _visible(company_id: str) -> bool:
    return company_id in security.allowed_companies()


class InMemoryRepository:
    """Thread-safe in-memory repository with the same scope semantics as the PostgreSQL implementation."""

    def __init__(self, evidence_store: EvidenceStore | None = None):
        import tempfile

        self.evidence_store: EvidenceStore = evidence_store or FileSystemEvidenceStore(
            tempfile.mkdtemp(prefix="pvc-evidence-")
        )
        self._lock = threading.RLock()
        self.companies: dict[str, CompanyProfile] = {}
        self.evidence: dict[str, EvidenceRef] = {}
        self.runs: dict[str, RunRecord] = {}
        self.findings: dict[str, Finding] = {}
        self.opportunities: dict[str, tuple[Opportunity, str]] = {}
        self.value_cases: dict[str, list[ValueCase]] = defaultdict(list)
        self.value_case_runs: dict[str, str] = {}
        self.priorities: dict[str, list[PriorityScore]] = {}
        self.plans: dict[str, PlanRecord] = {}
        self.approvals: dict[str, ApprovalRecord] = {}
        self.audit: list[AuditEvent] = []
        self.kpi_defs: dict[str, KpiDefinition] = {}
        self.kpi_obs: list[KpiObservation] = []
        self.kpi_alerts: list[KpiAlert] = []
        self.notifications: list[Notification] = []
        self.locks: dict[str, str] = {}
        self.lease_times: dict[str, datetime] = {}
        self.notification_claims: dict[str, tuple[str, datetime]] = {}
        self.investment_cases: dict[str, InvestmentCase] = {}
        self.case_revisions: dict[str, CaseRevision] = {}
        self.case_reviews: dict[str, CaseReview] = {}
        self.case_close_baselines: dict[str, CloseBaseline] = {}
        self.case_observations: dict[str, Observation] = {}
        self.case_attributions: dict[str, Attribution] = {}
        self.case_execution_events: dict[str, ExecutionEvent] = {}
        self.private_processing_grants: dict[str, GrantEvent] = {}
        self.private_intakes: dict[str, PrivateIntake] = {}
        self.private_sources: dict[str, bytes] = {}
        self.private_intake_reviews: dict[str, FinanceReview] = {}
        self.private_plan_reviews: dict[str, PrivatePlanReview] = {}
        self.private_counterfactuals: dict[str, PrivateCounterfactual] = {}
        self.private_counterfactual_reviews: dict[str, CounterfactualReview] = {}
        self.private_observations: dict[str, PrivateObservation] = {}
        self.private_execution_events: dict[str, PrivateExecutionEvent] = {}
        self.private_attributions: dict[str, private_attribution.PrivateAttribution] = {}
        self.private_attribution_reviews: dict[str, private_attribution.AttributionReview] = {}
        self.private_baselines: dict[str, PrivateBaseline] = {}
        self.private_capacity_plans: dict[str, PrivateCapacityRevision] = {}
        self.private_underwriting: dict[str, PrivateUnderwritingRevision] = {}
        self.private_financial_snapshots: dict[str, PrivateFinancialSnapshot] = {}

    def private_attribution_review_packet(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> dict[str, Any]:
        principal = require_grant_reader(company_id)
        with self.approval_transaction():
            proposal = self._private_attribution(company_id, revision_id)
            observation = self._private_observation(company_id, proposal.request.observation_id)
            counterfactual = self._private_counterfactual(company_id, observation.request.counterfactual_revision_id)
            actual = next(
                (
                    row
                    for row in self.list_private_financial_snapshots(company_id, proposal.case_key)
                    if row.snapshot_id == observation.request.actual_snapshot_id
                ),
                None,
            )
            if actual is None:
                raise NotFound(observation.request.actual_snapshot_id)
            baseline, plan = self._private_execution_context(company_id, proposal.baseline_id)
            events = self.list_private_execution_events(company_id, proposal.baseline_id)
            reviews = self.list_private_attribution_reviews(company_id, revision_id)
            head = private_attribution.attribution_review_head(proposal, reviews)
            proposal_head = self.list_private_attributions(company_id, proposal.case_key, proposal.attribution_key)[-1]
            checks = {
                "baseline_supported": False,
                "observation_supported": False,
                "proposal_supported": False,
                "finance_acceptance_supported": False,
            }
            if environment_id:
                try:
                    baseline_status = self.private_baseline_status(company_id, baseline.baseline_id, environment_id)
                    checks["baseline_supported"] = bool(baseline_status["usable_for_comparison"])
                except (security.ScopeError, ValueError, NotFound):
                    pass
                try:
                    self.usable_private_observation(company_id, observation.observation_id, environment_id)
                    checks["observation_supported"] = True
                    self._current_private_attribution(company_id, revision_id, environment_id)
                    checks["proposal_supported"] = True
                    self.usable_private_attribution(company_id, revision_id, environment_id)
                    checks["finance_acceptance_supported"] = True
                except (security.ScopeError, ValueError, NotFound):
                    pass  # Historical receipts remain scoped reads, never current support.
            try:
                require_finance_reviewer(company_id)
                can_review = principal.subject != proposal.author
            except security.ScopeError:
                can_review = False
            execution = private_execution_view(baseline, plan, events, baseline_supported=checks["baseline_supported"])
            packet = {
                "classification": "permissioned_private",
                "origin": proposal.origin,
                "company_id": company_id,
                "company_name": self.get_company(company_id).name,
                "case_key": proposal.case_key,
                "currency": proposal.currency,
                "unit_scale": 1,
                "generated_at": private_review.packet_timestamp(),
                "proposal": proposal.model_dump(mode="json"),
                "observation": observation.model_dump(mode="json"),
                "counterfactual": counterfactual.model_dump(mode="json"),
                "actual_snapshot": actual.model_dump(mode="json"),
                "baseline": baseline.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "execution": execution,
                "reviews": [r.model_dump(mode="json") for r in reviews],
                "current_proposal_revision_id": proposal_head.revision_id,
                "current_review_sha256": head.content_sha256 if head else None,
                "execution_head_sha256": events[-1].content_sha256 if events else None,
                "checks": checks,
                "viewer": principal.subject,
                "can_record_substantive_review": can_review and checks["proposal_supported"],
                "can_withdraw_review": can_review and head is not None and head.request.decision == "accept",
                "causal_impact_proven": False,
                "delivery_costs_reconciled_to_ledger": False,
            }
            packet["packet_sha256"] = private_review.packet_fingerprint(packet)
            return packet

    def private_review_index(self, company_id: str) -> list[dict[str, Any]]:
        require_grant_reader(company_id)
        with self.approval_transaction():
            company = self.get_company(company_id)
            heads: dict[tuple[str, str], private_attribution.PrivateAttribution] = {}
            for row in self._private_attribution_records(company_id):
                key = (row.case_key, row.attribution_key)
                if key not in heads or row.sequence > heads[key].sequence:
                    heads[key] = row
            cards = []
            for row in sorted(heads.values(), key=lambda r: r.recorded_at, reverse=True):
                head = private_attribution.attribution_review_head(
                    row, self.list_private_attribution_reviews(company_id, row.revision_id)
                )
                cards.append(
                    dict(
                        company_id=company_id,
                        company_name=company.name,
                        case_key=row.case_key,
                        revision_id=row.revision_id,
                        origin=row.origin,
                        first_month=row.first_month.isoformat(),
                        months=row.months,
                        decision=head.request.decision if head else None,
                    )
                )
            return cards

    def _private_attribution_records(self, company_id: str) -> list[private_attribution.PrivateAttribution]:
        require_grant_reader(company_id)
        with self._lock:
            return [
                private_attribution.PrivateAttribution.model_validate(r.model_dump(mode="json"))
                for r in self.private_attributions.values()
                if r.company_id == company_id
            ]

    def _private_attribution_review_records(
        self, company_id: str, revision_id: str
    ) -> list[private_attribution.AttributionReview]:
        require_grant_reader(company_id)
        with self._lock:
            return sorted(
                (
                    private_attribution.AttributionReview.model_validate(r.model_dump(mode="json"))
                    for r in self.private_attribution_reviews.values()
                    if r.company_id == company_id and r.attribution_revision_id == revision_id
                ),
                key=lambda r: r.sequence,
            )

    def _save_private_attribution(self, record: private_attribution.PrivateAttribution) -> None:
        self.private_attributions[record.revision_id] = record

    def _save_private_attribution_review(
        self, record: private_attribution.AttributionReview, proposal: private_attribution.PrivateAttribution
    ) -> None:
        self.private_attribution_reviews[record.review_id] = record

    def _private_attribution(self, company_id: str, revision_id: str) -> private_attribution.PrivateAttribution:
        require_grant_reader(company_id)
        result = next((r for r in self._private_attribution_records(company_id) if r.revision_id == revision_id), None)
        if result is None:
            raise NotFound(revision_id)
        return private_attribution.PrivateAttribution.model_validate(result.model_dump(mode="json"))

    def list_private_attributions(
        self, company_id: str, case_key: str, key: str
    ) -> list[private_attribution.PrivateAttribution]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        validate_grant_key(key)
        self.get_company(company_id)
        return sorted(
            (
                r
                for r in self._private_attribution_records(company_id)
                if r.case_key == case_key and r.attribution_key == key
            ),
            key=lambda r: r.sequence,
        )

    def list_private_attribution_reviews(
        self, company_id: str, revision_id: str
    ) -> list[private_attribution.AttributionReview]:
        self._private_attribution(company_id, revision_id)
        return self._private_attribution_review_records(company_id, revision_id)

    def record_private_attribution(
        self,
        company_id: str,
        case_key: str,
        key: str,
        request: private_attribution.AttributionRequest,
        environment_id: str,
    ) -> private_attribution.PrivateAttribution:
        principal = require_intake_writer(company_id)
        request = private_attribution.AttributionRequest.model_validate(request.model_dump(mode="json"))
        with self.approval_transaction():
            revisions = self.list_private_attributions(company_id, case_key, key)
            retry = next((r for r in revisions if r.request.idempotency_key == request.idempotency_key), None)
            if retry:
                if retry.request != request or retry.author != principal.subject:
                    raise Conflict("Private attribution idempotency key belongs to another request or author")
                return retry
            previous = revisions[-1] if revisions else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private attribution history changed; reload its current head")
            observation = self.usable_private_observation(company_id, request.observation_id, environment_id)
            baseline, plan = self._private_execution_context(company_id, observation.baseline_id)
            events = self.list_private_execution_events(company_id, baseline.baseline_id)
            if request.expected_execution_head_sha256 != (events[-1].content_sha256 if events else None):
                raise Conflict("Private execution history changed; reload its current head")
            result = private_attribution.prepare_attribution(
                company_id, case_key, key, request, observation, baseline, plan, events, previous
            )
            self._save_private_attribution(result)
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_attribution",
                    event_type="private_attribution_revision",
                    actor=result.author,
                    created_at=result.recorded_at,
                    payload={
                        "revision_id": result.revision_id,
                        "sha256": result.content_sha256,
                        "observation_id": observation.observation_id,
                    },
                )
            )
            return result

    def _current_private_attribution(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> private_attribution.PrivateAttribution:
        result = self._private_attribution(company_id, revision_id)
        if (
            self.list_private_attributions(company_id, result.case_key, result.attribution_key)[-1].revision_id
            != revision_id
        ):
            raise ValueError("private attribution is superseded")
        observation = self.usable_private_observation(company_id, result.request.observation_id, environment_id)
        baseline, plan = self._private_execution_context(company_id, result.baseline_id)
        events = self.list_private_execution_events(company_id, result.baseline_id)
        private_attribution.verify_attribution(result, observation, baseline, plan, events)
        private_attribution.require_current_execution_support(result, observation, baseline, plan, events)
        return result

    def _check_private_attribution_reservations(self, proposal: private_attribution.PrivateAttribution) -> None:
        heads: dict[str, private_attribution.PrivateAttribution] = {}
        for candidate in self._private_attribution_records(proposal.company_id):
            if (candidate.case_key, candidate.baseline_id) != (proposal.case_key, proposal.baseline_id):
                continue
            previous = heads.get(candidate.attribution_key)
            if previous is None or candidate.sequence > previous.sequence:
                heads[candidate.attribution_key] = candidate
        accepted = []
        for candidate in heads.values():
            review = private_attribution.attribution_review_head(
                candidate, self.list_private_attribution_reviews(candidate.company_id, candidate.revision_id)
            )
            if review and review.request.decision == "accept":
                accepted.append(candidate)
        private_attribution.require_disjoint_accepted_windows(proposal, accepted)

    def review_private_attribution(
        self,
        company_id: str,
        revision_id: str,
        request: private_attribution.AttributionReviewRequest,
        environment_id: str,
    ) -> private_attribution.AttributionReview:
        principal = require_finance_reviewer(company_id)
        request = private_attribution.AttributionReviewRequest.model_validate(request.model_dump(mode="json"))
        with self.approval_transaction():
            proposal = self._private_attribution(company_id, revision_id)
            reviews = self.list_private_attribution_reviews(company_id, revision_id)
            retry = next((r for r in reviews if r.request.idempotency_key == request.idempotency_key), None)
            if retry:
                if retry.request != request or retry.author != principal.subject:
                    raise Conflict("Attribution review idempotency key belongs to another request or author")
                return retry
            previous = private_attribution.attribution_review_head(proposal, reviews)
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Attribution review history changed; reload its current head")
            events = self.list_private_execution_events(company_id, proposal.baseline_id)
            if request.expected_execution_head_sha256 != (events[-1].content_sha256 if events else None):
                raise Conflict("Private execution history changed; reload its current head")
            if request.decision != "withdraw":
                proposal = self._current_private_attribution(company_id, revision_id, environment_id)
            if request.decision == "accept":
                self._check_private_attribution_reservations(proposal)
            result = private_attribution.prepare_attribution_review(proposal, request, reviews)
            if events and events[-1].recorded_at > result.recorded_at:
                raise ValueError("attribution review predates its execution history")
            self._save_private_attribution_review(result, proposal)
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_attribution_review",
                    event_type="private_attribution_review",
                    actor=result.author,
                    created_at=result.recorded_at,
                    payload={
                        "review_id": result.review_id,
                        "sha256": result.content_sha256,
                        "revision_id": revision_id,
                    },
                )
            )
            return result

    def usable_private_attribution(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> tuple[private_attribution.PrivateAttribution, private_attribution.AttributionReview]:
        require_grant_reader(company_id)
        with self.approval_transaction():
            result = self._current_private_attribution(company_id, revision_id, environment_id)
            reviews = self.list_private_attribution_reviews(company_id, revision_id)
            review = private_attribution.attribution_review_head(result, reviews)
            if review is None or review.request.decision != "accept":
                raise ValueError("attribution requires current finance acceptance")
            observation = self.usable_private_observation(company_id, result.request.observation_id, environment_id)
            baseline, plan = self._private_execution_context(company_id, result.baseline_id)
            events = self.list_private_execution_events(company_id, result.baseline_id)
            private_attribution.verify_review_evidence(result, reviews, observation, baseline, plan, events)
            self._check_private_attribution_reservations(result)
            return result, review

    def _private_execution_context(
        self, company_id: str, baseline_id: str
    ) -> tuple[PrivateBaseline, PrivateCapacityRevision]:
        require_grant_reader(company_id)
        baseline = self.private_baselines.get(baseline_id)
        if baseline is None or baseline.company_id != company_id:
            raise NotFound(baseline_id)
        baseline = PrivateBaseline.model_validate(baseline.model_dump(mode="json"))
        return baseline, self._private_capacity_revision(company_id, baseline.request.capacity_revision_id)

    def list_private_execution_events(self, company_id: str, baseline_id: str) -> list[PrivateExecutionEvent]:
        self._private_execution_context(company_id, baseline_id)
        with self._lock:
            return sorted(
                (
                    e
                    for e in self.private_execution_events.values()
                    if e.company_id == company_id and e.baseline_id == baseline_id
                ),
                key=lambda e: e.sequence,
            )

    def record_private_execution(
        self, company_id: str, baseline_id: str, request: PrivateExecutionRequest, environment_id: str
    ) -> PrivateExecutionEvent:
        request = PrivateExecutionRequest.model_validate(request.model_dump(mode="json"))
        principal = require_private_execution_author(company_id, request)
        with self.approval_transaction():
            baseline, plan = self._private_execution_context(company_id, baseline_id)
            events = self.list_private_execution_events(company_id, baseline_id)
            replay = next((e for e in events if e.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private execution idempotency key belongs to another request or author")
                return replay
            previous = events[-1] if events else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private execution history changed; reload its current head")
            if not execution_reducing_support(request):
                view = self.private_baseline_status(company_id, baseline_id, environment_id)
                if not view["usable_for_comparison"]:
                    raise ValueError("private execution requires a currently supported baseline")
            result = prepare_private_execution(company_id, baseline, plan, request, events)
            self.private_execution_events[result.event_id] = result
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_execution",
                    event_type="private_execution_" + request.payload.kind,
                    actor=result.author,
                    created_at=result.recorded_at,
                    payload={
                        "event_id": result.event_id,
                        "baseline_id": baseline_id,
                        "sha256": result.content_sha256,
                        "kind": request.payload.kind,
                    },
                )
            )
            return result

    def private_execution_status(self, company_id: str, baseline_id: str, environment_id: str) -> dict[str, Any]:
        require_grant_reader(company_id)
        with self.approval_transaction():
            baseline, plan = self._private_execution_context(company_id, baseline_id)
            view = self.private_baseline_status(company_id, baseline_id, environment_id)
            return private_execution_view(
                baseline,
                plan,
                self.list_private_execution_events(company_id, baseline_id),
                baseline_supported=view["usable_for_comparison"],
            )

    def _private_counterfactual(self, company_id: str, record_id: str) -> PrivateCounterfactual:
        require_grant_reader(company_id)
        result = self.private_counterfactuals.get(record_id)
        if result is None or result.company_id != company_id:
            raise NotFound(record_id)
        return PrivateCounterfactual.model_validate(result.model_dump(mode="json"))

    def list_private_counterfactuals(self, company_id: str, case_key: str, key: str) -> list[PrivateCounterfactual]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        validate_grant_key(key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_counterfactuals.values()
                    if r.company_id == company_id and r.case_key == case_key and r.counterfactual_key == key
                ),
                key=lambda r: r.sequence,
            )

    def _private_observation(self, company_id: str, record_id: str) -> PrivateObservation:
        require_grant_reader(company_id)
        result = self.private_observations.get(record_id)
        if result is None or result.company_id != company_id:
            raise NotFound(record_id)
        return PrivateObservation.model_validate(result.model_dump(mode="json"))

    def list_private_observations(self, company_id: str, case_key: str, key: str) -> list[PrivateObservation]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        validate_grant_key(key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_observations.values()
                    if r.company_id == company_id and r.case_key == case_key and r.measurement_key == key
                ),
                key=lambda r: r.sequence,
            )

    def list_private_counterfactual_reviews(self, company_id: str, revision_id: str) -> list[CounterfactualReview]:
        self._private_counterfactual(company_id, revision_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_counterfactual_reviews.values()
                    if r.company_id == company_id and r.counterfactual_revision_id == revision_id
                ),
                key=lambda r: r.sequence,
            )

    def _private_measurement_baseline(
        self, company_id: str, baseline_id: str, environment_id: str
    ) -> tuple[PrivateBaseline, PrivateFinancialSnapshot]:
        view = self.private_baseline_status(company_id, baseline_id, environment_id)
        if not view["usable_for_comparison"]:
            raise ValueError("private comparison baseline is no longer currently supported")
        baseline = PrivateBaseline.model_validate(view["baseline"])
        anchor = next(
            (
                s
                for s in self.list_private_financial_snapshots(company_id, baseline.case_key)
                if s.content_sha256 == baseline.financial_snapshot_sha256
            ),
            None,
        )
        if anchor is None:
            raise NotFound(baseline.financial_snapshot_sha256)
        return baseline, anchor

    def record_private_counterfactual(
        self, company_id: str, case_key: str, key: str, request: CounterfactualRequest, environment_id: str
    ) -> PrivateCounterfactual:
        principal = require_intake_writer(company_id)
        request = CounterfactualRequest.model_validate(request.model_dump(mode="json"))
        with self.approval_transaction():
            revisions = self.list_private_counterfactuals(company_id, case_key, key)
            replay = next((r for r in revisions if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private counterfactual idempotency key belongs to another request or author")
                return replay
            previous = revisions[-1] if revisions else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private counterfactual history changed; reload its current head")
            baseline, anchor = self._private_measurement_baseline(company_id, request.baseline_id, environment_id)
            result = prepare_counterfactual(company_id, case_key, key, request, baseline, anchor, previous)
            self.private_counterfactuals[result.revision_id] = result
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_counterfactual",
                    event_type="private_counterfactual_revision",
                    actor=result.author,
                    created_at=result.recorded_at,
                    payload={
                        "revision_id": result.revision_id,
                        "sha256": result.content_sha256,
                        "baseline_id": baseline.baseline_id,
                    },
                )
            )
            return result

    def _current_private_counterfactual(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> PrivateCounterfactual:
        result = self._private_counterfactual(company_id, revision_id)
        if (
            self.list_private_counterfactuals(company_id, result.case_key, result.counterfactual_key)[-1].revision_id
            != revision_id
        ):
            raise ValueError("private counterfactual is superseded")
        baseline, anchor = self._private_measurement_baseline(company_id, result.request.baseline_id, environment_id)
        verify_counterfactual(result, baseline, anchor)
        return result

    def review_private_counterfactual(
        self, company_id: str, revision_id: str, request: CounterfactualReviewRequest, environment_id: str
    ) -> CounterfactualReview:
        principal = require_finance_reviewer(company_id)
        request = CounterfactualReviewRequest.model_validate(request.model_dump(mode="json"))
        with self.approval_transaction():
            proposal = self._private_counterfactual(company_id, revision_id)
            reviews = self.list_private_counterfactual_reviews(company_id, revision_id)
            replay = next((r for r in reviews if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Counterfactual review idempotency key belongs to another request or author")
                return replay
            previous = counterfactual_review_head(proposal, reviews)
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Counterfactual review history changed; reload its current head")
            if request.decision != "withdraw":
                proposal = self._current_private_counterfactual(company_id, revision_id, environment_id)
            result = prepare_counterfactual_review(proposal, request, reviews)
            self.private_counterfactual_reviews[result.review_id] = result
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_counterfactual_review",
                    event_type="private_counterfactual_review",
                    actor=result.author,
                    created_at=result.recorded_at,
                    payload={
                        "review_id": result.review_id,
                        "sha256": result.content_sha256,
                        "revision_id": revision_id,
                    },
                )
            )
            return result

    def usable_private_counterfactual(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> tuple[PrivateCounterfactual, CounterfactualReview]:
        require_grant_reader(company_id)
        with self.approval_transaction():
            result = self._current_private_counterfactual(company_id, revision_id, environment_id)
            review = counterfactual_review_head(
                result, self.list_private_counterfactual_reviews(company_id, revision_id)
            )
            if review is None or review.request.decision != "accept":
                raise ValueError("counterfactual requires current finance acceptance")
            return result, review

    def record_private_observation(
        self, company_id: str, case_key: str, key: str, request: PrivateObservationRequest, environment_id: str
    ) -> PrivateObservation:
        principal = require_snapshot_writer(company_id)
        request = PrivateObservationRequest.model_validate(request.model_dump(mode="json"))
        with self.approval_transaction():
            observations = self.list_private_observations(company_id, case_key, key)
            replay = next((r for r in observations if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private observation idempotency key belongs to another request or author")
                return replay
            previous = observations[-1] if observations else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private observation history changed; reload its current head")
            proposal, review = self.usable_private_counterfactual(
                company_id, request.counterfactual_revision_id, environment_id
            )
            baseline, anchor = self._private_measurement_baseline(
                company_id, proposal.request.baseline_id, environment_id
            )
            actual = self.usable_private_financial_snapshot(company_id, request.actual_snapshot_id, environment_id)
            result = prepare_private_observation(
                company_id, case_key, key, request, proposal, review, baseline, actual, anchor, previous
            )
            self.private_observations[result.observation_id] = result
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_observation",
                    event_type="private_observation",
                    actor=result.author,
                    created_at=result.recorded_at,
                    payload={
                        "observation_id": result.observation_id,
                        "sha256": result.content_sha256,
                        "counterfactual_revision_id": proposal.revision_id,
                        "actual_snapshot_id": actual.snapshot_id,
                    },
                )
            )
            return result

    def usable_private_observation(
        self, company_id: str, observation_id: str, environment_id: str
    ) -> PrivateObservation:
        require_grant_reader(company_id)
        with self.approval_transaction():
            result = self._private_observation(company_id, observation_id)
            if (
                self.list_private_observations(company_id, result.case_key, result.measurement_key)[-1].observation_id
                != observation_id
            ):
                raise ValueError("private observation is superseded")
            proposal, review = self.usable_private_counterfactual(
                company_id, result.request.counterfactual_revision_id, environment_id
            )
            baseline, anchor = self._private_measurement_baseline(
                company_id, proposal.request.baseline_id, environment_id
            )
            actual = self.usable_private_financial_snapshot(
                company_id, result.request.actual_snapshot_id, environment_id
            )
            verify_observation(result, proposal, review, baseline, actual, anchor)
            return result

    def _private_capacity_revision(self, company_id: str, revision_id: str) -> PrivateCapacityRevision:
        require_grant_reader(company_id)
        revision = self.private_capacity_plans.get(revision_id)
        if revision is None or revision.company_id != company_id:
            raise NotFound(revision_id)
        return revision

    def list_private_plan_reviews(self, company_id: str, revision_id: str) -> list[PrivatePlanReview]:
        self._private_capacity_revision(company_id, revision_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_plan_reviews.values()
                    if r.company_id == company_id and r.capacity_revision_id == revision_id
                ),
                key=lambda r: (r.review_kind, r.sequence),
            )

    def review_private_capacity(
        self, company_id: str, revision_id: str, request: PlanReviewRequest, environment_id: str
    ) -> PrivatePlanReview:
        principal = require_private_plan_reviewer(company_id, request.review_kind)
        with self.approval_transaction():
            plan = self._private_capacity_revision(company_id, revision_id)
            reviews = self.list_private_plan_reviews(company_id, revision_id)
            replay = next(
                (
                    r
                    for r in reviews
                    if r.review_kind == request.review_kind and r.request.idempotency_key == request.idempotency_key
                ),
                None,
            )
            if replay:
                if replay.request != request or replay.actor != principal.subject:
                    raise Conflict("Private plan review idempotency key belongs to another request or author")
                return replay
            previous = private_review_heads(plan, reviews).get(request.review_kind)
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private plan review history changed; reload its current role head")
            if request.decision != "withdraw":
                plan = self.usable_private_capacity_plan(company_id, revision_id, environment_id)
            review = prepare_private_plan_review(plan, request, reviews)
            self.private_plan_reviews[review.review_id] = review
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_plan_review",
                    event_type="private_plan_review",
                    actor=review.actor,
                    created_at=review.recorded_at,
                    payload={
                        "review_id": review.review_id,
                        "sha256": review.content_sha256,
                        "capacity_revision_id": revision_id,
                        "review_kind": review.review_kind,
                    },
                )
            )
            return review

    def list_private_baselines(self, company_id: str, case_key: str) -> list[PrivateBaseline]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (r for r in self.private_baselines.values() if r.company_id == company_id and r.case_key == case_key),
                key=lambda r: r.sequence,
            )

    def freeze_private_baseline(
        self, company_id: str, case_key: str, request: BaselineRequest, environment_id: str
    ) -> PrivateBaseline:
        principal = require_private_baseline_author(company_id)
        with self.approval_transaction():
            baselines = self.list_private_baselines(company_id, case_key)
            replay = next((b for b in baselines if b.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private baseline idempotency key belongs to another request or author")
                return replay
            previous = baselines[-1] if baselines else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private baseline history changed; reload its current head")
            plan = self.usable_private_capacity_plan(company_id, request.capacity_revision_id, environment_id)
            baseline = prepare_private_baseline(
                company_id,
                case_key,
                request,
                plan,
                self.list_private_plan_reviews(company_id, plan.revision_id),
                previous,
            )
            self.private_baselines[baseline.baseline_id] = baseline
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_baseline",
                    event_type="private_baseline_designation",
                    actor=baseline.author,
                    created_at=baseline.recorded_at,
                    payload={
                        "baseline_id": baseline.baseline_id,
                        "sha256": baseline.content_sha256,
                        "capacity_revision_id": plan.revision_id,
                    },
                )
            )
            return baseline

    def private_baseline_status(self, company_id: str, baseline_id: str, environment_id: str) -> dict[str, Any]:
        require_grant_reader(company_id)
        with self.approval_transaction():
            baseline = self.private_baselines.get(baseline_id)
            if baseline is None or baseline.company_id != company_id:
                raise NotFound(baseline_id)
            plan = self._private_capacity_revision(company_id, baseline.request.capacity_revision_id)
            underwriting = next(
                (
                    r
                    for r in self.list_private_underwriting(company_id, plan.case_key)
                    if r.revision_id == plan.request.underwriting_revision_id
                ),
                None,
            )
            if underwriting is None:
                raise NotFound(plan.request.underwriting_revision_id)
            financials = next(
                (
                    s
                    for s in self.list_private_financial_snapshots(company_id, plan.case_key)
                    if s.snapshot_id == underwriting.request.inputs.financial_snapshot_id
                ),
                None,
            )
            if financials is None:
                raise NotFound(underwriting.request.inputs.financial_snapshot_id)
            # Historical comparison needs current processing permission, but not
            # current-source acceptance. Reproduce originals before reporting support.
            raw = self.private_intake_source(
                company_id, financials.request.intake_id, environment_id, accepted_only=False
            )
            verify_private_financial_snapshot(
                financials, self._private_intake(company_id, financials.request.intake_id), raw
            )
            verify_private_capacity(plan, underwriting, financials)
            try:
                self.usable_private_financial_snapshot(company_id, financials.snapshot_id, environment_id)
                source_current = True
            except ValueError:
                source_current = False
            return private_baseline_view(
                baseline,
                plan,
                self.list_private_plan_reviews(company_id, plan.revision_id),
                self.list_private_baselines(company_id, baseline.case_key),
                source_current=source_current,
            )

    def list_private_capacity_plans(self, company_id: str, case_key: str) -> list[PrivateCapacityRevision]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_capacity_plans.values()
                    if r.company_id == company_id and r.case_key == case_key
                ),
                key=lambda r: r.sequence,
            )

    def record_private_capacity_plan(
        self, company_id: str, case_key: str, request: CapacityPlanRequest, environment_id: str
    ) -> PrivateCapacityRevision:
        principal = require_intake_writer(company_id)
        with self.approval_transaction():
            revisions = self.list_private_capacity_plans(company_id, case_key)
            replay = next((r for r in revisions if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private capacity idempotency key belongs to another request or author")
                return replay
            previous = revisions[-1] if revisions else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private capacity history changed; reload its current head")
            underwriting = self.usable_private_underwriting(
                company_id, request.underwriting_revision_id, environment_id
            )
            financials = self.usable_private_financial_snapshot(
                company_id,
                underwriting.request.inputs.financial_snapshot_id,
                environment_id,
            )
            revision = prepare_private_capacity(company_id, case_key, request, underwriting, financials, previous)
            self.private_capacity_plans[revision.revision_id] = revision
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_capacity",
                    event_type="private_capacity_revision",
                    actor=revision.author,
                    created_at=revision.recorded_at,
                    payload={
                        "revision_id": revision.revision_id,
                        "sha256": revision.content_sha256,
                        "underwriting_revision_id": underwriting.revision_id,
                    },
                )
            )
            return revision

    def usable_private_capacity_plan(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> PrivateCapacityRevision:
        require_grant_reader(company_id)
        with self.approval_transaction():
            revision = self.private_capacity_plans.get(revision_id)
            if revision is None or revision.company_id != company_id:
                raise NotFound(revision_id)
            if self.list_private_capacity_plans(company_id, revision.case_key)[-1].revision_id != revision_id:
                raise ValueError("private capacity revision is superseded")
            underwriting = self.usable_private_underwriting(
                company_id,
                revision.request.underwriting_revision_id,
                environment_id,
            )
            financials = self.usable_private_financial_snapshot(
                company_id,
                underwriting.request.inputs.financial_snapshot_id,
                environment_id,
            )
            verify_private_capacity(revision, underwriting, financials)
            return revision

    def list_private_underwriting(self, company_id: str, case_key: str) -> list[PrivateUnderwritingRevision]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_underwriting.values()
                    if r.company_id == company_id and r.case_key == case_key
                ),
                key=lambda r: r.sequence,
            )

    def record_private_underwriting(
        self, company_id: str, case_key: str, request: UnderwritingRequest, environment_id: str
    ) -> PrivateUnderwritingRevision:
        principal = require_intake_writer(company_id)
        with self.approval_transaction():
            revisions = self.list_private_underwriting(company_id, case_key)
            replay = next((r for r in revisions if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private underwriting idempotency key belongs to another request or author")
                return replay
            previous = revisions[-1] if revisions else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private underwriting history changed; reload its current head")
            snapshot = self.usable_private_financial_snapshot(
                company_id, request.inputs.financial_snapshot_id, environment_id
            )
            revision = prepare_private_underwriting(company_id, case_key, request, snapshot, previous)
            self.private_underwriting[revision.revision_id] = revision
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_underwriting",
                    event_type="private_underwriting_revision",
                    actor=revision.author,
                    created_at=revision.recorded_at,
                    payload={
                        "revision_id": revision.revision_id,
                        "sha256": revision.content_sha256,
                        "snapshot_id": snapshot.snapshot_id,
                    },
                )
            )
            return revision

    def usable_private_underwriting(
        self, company_id: str, revision_id: str, environment_id: str
    ) -> PrivateUnderwritingRevision:
        require_grant_reader(company_id)
        with self.approval_transaction():
            revision = self.private_underwriting.get(revision_id)
            if revision is None or revision.company_id != company_id:
                raise NotFound(revision_id)
            if self.list_private_underwriting(company_id, revision.case_key)[-1].revision_id != revision_id:
                raise ValueError("private underwriting revision is superseded")
            snapshot = self.usable_private_financial_snapshot(
                company_id,
                revision.request.inputs.financial_snapshot_id,
                environment_id,
            )
            verify_private_underwriting(revision, snapshot)
            return revision

    def list_private_financial_snapshots(self, company_id: str, case_key: str) -> list[PrivateFinancialSnapshot]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_financial_snapshots.values()
                    if r.company_id == company_id and r.case_key == case_key
                ),
                key=lambda r: r.sequence,
            )

    def record_private_financial_snapshot(
        self, company_id: str, case_key: str, request: FinancialSnapshotRequest, environment_id: str
    ) -> PrivateFinancialSnapshot:
        principal = require_snapshot_writer(company_id)
        with self.approval_transaction():
            snapshots = self.list_private_financial_snapshots(company_id, case_key)
            replay = next((r for r in snapshots if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.author != principal.subject:
                    raise Conflict("Private financial idempotency key belongs to another request or author")
                return replay
            previous = snapshots[-1] if snapshots else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private financial history changed; reload its current head")
            record = self._private_intake(company_id, request.intake_id)
            snapshot = prepare_snapshot(
                company_id,
                case_key,
                request,
                record,
                self.private_sources[record.intake_id],
                self.list_private_grants(company_id, record.request.grant_key),
                self.list_private_finance_reviews(company_id, record.intake_id),
                self.list_private_intakes(company_id, record.dataset_key)[-1],
                previous,
                environment_id,
            )
            self.private_financial_snapshots[snapshot.snapshot_id] = snapshot
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_financials",
                    event_type="private_financial_snapshot",
                    actor=snapshot.author,
                    created_at=snapshot.recorded_at,
                    payload={
                        "snapshot_id": snapshot.snapshot_id,
                        "sha256": snapshot.content_sha256,
                        "intake_id": record.intake_id,
                    },
                )
            )
            return snapshot

    def usable_private_financial_snapshot(
        self, company_id: str, snapshot_id: str, environment_id: str
    ) -> PrivateFinancialSnapshot:
        require_grant_reader(company_id)
        with self.approval_transaction():
            snapshot = self.private_financial_snapshots.get(snapshot_id)
            if snapshot is None or snapshot.company_id != company_id:
                raise NotFound(snapshot_id)
            record = self._private_intake(company_id, snapshot.request.intake_id)
            require_current_snapshot(
                snapshot,
                record,
                self.private_sources[record.intake_id],
                self.list_private_grants(company_id, record.request.grant_key),
                self.list_private_finance_reviews(company_id, record.intake_id),
                self.list_private_intakes(company_id, record.dataset_key)[-1],
                environment_id,
            )
            return snapshot

    def list_private_intakes(self, company_id: str, dataset_key: str) -> list[PrivateIntake]:
        require_grant_reader(company_id)
        validate_grant_key(dataset_key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    r
                    for r in self.private_intakes.values()
                    if r.company_id == company_id and r.dataset_key == dataset_key
                ),
                key=lambda r: r.sequence,
            )

    def _private_intake(self, company_id: str, intake_id: str) -> PrivateIntake:
        require_grant_reader(company_id)
        record = self.private_intakes.get(intake_id)
        if record is None or record.company_id != company_id:
            raise NotFound(intake_id)
        return record

    def list_private_finance_reviews(self, company_id: str, intake_id: str) -> list[FinanceReview]:
        with self._lock:
            self._private_intake(company_id, intake_id)
            return sorted(
                (
                    r
                    for r in self.private_intake_reviews.values()
                    if r.company_id == company_id and r.intake_id == intake_id
                ),
                key=lambda r: r.sequence,
            )

    def record_private_intake(
        self, company_id: str, dataset_key: str, request: IntakeRequest, raw: bytes, environment_id: str
    ) -> PrivateIntake:
        principal = require_intake_writer(company_id)
        with self.approval_transaction():
            records = self.list_private_intakes(company_id, dataset_key)
            replay = next((r for r in records if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if (
                    replay.request != request
                    or replay.actor != principal.subject
                    or replay.source_sha256 != hashlib.sha256(raw).hexdigest()
                ):
                    raise Conflict("Private intake idempotency key belongs to another request, source or actor")
                return replay
            previous = records[-1] if records else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private dataset changed; reload its current head")
            record = prepare_intake(
                company_id,
                dataset_key,
                request,
                raw,
                self.list_private_grants(company_id, request.grant_key),
                previous,
                environment_id,
            )
            self.private_intakes[record.intake_id] = record
            self.private_sources[record.intake_id] = raw
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_intake",
                    event_type="private_source_recorded",
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={
                        "intake_id": record.intake_id,
                        "sha256": record.content_sha256,
                        "status": record.preflight.status,
                    },
                )
            )
            return record

    def review_private_intake(
        self, company_id: str, intake_id: str, request: FinanceReviewRequest, environment_id: str
    ) -> FinanceReview:
        principal = require_finance_reviewer(company_id)
        with self.approval_transaction():
            record = self._private_intake(company_id, intake_id)
            reviews = self.list_private_finance_reviews(company_id, intake_id)
            replay = next((r for r in reviews if r.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.actor != principal.subject:
                    raise Conflict("Private review idempotency key belongs to another request or actor")
                return replay
            if self.list_private_intakes(company_id, record.dataset_key)[-1].intake_id != intake_id:
                raise Conflict("Private intake was superseded; review its replacement")
            previous = reviews[-1] if reviews else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private finance review changed; reload its current head")
            review = prepare_private_review(
                record,
                self.private_sources[intake_id],
                request,
                self.list_private_grants(company_id, record.request.grant_key),
                previous,
                environment_id,
            )
            self.private_intake_reviews[review.review_id] = review
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_intake",
                    event_type="private_finance_" + request.decision,
                    actor=review.actor,
                    created_at=review.recorded_at,
                    payload={"intake_id": intake_id, "review_id": review.review_id, "sha256": review.content_sha256},
                )
            )
            return review

    def private_intake_source(
        self, company_id: str, intake_id: str, environment_id: str, *, accepted_only: bool = False
    ) -> bytes:
        with self.approval_transaction():
            record = self._private_intake(company_id, intake_id)
            return authorize_source(
                record,
                self.private_sources[intake_id],
                self.list_private_grants(company_id, record.request.grant_key),
                self.list_private_finance_reviews(company_id, intake_id),
                self.list_private_intakes(company_id, record.dataset_key)[-1],
                environment_id,
                accepted_only=accepted_only,
            )

    def list_private_grants(self, company_id: str, grant_key: str) -> list[GrantEvent]:
        require_grant_reader(company_id)
        validate_grant_key(grant_key)
        self.get_company(company_id)
        with self._lock:
            return sorted(
                (
                    e
                    for e in self.private_processing_grants.values()
                    if e.company_id == company_id and e.grant_key == grant_key
                ),
                key=lambda e: e.sequence,
            )

    def record_private_grant(self, company_id: str, grant_key: str, request: GrantRequest) -> GrantEvent:
        principal = require_grant_author(company_id)
        with self.approval_transaction():
            events = self.list_private_grants(company_id, grant_key)
            replay = next((e for e in events if e.request.idempotency_key == request.idempotency_key), None)
            if replay:
                if replay.request != request or replay.actor != principal.subject:
                    raise Conflict("Private grant idempotency key belongs to another request or actor")
                return replay
            previous = events[-1] if events else None
            if request.expected_previous_sha256 != (previous.content_sha256 if previous else None):
                raise Conflict("Private grant changed; reload its current head")
            record = prepare_grant_event(company_id, grant_key, request, previous)
            self.private_processing_grants[record.event_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="private_intake",
                    event_type="private_processing_" + request.action,
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={"grant_key": grant_key, "event_id": record.event_id, "sha256": record.content_sha256},
                )
            )
            return record

    # Research-case review never routes through operating-plan approval or KPI activation.
    def create_investment_case(self, company_id: str, case_id: str, label: str, currency: str) -> InvestmentCase:
        with self.approval_transaction():
            self.get_company(company_id)
            record = new_case(company_id, case_id, label, currency)
            if case_id in self.investment_cases:
                raise Conflict("Case identity already exists")
            self.investment_cases[case_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=company_id,
                    step="case_review",
                    event_type="case_created",
                    actor=record.created_by,
                    created_at=record.created_at,
                    payload={"case_id": case_id},
                )
            )
            return record

    def get_investment_case(self, case_id: str) -> InvestmentCase:
        record = self.investment_cases.get(case_id)
        if record is None or not _visible(record.company_id):
            raise NotFound(case_id)
        return record

    def get_case_revision(self, revision_id: str) -> CaseRevision:
        record = self.case_revisions.get(revision_id)
        if record is None or not _visible(record.company_id):
            raise NotFound(revision_id)
        return record

    def list_case_revisions(self, case_id: str) -> list[CaseRevision]:
        self.get_investment_case(case_id)
        return sorted((r for r in self.case_revisions.values() if r.case_id == case_id), key=lambda r: r.sequence)

    def append_case_revision(self, case_id: str, expected_parent: str | None, draft: RevisionDraft) -> CaseRevision:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            if expected_parent != case.current_revision_id:
                raise Conflict("Case changed; reload the current revision before appending")
            parent = self.get_case_revision(expected_parent) if expected_parent else None
            record = prepare_revision(case, draft, parent)
            self.case_revisions[record.revision_id] = record
            self.investment_cases[case_id] = case.model_copy(
                update={
                    "version": record.sequence,
                    "current_revision_id": record.revision_id,
                    "original_revision_id": case.original_revision_id or record.revision_id,
                }
            )
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=case.company_id,
                    step="case_review",
                    event_type="case_revision_appended",
                    actor=record.author,
                    created_at=record.recorded_at,
                    payload={"case_id": case_id, "revision_id": record.revision_id, "sha256": record.content_sha256},
                )
            )
            return record

    def list_close_baselines(self, case_id: str) -> list[CloseBaseline]:
        self.get_investment_case(case_id)
        return sorted(
            (b for b in self.case_close_baselines.values() if b.case_id == case_id),
            key=lambda b: (b.request.mode, b.sequence),
        )

    def list_execution_events(self, case_id: str) -> list[ExecutionEvent]:
        self.get_investment_case(case_id)
        return sorted(
            (r for r in self.case_execution_events.values() if r.case_id == case_id),
            key=lambda r: (r.recorded_at, r.event_id),
        )

    def record_execution_event(self, case_id: str, request: ExecutionRequest) -> ExecutionEvent:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            principal = writer(case.company_id)
            events = self.list_execution_events(case_id)
            replay = next((e for e in events if e.request.ingestion_key == request.ingestion_key), None)
            if replay is not None:
                if replay.request != request or replay.actor != principal.subject:
                    raise Conflict("Execution ingestion key belongs to different content or author")
                return replay
            baselines = self.list_close_baselines(case_id)
            baseline = next((b for b in baselines if b.baseline_id == request.baseline_id), None)
            if baseline is None:
                raise NotFound(request.baseline_id)
            chain = [
                e
                for e in events
                if e.request.baseline_id == request.baseline_id and e.stream_key == stream_key(request.payload)
            ]
            previous = max(chain, key=lambda e: e.sequence) if chain else None
            if request.expected_previous_id != (previous.event_id if previous else None):
                raise Conflict("Execution stream changed; bind its latest receipt")
            record = prepare_execution(
                case,
                baseline,
                self.get_case_revision(baseline.request.revision_id),
                self.list_case_reviews(case_id),
                baselines,
                events,
                self.list_case_observations(case_id),
                self.list_case_attributions(case_id),
                request,
                previous,
            )
            self.case_execution_events[record.event_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=case.company_id,
                    step="case_execution",
                    event_type="execution_" + request.payload.kind + "_recorded",
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={
                        "case_id": case_id,
                        "event_id": record.event_id,
                        "sha256": record.content_sha256,
                        "previous_id": request.expected_previous_id,
                        "mode": request.mode,
                    },
                )
            )
            return record

    def case_execution(self, case_id: str, baseline_id: str, as_of: date) -> dict[str, Any]:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            baselines = self.list_close_baselines(case_id)
            baseline = next((b for b in baselines if b.baseline_id == baseline_id), None)
            if baseline is None:
                raise NotFound(baseline_id)
            return execution_report(
                case,
                baseline,
                self.get_case_revision(baseline.request.revision_id),
                self.list_case_reviews(case_id),
                baselines,
                self.list_execution_events(case_id),
                self.list_case_observations(case_id),
                self.list_case_attributions(case_id),
                as_of,
            )

    def list_case_observations(self, case_id: str) -> list[Observation]:
        self.get_investment_case(case_id)
        return sorted(
            (r for r in self.case_observations.values() if r.case_id == case_id),
            key=lambda r: (r.recorded_at, r.observation_id),
        )

    def list_case_attributions(self, case_id: str) -> list[Attribution]:
        self.get_investment_case(case_id)
        return sorted(
            (r for r in self.case_attributions.values() if r.case_id == case_id),
            key=lambda r: (r.recorded_at, r.attribution_id),
        )

    def record_case_observation(self, case_id: str, request: ObservationRequest) -> Observation:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            principal = writer(case.company_id)
            existing = self.list_case_observations(case_id)
            replay = next((r for r in existing if r.request.ingestion_key == request.ingestion_key), None)
            if replay is not None:
                if replay.request != request or replay.actor != principal.subject:
                    raise Conflict("Ingestion key already belongs to another request or author")
                return replay
            baselines = self.list_close_baselines(case_id)
            baseline = next((b for b in baselines if b.baseline_id == request.baseline_id), None)
            if baseline is None:
                raise NotFound(request.baseline_id)
            chain = [
                r
                for r in existing
                if r.request.baseline_id == request.baseline_id and r.request.observed.start == request.observed.start
            ]
            previous = max(chain, key=lambda r: r.sequence) if chain else None
            if request.expected_previous_id != (previous.observation_id if previous else None):
                raise Conflict("Observation changed; explicitly bind the latest snapshot")
            record = prepare_observation(
                case,
                baseline,
                self.get_case_revision(baseline.request.revision_id),
                self.list_case_reviews(case_id),
                baselines,
                request,
                previous,
            )
            self.case_observations[record.observation_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=case.company_id,
                    step="case_realization",
                    event_type="case_observation_recorded",
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={
                        "case_id": case_id,
                        "observation_id": record.observation_id,
                        "sha256": record.content_sha256,
                        "previous_id": request.expected_previous_id,
                    },
                )
            )
            return record

    def record_case_attribution(self, case_id: str, request: AttributionRequest) -> Attribution:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            principal = writer(case.company_id)
            existing = self.list_case_attributions(case_id)
            replay = next((r for r in existing if r.request.ingestion_key == request.ingestion_key), None)
            if replay is not None:
                if replay.request != request or replay.actor != principal.subject:
                    raise Conflict("Ingestion key already belongs to another request or author")
                return replay
            baselines = self.list_close_baselines(case_id)
            observations = self.list_case_observations(case_id)
            observation = next((o for o in observations if o.observation_id == request.observation_id), None)
            if observation is None:
                raise NotFound(request.observation_id)
            if any(o.request.expected_previous_id == observation.observation_id for o in observations):
                raise Conflict("Corrected observations require fresh attribution against the new snapshot")
            baseline = next(b for b in baselines if b.baseline_id == observation.request.baseline_id)
            chain = [r for r in existing if r.request.observation_id == request.observation_id]
            previous = max(chain, key=lambda r: r.sequence) if chain else None
            if request.expected_previous_id != (previous.attribution_id if previous else None):
                raise Conflict("Attribution changed; explicitly bind the latest claims")
            record = prepare_attribution(
                case,
                baseline,
                self.get_case_revision(baseline.request.revision_id),
                self.list_case_reviews(case_id),
                baselines,
                observation,
                request,
                previous,
            )
            self.case_attributions[record.attribution_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=case.company_id,
                    step="case_realization",
                    event_type="case_attribution_recorded",
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={
                        "case_id": case_id,
                        "attribution_id": record.attribution_id,
                        "sha256": record.content_sha256,
                        "previous_id": request.expected_previous_id,
                    },
                )
            )
            return record

    def case_realization(self, case_id: str, baseline_id: str) -> dict[str, Any]:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            baselines = self.list_close_baselines(case_id)
            baseline = next((b for b in baselines if b.baseline_id == baseline_id), None)
            if baseline is None:
                raise NotFound(baseline_id)
            return realization_report(
                case,
                baseline,
                self.list_case_revisions(case_id),
                self.list_case_reviews(case_id),
                baselines,
                self.list_case_observations(case_id),
                self.list_case_attributions(case_id),
            )

    def designate_close_baseline(self, case_id: str, request: CloseBaselineRequest) -> CloseBaseline:
        with self.approval_transaction():
            case = self.get_investment_case(case_id)
            revision = self.get_case_revision(request.revision_id)
            existing = [b for b in self.list_close_baselines(case_id) if b.request.mode == request.mode]
            previous = existing[-1] if existing else None
            if request.expected_previous_id != (previous.baseline_id if previous else None):
                raise Conflict("Close baseline changed; bind the latest designation explicitly")
            record = prepare_close_baseline(case, revision, self.list_case_reviews(case_id), request, previous)
            self.case_close_baselines[record.baseline_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=case.company_id,
                    step="case_review",
                    event_type="close_baseline_designated",
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={
                        "case_id": case_id,
                        "baseline_id": record.baseline_id,
                        "revision_id": request.revision_id,
                        "review_id": request.review_id,
                        "mode": request.mode,
                        "sha256": record.content_sha256,
                    },
                )
            )
            return record

    def list_case_reviews(self, case_id: str) -> list[CaseReview]:
        self.get_investment_case(case_id)
        return sorted(
            (r for r in self.case_reviews.values() if r.case_id == case_id), key=lambda r: (r.recorded_at, r.review_id)
        )

    def review_case_revision(self, revision_id: str, request: ReviewRequest) -> CaseReview:
        with self.approval_transaction():
            revision = self.get_case_revision(revision_id)
            case = self.get_investment_case(revision.case_id)
            if case.current_revision_id != revision_id and request.decision != "withdraw":
                raise Conflict("Cannot review a stale case revision")
            previous = self.case_reviews.get(request.supersedes_review_id) if request.supersedes_review_id else None
            if request.supersedes_review_id and (previous is None or not _visible(previous.company_id)):
                raise NotFound(request.supersedes_review_id)
            record = prepare_review(case, revision, request, previous)
            if previous is None and any(
                r.revision_id == revision_id
                and r.mode == record.mode
                and r.actor == record.actor
                and r.supersedes_review_id is None
                for r in self.case_reviews.values()
            ):
                raise Conflict("Reviewer already recorded a receipt; append a correction explicitly")
            if previous is not None and any(
                r.supersedes_review_id == previous.review_id for r in self.case_reviews.values()
            ):
                raise Conflict("Receipt already superseded; correct the latest receipt")
            self.case_reviews[record.review_id] = record
            self.append_audit(
                AuditEvent(
                    run_id=None,
                    company_id=case.company_id,
                    step="case_review",
                    event_type="case_review_recorded",
                    actor=record.actor,
                    created_at=record.recorded_at,
                    payload={
                        "case_id": case.case_id,
                        "revision_id": revision_id,
                        "review_id": record.review_id,
                        "mode": record.mode,
                        "decision": record.decision,
                    },
                )
            )
            return record

    def fenced_run(self, run_id: str, owner: str) -> FencedRepository:
        return FencedRepository(self, run_id, owner)

    def lease_valid(self, run_id: str, owner: str) -> bool:
        return self.locks.get(run_id) == owner and self.lease_times.get(run_id, now()) > now() - timedelta(minutes=15)

    # companies ---------------------------------------------------------------------------------------------
    def upsert_company(self, profile: CompanyProfile) -> None:
        security.require(profile.company_id)
        with self._lock:
            self.companies[profile.company_id] = profile

    def get_company(self, company_id: str) -> CompanyProfile:
        security.require(company_id)
        if company_id not in self.companies:
            raise NotFound(company_id)
        return self.companies[company_id]

    def list_companies(self) -> list[str]:
        return sorted(c for c in self.companies if _visible(c))

    # evidence ----------------------------------------------------------------------------------------------
    def add_evidence(self, record: EvidenceRecord) -> str:
        security.require(record.company_id)
        if record.company_id not in self.companies:
            raise NotFound(f"Company {record.company_id} is not onboarded")
        with self._lock:
            key = self.evidence_store.put_original(record.company_id, record.evidence_id, record.content)
            if record.evidence_id not in self.evidence:
                self.evidence[record.evidence_id] = EvidenceRef(
                    evidence_id=record.evidence_id,
                    company_id=record.company_id,
                    source_uri=record.source_uri,
                    source_type=record.source_type,
                    retrieved_at=record.retrieved_at,
                    as_of=record.as_of,
                    content_hash=record.content_hash,
                    metadata={**record.metadata, "storage_key": key, "size_bytes": len(record.content)},
                )
        return record.evidence_id

    def get_evidence(self, evidence_id: str) -> EvidenceRef:
        ev = self.evidence.get(evidence_id)
        if ev is None or not _visible(ev.company_id):
            raise NotFound(evidence_id)
        return ev

    def list_evidence(self, company_id: str, evidence_ids: list[str] | None = None) -> list[EvidenceRef]:
        security.require(company_id)
        wanted = set(evidence_ids) if evidence_ids is not None else None
        return sorted(
            (
                e
                for e in self.evidence.values()
                if e.company_id == company_id and (wanted is None or e.evidence_id in wanted)
            ),
            key=lambda e: e.evidence_id,
        )

    def evidence_for_opportunity(self, company_id: str, opportunity_id: str) -> list[EvidenceRef]:
        opp = self.get_opportunity(company_id, opportunity_id)
        return self.list_evidence(company_id, opp.evidence_ids)

    def evidence_content(self, evidence_id: str) -> bytes:
        ev = self.get_evidence(evidence_id)
        return self.evidence_store.get_original(ev.company_id, evidence_id)

    # runs --------------------------------------------------------------------------------------------------
    def create_run(
        self,
        company_id: str,
        requested_by: str,
        *,
        project_type: str = "value_creation_diagnostic",
        idempotency_key: str | None = None,
        reference_date: date | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[RunRecord, bool]:
        security.require(company_id)
        with self._lock:
            if company_id not in self.companies:
                raise NotFound(f"Company {company_id} is not onboarded")
            if idempotency_key:
                for r in self.runs.values():
                    if r.company_id == company_id and r.idempotency_key == idempotency_key:
                        return r, False
            ts = now()
            run_id = str(uuid.uuid4())
            rec = RunRecord(
                run_id=run_id,
                company_id=company_id,
                project_type=project_type,
                status=Status.PENDING,
                current_step=None,
                completed_steps=[],
                state={},
                idempotency_key=idempotency_key,
                requested_by=requested_by,
                reference_date=reference_date,
                params=params or {},
                created_at=ts,
                updated_at=ts,
            )
            self.runs[run_id] = rec
            return rec, True

    def get_run(self, run_id: str) -> RunRecord:
        r = self.runs.get(run_id)
        if r is None or not _visible(r.company_id):
            raise NotFound(run_id)
        return r

    def save_run_state(self, state: RunState) -> None:
        with self._lock:
            r = self.get_run(state.run_id)
            self.runs[state.run_id] = r.model_copy(
                update={
                    "status": state.status,
                    "current_step": state.current_step,
                    "completed_steps": list(state.completed_steps),
                    "state": state.to_json(),
                    "updated_at": now(),
                }
            )

    def list_runs(self, company_id: str | None = None, status: Status | None = None) -> list[RunRecord]:
        if company_id:
            security.require(company_id)
        return sorted(
            (
                r
                for r in self.runs.values()
                if _visible(r.company_id)
                and (company_id is None or r.company_id == company_id)
                and (status is None or r.status == status)
            ),
            key=lambda r: r.created_at,
        )

    def request_resume(self, run_id: str) -> None:
        with self._lock:
            r = self.get_run(run_id)
            self.runs[run_id] = r.model_copy(update={"resume_requested_at": now(), "updated_at": now()})

    def claim_runnable(self, worker_id: str, limit: int = 5) -> list[RunRecord]:
        with self._lock:
            out: list[RunRecord] = []
            for r in sorted(self.runs.values(), key=lambda r: r.created_at):
                if len(out) >= limit:
                    break
                if (
                    not _visible(r.company_id)
                    or (r.run_id in self.locks and self.lease_valid(r.run_id, self.locks[r.run_id]))
                    or r.params.get("mode") == "interactive"
                ):
                    continue  # interactive runs are driven by the client and finalized on approval
                if r.status in (Status.PENDING, Status.RUNNING) or (
                    r.resume_requested_at is not None and r.status not in (Status.COMPLETE, Status.REJECTED)
                ):
                    self.locks[r.run_id] = worker_id
                    self.lease_times[r.run_id] = now()
                    self.runs[r.run_id] = r.model_copy(update={"resume_requested_at": None})
                    out.append(self.runs[r.run_id])
            return out

    def acquire_run(self, run_id: str, worker_id: str) -> bool:
        self.get_run(run_id)
        with self._lock:
            holder = self.locks.get(run_id)
            if holder not in (None, worker_id) and self.lease_valid(run_id, holder):
                return False
            self.locks[run_id] = worker_id
            self.lease_times[run_id] = now()
            return True

    def renew_lease(self, run_id: str, worker_id: str) -> bool:
        with self._lock:
            if not self.lease_valid(run_id, worker_id):
                return False
            self.lease_times[run_id] = now()
            return True

    def release_run(self, run_id: str, worker_id: str | None = None) -> None:
        with self._lock:
            if worker_id is None or self.locks.get(run_id) == worker_id:
                self.locks.pop(run_id, None)

    # findings / opportunities --------------------------------------------------------------------------------
    def add_finding(self, finding: Finding) -> None:
        security.require(finding.company_id)
        run = self.get_run(finding.run_id)
        if run.company_id != finding.company_id:
            raise security.ScopeError("Finding company does not match run company")
        self._check_evidence(finding.company_id, finding.evidence_ids + finding.contradicting_evidence_ids)
        with self._lock:
            self.findings.setdefault(finding.finding_id, finding)

    def _check_evidence(self, company_id: str, ids: list[str]) -> None:
        for eid in ids:
            ev = self.evidence.get(eid)
            if ev is None or ev.company_id != company_id:
                raise NotFound(f"Evidence {eid} not found for company {company_id}")

    def list_findings(self, run_id: str) -> list[Finding]:
        self.get_run(run_id)
        return [f for f in self.findings.values() if f.run_id == run_id]

    def add_opportunity(self, opp: Opportunity, proposer: str, flow_through_rule: str = "") -> None:
        security.require(opp.company_id)
        run = self.get_run(opp.run_id)
        if run.company_id != opp.company_id:
            raise security.ScopeError("Opportunity company does not match run company")
        self._check_evidence(opp.company_id, opp.evidence_ids)
        with self._lock:
            self.opportunities.setdefault(opp.opportunity_id, (opp, proposer))

    def get_opportunity(self, company_id: str, opportunity_id: str) -> Opportunity:
        security.require(company_id)
        hit = self.opportunities.get(opportunity_id)
        if hit is None or hit[0].company_id != company_id:
            raise NotFound(opportunity_id)
        return hit[0]

    def list_opportunities(self, run_id: str) -> list[Opportunity]:
        self.get_run(run_id)
        return [o for o, _ in self.opportunities.values() if o.run_id == run_id]

    def save_value_case(self, company_id: str, run_id: str, vc: ValueCase, policy_version: str) -> None:
        self.get_opportunity(company_id, vc.opportunity_id)
        with self._lock:
            self.value_cases[vc.opportunity_id].append(vc)
            self.value_case_runs[vc.opportunity_id] = run_id

    def get_value_case(self, company_id: str, opportunity_id: str) -> ValueCase:
        self.get_opportunity(company_id, opportunity_id)
        cases = self.value_cases.get(opportunity_id)
        if not cases:
            raise NotFound(f"No value case for {opportunity_id}")
        return cases[-1]

    def list_value_cases(self, run_id: str) -> list[ValueCase]:
        self.get_run(run_id)
        return [cases[-1] for oid, cases in self.value_cases.items() if self.value_case_runs.get(oid) == run_id]

    def save_priorities(self, run_id: str, company_id: str, scores: list[PriorityScore]) -> None:
        security.require(company_id)
        self.get_run(run_id)
        with self._lock:
            self.priorities[run_id] = list(scores)

    def list_priorities(self, run_id: str) -> list[PriorityScore]:
        self.get_run(run_id)
        return sorted(self.priorities.get(run_id, []), key=lambda p: p.rank)

    # plans / approvals -------------------------------------------------------------------------------------
    @contextmanager
    def approval_transaction(self) -> Iterator[None]:
        # Private source bytes share the same rollback boundary as their receipts.
        with self._lock:
            fields = (
                "runs",
                "plans",
                "approvals",
                "audit",
                "kpi_defs",
                "investment_cases",
                "case_revisions",
                "case_reviews",
                "case_close_baselines",
                "case_observations",
                "case_attributions",
                "case_execution_events",
                "private_processing_grants",
                "private_intakes",
                "private_sources",
                "private_intake_reviews",
                "private_financial_snapshots",
                "private_underwriting",
                "private_capacity_plans",
                "private_plan_reviews",
                "private_baselines",
                "private_counterfactuals",
                "private_counterfactual_reviews",
                "private_observations",
                "private_execution_events",
                "private_attributions",
                "private_attribution_reviews",
            )
            before = {name: copy.deepcopy(getattr(self, name)) for name in fields}
            try:
                yield
            except BaseException:
                for name, value in before.items():
                    setattr(self, name, value)
                raise

    def save_plan(self, record: PlanRecord) -> None:
        security.require(record.company_id)
        self.get_run(record.run_id)
        with self._lock:
            for p in self.plans.values():
                if p.run_id == record.run_id and p.status == "proposed" and p.plan_id != record.plan_id:
                    self.plans[p.plan_id] = p.model_copy(update={"status": "superseded"})
            self.plans[record.plan_id] = record

    def get_plan(self, plan_id: str) -> PlanRecord:
        p = self.plans.get(plan_id)
        if p is None or not _visible(p.company_id):
            raise NotFound(plan_id)
        return p

    def latest_plan(self, run_id: str) -> PlanRecord | None:
        self.get_run(run_id)
        plans = [p for p in self.plans.values() if p.run_id == run_id and p.status != "superseded"]
        return max(plans, key=lambda p: p.created_at) if plans else None

    def update_plan_status(self, plan_id: str, status: str, approved_plan: dict[str, Any] | None = None) -> None:
        with self._lock:
            p = self.get_plan(plan_id)
            upd: dict[str, Any] = {"status": status}
            if status == "approved":
                upd.update(approved_plan=approved_plan or p.plan, approved_at=now())
            self.plans[plan_id] = p.model_copy(update=upd)

    def create_approval_request(
        self, run_id: str, company_id: str, artifact_type: str, artifact_id: str
    ) -> ApprovalRecord:
        security.require(company_id)
        self.get_run(run_id)
        with self._lock:
            for a in self.approvals.values():
                if a.run_id == run_id and a.artifact_id == artifact_id and a.decision is None:
                    return a
            rec = ApprovalRecord(
                approval_id=str(uuid.uuid4()),
                run_id=run_id,
                company_id=company_id,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                requested_at=now(),
            )
            self.approvals[rec.approval_id] = rec
            return rec

    def record_decision(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        rationale: str | None,
        edits: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        with self._lock:
            a = self.approvals.get(approval_id)
            if a is None or not _visible(a.company_id):
                raise NotFound(approval_id)
            if a.decision is not None:
                raise Conflict(f"Approval {approval_id} already decided ({a.decision})")
            rec = a.model_copy(
                update={
                    "decision": decision,
                    "decided_by": decided_by,
                    "rationale": rationale,
                    "edits": edits or {},
                    "diff": diff or {},
                    "decided_at": now(),
                }
            )
            self.approvals[approval_id] = rec
            if self.get_run(rec.run_id).params.get("mode") != "interactive":
                self.request_resume(rec.run_id)
            return rec

    def latest_approval(self, run_id: str) -> ApprovalRecord | None:
        items = self.list_approvals(run_id)
        return items[-1] if items else None

    def list_approvals(self, run_id: str) -> list[ApprovalRecord]:
        self.get_run(run_id)
        return sorted((a for a in self.approvals.values() if a.run_id == run_id), key=lambda a: a.requested_at)

    def pending_approvals(self) -> list[ApprovalRecord]:
        return sorted(
            (a for a in self.approvals.values() if a.decision is None and _visible(a.company_id)),
            key=lambda a: a.requested_at,
        )

    def mark_escalated(self, approval_id: str) -> None:
        with self._lock:
            a = self.approvals.get(approval_id)
            if a is None or not _visible(a.company_id):
                raise NotFound(approval_id)
            self.approvals[approval_id] = a.model_copy(update={"escalated_at": now()})

    # audit (append-only) -----------------------------------------------------------------------------------
    def append_audit(self, event: AuditEvent) -> None:
        security.require(event.company_id)
        with self._lock:
            self.audit.append(event)

    def list_audit(self, *, run_id: str | None = None, company_id: str | None = None) -> list[AuditEvent]:
        if company_id:
            security.require(company_id)
        return [
            e
            for e in self.audit
            if _visible(e.company_id)
            and (run_id is None or e.run_id == run_id)
            and (company_id is None or e.company_id == company_id)
        ]

    # KPIs --------------------------------------------------------------------------------------------------
    def save_kpi_definitions(self, defs: list[KpiDefinition]) -> None:
        for d in defs:
            security.require(d.company_id)
        with self._lock:
            for d in defs:
                for k, existing in list(self.kpi_defs.items()):
                    if (
                        existing.company_id == d.company_id
                        and existing.metric == d.metric
                        and existing.metric_params == d.metric_params
                        and existing.active
                        and k != d.kpi_id
                    ):
                        self.kpi_defs[k] = existing.model_copy(update={"active": False})
                self.kpi_defs[d.kpi_id] = d

    def list_kpi_definitions(self, company_id: str, active_only: bool = True) -> list[KpiDefinition]:
        security.require(company_id)
        return sorted(
            (d for d in self.kpi_defs.values() if d.company_id == company_id and (d.active or not active_only)),
            key=lambda d: d.kpi_id,
        )

    def add_kpi_observation(self, obs: KpiObservation) -> None:
        security.require(obs.company_id)
        with self._lock:
            self.kpi_obs.append(obs)

    def list_kpi_observations(self, company_id: str, kpi_id: str | None = None) -> list[KpiObservation]:
        security.require(company_id)
        return sorted(
            (o for o in self.kpi_obs if o.company_id == company_id and (kpi_id is None or o.kpi_id == kpi_id)),
            key=lambda o: (o.kpi_id, o.observed_at),
        )

    def add_kpi_alert(self, alert: KpiAlert) -> None:
        security.require(alert.company_id)
        with self._lock:
            self.kpi_alerts.append(alert)

    def list_kpi_alerts(self, company_id: str) -> list[KpiAlert]:
        security.require(company_id)
        return [a for a in self.kpi_alerts if a.company_id == company_id]

    def add_notification(self, n: Notification) -> None:
        security.require(n.company_id)
        with self._lock:
            if not any(x.notification_id == n.notification_id for x in self.notifications):
                self.notifications.append(n)

    def list_notifications(self, company_id: str) -> list[Notification]:
        security.require(company_id)
        return [n for n in self.notifications if n.company_id == company_id]

    def claim_notification(self, n: Notification, owner: str) -> bool:
        security.require(n.company_id)
        with self._lock:
            self.add_notification(n)
            current = next(x for x in self.notifications if x.notification_id == n.notification_id)
            claim = self.notification_claims.get(n.notification_id)
            if current.status == "delivered" or (claim and claim[1] > now() - timedelta(minutes=5)):
                return False
            self.notification_claims[n.notification_id] = (owner, now())
            return True

    def finish_notification(self, notification_id: str, owner: str, *, delivered: bool) -> None:
        with self._lock:
            claim = self.notification_claims.get(notification_id)
            if claim is None or claim[0] != owner:
                raise LeaseLost(notification_id)
            for i, n in enumerate(self.notifications):
                if n.notification_id == notification_id:
                    security.require(n.company_id)
                    self.notifications[i] = n.model_copy(
                        update={
                            "status": "delivered" if delivered else "pending",
                            "delivered_at": now() if delivered else None,
                        }
                    )
            del self.notification_claims[notification_id]

    # deletion ----------------------------------------------------------------------------------------------
    def delete_company_data(self, company_id: str) -> dict[str, int]:
        security.require(company_id)
        evidence_objects = self.evidence_store.delete_company(company_id)  # first, as in the PostgreSQL repository
        with self._lock:
            run_ids = {r for r, rec in self.runs.items() if rec.company_id == company_id}
            counts = {
                "runs": len(run_ids),
                "evidence": sum(1 for e in self.evidence.values() if e.company_id == company_id),
                "findings": sum(1 for f in self.findings.values() if f.company_id == company_id),
                "opportunities": sum(1 for o, _ in self.opportunities.values() if o.company_id == company_id),
            }
            self.evidence = {k: v for k, v in self.evidence.items() if v.company_id != company_id}
            self.findings = {k: v for k, v in self.findings.items() if v.company_id != company_id}
            opp_ids = {k for k, (o, _) in self.opportunities.items() if o.company_id == company_id}
            self.opportunities = {k: v for k, v in self.opportunities.items() if k not in opp_ids}
            for oid in opp_ids:
                self.value_cases.pop(oid, None)
                self.value_case_runs.pop(oid, None)
            for rid in run_ids:
                self.priorities.pop(rid, None)
                self.runs.pop(rid, None)
            self.plans = {k: v for k, v in self.plans.items() if v.company_id != company_id}
            self.approvals = {k: v for k, v in self.approvals.items() if v.company_id != company_id}
            self.kpi_defs = {k: v for k, v in self.kpi_defs.items() if v.company_id != company_id}
            self.kpi_obs = [o for o in self.kpi_obs if o.company_id != company_id]
            self.kpi_alerts = [a for a in self.kpi_alerts if a.company_id != company_id]
            self.notifications = [n for n in self.notifications if n.company_id != company_id]
            private_ids = {k for k, v in self.private_intakes.items() if v.company_id == company_id}
            counts["private_source_bytes"] = sum(len(self.private_sources[k]) for k in private_ids)
            self.private_sources = {k: v for k, v in self.private_sources.items() if k not in private_ids}
            for name in (
                "investment_cases",
                "case_revisions",
                "case_reviews",
                "case_close_baselines",
                "case_observations",
                "case_attributions",
                "case_execution_events",
                "private_processing_grants",
                "private_intakes",
                "private_intake_reviews",
                "private_financial_snapshots",
                "private_underwriting",
                "private_capacity_plans",
                "private_plan_reviews",
                "private_baselines",
                "private_counterfactuals",
                "private_counterfactual_reviews",
                "private_observations",
                "private_execution_events",
                "private_attributions",
                "private_attribution_reviews",
            ):
                rows = getattr(self, name)
                counts[name] = sum(row.company_id == company_id for row in rows.values())
                setattr(self, name, {key: row for key, row in rows.items() if row.company_id != company_id})
            self.companies.pop(company_id, None)
            counts["evidence_objects"] = evidence_objects
            return counts


_repo: Repository | None = None
_repo_lock = threading.Lock()


def set_repository(repo: Repository | None) -> None:
    global _repo
    _repo = repo


def get_repository() -> Repository:
    """In-memory repository in tests and dev; PostgreSQL when DATABASE_URL is set."""
    global _repo
    with _repo_lock:
        if _repo is None:
            url = os.environ.get("DATABASE_URL")
            if not url and os.environ.get("PVC_ENV", "prod") != "dev":
                raise RuntimeError("DATABASE_URL is required outside dev")
            store = _default_store()
            if url:
                from .postgres import PostgresRepository

                _repo = PostgresRepository(url, store)
            else:
                _repo = InMemoryRepository(store)
        return _repo


def _default_store() -> EvidenceStore:
    bucket = os.environ.get("PVC_EVIDENCE_BUCKET")
    if bucket:
        from .evidence_store import S3EvidenceStore

        return S3EvidenceStore(bucket, kms_key_id=os.environ.get("PVC_EVIDENCE_KMS_KEY_ID") or None)
    return FileSystemEvidenceStore(os.environ.get("PVC_EVIDENCE_DIR", "var/evidence"))


def as_decimal(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))
