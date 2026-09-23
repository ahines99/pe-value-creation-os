"""Repository interface and in-memory implementation (PVC-031).

Scope rules (both implementations):
- Methods that take `company_id` raise `ScopeError` when the current principal may not access it.
- Lookups by id return `NotFound` for rows outside the principal's scope, exactly as PostgreSQL row-level
  security hides them, so callers cannot probe for other companies' ids.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol

from .. import security
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


def now() -> datetime:
    return datetime.now(UTC)


class Repository(Protocol):
    evidence_store: EvidenceStore

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
    def release_run(self, run_id: str) -> None: ...

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
                if not _visible(r.company_id) or r.run_id in self.locks:
                    continue
                if r.status == Status.PENDING or (
                    r.resume_requested_at is not None and r.status not in (Status.COMPLETE, Status.REJECTED)
                ):
                    self.locks[r.run_id] = worker_id
                    self.runs[r.run_id] = r.model_copy(update={"resume_requested_at": None})
                    out.append(self.runs[r.run_id])
            return out

    def release_run(self, run_id: str) -> None:
        with self._lock:
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
            self.notifications.append(n)

    def list_notifications(self, company_id: str) -> list[Notification]:
        security.require(company_id)
        return [n for n in self.notifications if n.company_id == company_id]

    # deletion ----------------------------------------------------------------------------------------------
    def delete_company_data(self, company_id: str) -> dict[str, int]:
        security.require(company_id)
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
            self.companies.pop(company_id, None)
            counts["evidence_objects"] = self.evidence_store.delete_company(company_id)
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

        return S3EvidenceStore(bucket)
    return FileSystemEvidenceStore(os.environ.get("PVC_EVIDENCE_DIR", "var/evidence"))


def as_decimal(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))
