"""Repository interface and in-memory implementation (PVC-031).

Scope rules (both implementations):
- Methods that take `company_id` raise `ScopeError` when the current principal may not access it.
- Lookups by id return `NotFound` for rows outside the principal's scope, exactly as PostgreSQL row-level
  security hides them, so callers cannot probe for other companies' ids.
"""

from __future__ import annotations

import copy
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
    evidence_store: EvidenceStore

    def create_investment_case(self, company_id: str, case_id: str, label: str, currency: str) -> InvestmentCase: ...
    def get_investment_case(self, case_id: str) -> InvestmentCase: ...
    def append_case_revision(self, case_id: str, expected_parent: str | None, draft: RevisionDraft) -> CaseRevision: ...
    def get_case_revision(self, revision_id: str) -> CaseRevision: ...
    def list_case_revisions(self, case_id: str) -> list[CaseRevision]: ...
    def review_case_revision(self, revision_id: str, request: ReviewRequest) -> CaseReview: ...
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
        # Approval decisions mutate only these collections; no source/evidence object writes occur here.
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
            for name in (
                "investment_cases",
                "case_revisions",
                "case_reviews",
                "case_close_baselines",
                "case_observations",
                "case_attributions",
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
