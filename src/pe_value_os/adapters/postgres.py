"""PostgreSQL repository (PVC-031, PVC-034).

Each transaction sets `pvc.companies` to the current principal's allowed companies, so row-level security
filters every statement even if a query forgets a company predicate. Connect as the `pvc_app` role (not the
table owner) in every environment except migrations.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from typing import Any, TypeVar

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .. import security
from ..diligence import private_attribution
from ..diligence.cases import (
    CaseReview,
    CaseRevision,
    InvestmentCase,
    ReviewRequest,
    new_case,
    prepare_review,
)
from ..diligence.close_baseline import CloseBaseline
from ..diligence.execution import (
    Acceptance,
    ClaimLink,
    Delivery,
    ExecutionEvent,
    execution_report,
)
from ..diligence.models import Record
from ..diligence.private_baselines import (
    PrivateBaseline,
    PrivatePlanReview,
)
from ..diligence.private_capacity import (
    PrivateCapacityRevision,
)
from ..diligence.private_execution import PrivateExecutionEvent
from ..diligence.private_financials import (
    PrivateFinancialSnapshot,
)
from ..diligence.private_grants import (
    GrantEvent,
)
from ..diligence.private_grants import (
    require_reader as require_grant_reader,
)
from ..diligence.private_grants import (
    validate_key as validate_grant_key,
)
from ..diligence.private_observations import (
    CounterfactualReview,
    PrivateCounterfactual,
    PrivateObservation,
)
from ..diligence.private_records import (
    FinanceReview,
    PrivateIntake,
)
from ..diligence.private_underwriting import (
    PrivateUnderwritingRevision,
)
from ..diligence.realization import (
    Attribution,
    Observation,
    realization_report,
)
from ..domain.kpi_models import KpiAlert, KpiDefinition, KpiObservation, Notification
from ..domain.models import AuditEvent, EvidenceRef, Finding
from ..domain.project_models import Opportunity, PriorityScore, ScenarioInputs, ValueCase
from ..domain.runs import ApprovalDecision, ApprovalRecord, PlanRecord, RunRecord, RunState, Status
from ..domain.source_models import CompanyProfile
from .base import EvidenceRecord
from .evidence_store import EvidenceStore
from .repositories import LEASE, Conflict, FencedRepository, LeaseLost, NotFound, RecordRules

_R = TypeVar("_R", bound=Record)


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


_APPROVAL_CURSOR: ContextVar[tuple[int, Any] | None] = ContextVar("pvc_approval_cursor", default=None)


class PostgresRepository(RecordRules):
    def __init__(self, url: str, evidence_store: EvidenceStore, *, min_size: int = 1, max_size: int = 10):
        self.url = url
        self.evidence_store = evidence_store
        self.pool = ConnectionPool(
            url,
            min_size=min_size,
            max_size=max_size,
            open=True,
            kwargs={"row_factory": dict_row},
            check=ConnectionPool.check_connection,
        )

    def fenced_run(self, run_id: str, owner: str) -> FencedRepository:
        return FencedRepository(self, run_id, owner)

    @contextmanager
    def _private_transaction(self, company_id: str) -> Iterator[None]:
        with self.approval_transaction(), self._tx() as cur:
            # Serialize initial grants as well as revisions and revocations. The
            # company row exists before any private stream and is protected by RLS.
            if not cur.execute(
                "select company_id from companies where company_id=%s for update", (company_id,)
            ).fetchone():
                raise NotFound(company_id)
            yield

    @contextmanager
    def _case_transaction(self, case_id: str) -> Iterator[InvestmentCase]:
        with self.approval_transaction(), self._tx() as cur:
            row = cur.execute("select * from investment_cases where case_id=%s for update", (case_id,)).fetchone()
            if row is None:
                raise NotFound(case_id)
            yield self._investment_case(row)

    def _private_row(self, model: type[_R], table: str, key: str, company_id: str, record_id: str) -> _R:
        require_grant_reader(company_id)
        try:
            if str(uuid.UUID(record_id)) != record_id:
                raise ValueError("Noncanonical identifier")
        except ValueError as exc:
            raise NotFound(record_id) from exc
        with self._tx() as cur:
            row = cur.execute(
                f"select record from {table} where company_id=%s and {key}=%s", (company_id, record_id)
            ).fetchone()
        if row is None:
            raise NotFound(record_id)
        return model.model_validate(row["record"])

    def _private_attribution_records(self, company_id: str) -> list[private_attribution.PrivateAttribution]:
        require_grant_reader(company_id)
        with self._tx() as cur:
            return [
                private_attribution.PrivateAttribution.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_attributions where company_id=%s", (company_id,)
                ).fetchall()
            ]

    def _private_attribution_review_records(
        self, company_id: str, revision_id: str
    ) -> list[private_attribution.AttributionReview]:
        require_grant_reader(company_id)
        with self._tx() as cur:
            return [
                private_attribution.AttributionReview.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_attribution_reviews where company_id=%s and attribution_revision_id=%s order by sequence",
                    (company_id, revision_id),
                ).fetchall()
            ]

    def _save_private_attribution(self, record: private_attribution.PrivateAttribution) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_attributions
              (revision_id,company_id,case_key,attribution_key,sequence,previous_sha256,idempotency_key,content_sha256,baseline_id,baseline_sha256,observation_id,observation_sha256,execution_head_sha256,record)
              values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.revision_id,
                    record.company_id,
                    record.case_key,
                    record.attribution_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    record.baseline_id,
                    record.baseline_sha256,
                    record.request.observation_id,
                    record.request.observation_sha256,
                    record.request.expected_execution_head_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_attribution_review(
        self, record: private_attribution.AttributionReview, proposal: private_attribution.PrivateAttribution
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_attribution_reviews
              (review_id,company_id,case_key,attribution_revision_id,attribution_sha256,baseline_id,sequence,previous_sha256,idempotency_key,content_sha256,execution_head_sha256,record)
              values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.review_id,
                    record.company_id,
                    record.case_key,
                    record.attribution_revision_id,
                    record.request.expected_attribution_sha256,
                    proposal.baseline_id,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    record.request.expected_execution_head_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _private_execution_context(
        self, company_id: str, baseline_id: str
    ) -> tuple[PrivateBaseline, PrivateCapacityRevision]:
        baseline = self._private_baseline(company_id, baseline_id)
        return baseline, self._private_capacity_revision(company_id, baseline.request.capacity_revision_id)

    def _private_baseline(self, company_id: str, baseline_id: str) -> PrivateBaseline:
        return self._private_row(PrivateBaseline, "private_baselines", "baseline_id", company_id, baseline_id)

    def list_private_execution_events(self, company_id: str, baseline_id: str) -> list[PrivateExecutionEvent]:
        self._private_execution_context(company_id, baseline_id)
        with self._tx() as cur:
            return [
                PrivateExecutionEvent.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_execution_events where company_id=%s and baseline_id=%s order by sequence",
                    (company_id, baseline_id),
                ).fetchall()
            ]

    def _private_counterfactual(self, company_id: str, record_id: str) -> PrivateCounterfactual:
        return self._private_row(PrivateCounterfactual, "private_counterfactuals", "revision_id", company_id, record_id)

    def list_private_counterfactuals(self, company_id: str, case_key: str, key: str) -> list[PrivateCounterfactual]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        validate_grant_key(key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateCounterfactual.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_counterfactuals where company_id=%s and case_key=%s and counterfactual_key=%s order by sequence",
                    (company_id, case_key, key),
                ).fetchall()
            ]

    def _private_observation(self, company_id: str, record_id: str) -> PrivateObservation:
        return self._private_row(PrivateObservation, "private_observations", "observation_id", company_id, record_id)

    def list_private_observations(self, company_id: str, case_key: str, key: str) -> list[PrivateObservation]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        validate_grant_key(key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateObservation.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_observations where company_id=%s and case_key=%s and measurement_key=%s order by sequence",
                    (company_id, case_key, key),
                ).fetchall()
            ]

    def list_private_counterfactual_reviews(self, company_id: str, revision_id: str) -> list[CounterfactualReview]:
        self._private_counterfactual(company_id, revision_id)
        with self._tx() as cur:
            return [
                CounterfactualReview.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_counterfactual_reviews where company_id=%s and counterfactual_revision_id=%s order by sequence",
                    (company_id, revision_id),
                ).fetchall()
            ]

    def _private_capacity_revision(self, company_id: str, revision_id: str) -> PrivateCapacityRevision:
        return self._private_row(
            PrivateCapacityRevision, "private_capacity_plans", "revision_id", company_id, revision_id
        )

    def list_private_plan_reviews(self, company_id: str, revision_id: str) -> list[PrivatePlanReview]:
        self._private_capacity_revision(company_id, revision_id)
        with self._tx() as cur:
            return [
                PrivatePlanReview.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_plan_reviews where company_id=%s and capacity_revision_id=%s order by review_kind,sequence",
                    (company_id, revision_id),
                ).fetchall()
            ]

    def list_private_baselines(self, company_id: str, case_key: str) -> list[PrivateBaseline]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateBaseline.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_baselines where company_id=%s and case_key=%s order by sequence",
                    (company_id, case_key),
                ).fetchall()
            ]

    def list_private_capacity_plans(self, company_id: str, case_key: str) -> list[PrivateCapacityRevision]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateCapacityRevision.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_capacity_plans where company_id=%s and case_key=%s order by sequence",
                    (company_id, case_key),
                ).fetchall()
            ]

    def list_private_underwriting(self, company_id: str, case_key: str) -> list[PrivateUnderwritingRevision]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateUnderwritingRevision.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_underwriting where company_id=%s and case_key=%s order by sequence",
                    (company_id, case_key),
                ).fetchall()
            ]

    def list_private_financial_snapshots(self, company_id: str, case_key: str) -> list[PrivateFinancialSnapshot]:
        require_grant_reader(company_id)
        validate_grant_key(case_key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateFinancialSnapshot.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_financial_snapshots where company_id=%s and case_key=%s order by sequence",
                    (company_id, case_key),
                ).fetchall()
            ]

    def list_private_intakes(self, company_id: str, dataset_key: str) -> list[PrivateIntake]:
        require_grant_reader(company_id)
        validate_grant_key(dataset_key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                PrivateIntake.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_intakes where company_id=%s and dataset_key=%s order by sequence",
                    (company_id, dataset_key),
                ).fetchall()
            ]

    def _private_intake(self, company_id: str, intake_id: str) -> PrivateIntake:
        return self._private_row(PrivateIntake, "private_intakes", "intake_id", company_id, intake_id)

    def _private_source(self, company_id: str, intake_id: str) -> bytes:
        with self._tx() as cur:
            row = cur.execute(
                "select source_bytes from private_intakes where company_id=%s and intake_id=%s", (company_id, intake_id)
            ).fetchone()
        if row is None:
            raise NotFound(intake_id)
        return bytes(row["source_bytes"])

    def list_private_finance_reviews(self, company_id: str, intake_id: str) -> list[FinanceReview]:
        self._private_intake(company_id, intake_id)
        with self._tx() as cur:
            return [
                FinanceReview.model_validate(r["record"])
                for r in cur.execute(
                    "select record from private_intake_reviews where company_id=%s and intake_id=%s order by sequence",
                    (company_id, intake_id),
                ).fetchall()
            ]

    def list_private_grants(self, company_id: str, grant_key: str) -> list[GrantEvent]:
        require_grant_reader(company_id)
        validate_grant_key(grant_key)
        self.get_company(company_id)
        with self._tx() as cur:
            return [
                GrantEvent.model_validate(row["record"])
                for row in cur.execute(
                    "select record from private_processing_grants where company_id=%s and grant_key=%s order by sequence",
                    (company_id, grant_key),
                ).fetchall()
            ]

    def _private_underwriting_revision(self, company_id: str, revision_id: str) -> PrivateUnderwritingRevision:
        return self._private_row(
            PrivateUnderwritingRevision, "private_underwriting", "revision_id", company_id, revision_id
        )

    def _private_financial_snapshot(self, company_id: str, snapshot_id: str) -> PrivateFinancialSnapshot:
        return self._private_row(
            PrivateFinancialSnapshot, "private_financial_snapshots", "snapshot_id", company_id, snapshot_id
        )

    # Inserts run on the private transaction's cursor; related records supply binding columns.
    def _save_private_execution(self, record: PrivateExecutionEvent) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_execution_events
                (event_id,company_id,case_key,baseline_id,baseline_sha256,sequence,previous_sha256,idempotency_key,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.event_id,
                    record.company_id,
                    record.case_key,
                    record.baseline_id,
                    record.request.baseline_sha256,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_counterfactual(
        self, record: PrivateCounterfactual, baseline: PrivateBaseline, anchor: PrivateFinancialSnapshot
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_counterfactuals (revision_id,company_id,case_key,sequence,previous_sha256,idempotency_key,content_sha256,counterfactual_key,baseline_id,baseline_sha256,financial_snapshot_sha256,record) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.revision_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    record.counterfactual_key,
                    baseline.baseline_id,
                    baseline.content_sha256,
                    anchor.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_counterfactual_review(
        self, record: CounterfactualReview, proposal: PrivateCounterfactual
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_counterfactual_reviews (review_id,company_id,case_key,sequence,previous_sha256,idempotency_key,content_sha256,counterfactual_revision_id,counterfactual_sha256,record) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.review_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    proposal.revision_id,
                    proposal.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_observation(
        self,
        record: PrivateObservation,
        baseline: PrivateBaseline,
        proposal: PrivateCounterfactual,
        review: CounterfactualReview,
        actual: PrivateFinancialSnapshot,
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_observations (observation_id,company_id,case_key,sequence,previous_sha256,idempotency_key,content_sha256,measurement_key,baseline_id,baseline_sha256,counterfactual_revision_id,counterfactual_sha256,counterfactual_review_sha256,actual_snapshot_id,actual_snapshot_sha256,record) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.observation_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    record.measurement_key,
                    baseline.baseline_id,
                    baseline.content_sha256,
                    proposal.revision_id,
                    proposal.content_sha256,
                    review.content_sha256,
                    actual.snapshot_id,
                    actual.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_plan_review(self, record: PrivatePlanReview, plan: PrivateCapacityRevision) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_plan_reviews
                (review_id,company_id,case_key,capacity_revision_id,capacity_sha256,review_kind,sequence,previous_sha256,idempotency_key,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.review_id,
                    record.company_id,
                    plan.case_key,
                    plan.revision_id,
                    plan.content_sha256,
                    record.review_kind,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_baseline(self, record: PrivateBaseline) -> None:
        request = record.request
        with self._tx() as cur:
            cur.execute(
                """insert into private_baselines
                (baseline_id,company_id,case_key,sequence,previous_sha256,idempotency_key,capacity_revision_id,capacity_sha256,
                 finance_review_id,finance_review_sha256,operating_review_id,operating_review_sha256,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.baseline_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    request.expected_previous_sha256,
                    request.idempotency_key,
                    request.capacity_revision_id,
                    request.expected_capacity_sha256,
                    request.finance_review_id,
                    request.finance_review_sha256,
                    request.operating_review_id,
                    request.operating_review_sha256,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_capacity_plan(
        self, record: PrivateCapacityRevision, underwriting: PrivateUnderwritingRevision
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_capacity_plans
                (revision_id,company_id,case_key,sequence,previous_sha256,idempotency_key,underwriting_sha256,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.revision_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    underwriting.content_sha256,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_underwriting(
        self, record: PrivateUnderwritingRevision, snapshot: PrivateFinancialSnapshot
    ) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_underwriting
                (revision_id,company_id,case_key,sequence,previous_sha256,idempotency_key,snapshot_sha256,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.revision_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    snapshot.content_sha256,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_financial_snapshot(self, record: PrivateFinancialSnapshot, intake: PrivateIntake) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_financial_snapshots
                (snapshot_id,company_id,case_key,sequence,previous_sha256,idempotency_key,intake_id,intake_sha256,finance_review_sha256,grant_key,grant_sha256,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.snapshot_id,
                    record.company_id,
                    record.case_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    intake.intake_id,
                    intake.content_sha256,
                    record.request.expected_finance_review_sha256,
                    intake.request.grant_key,
                    record.request.expected_grant_sha256,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_intake(self, record: PrivateIntake, raw: bytes) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_intakes
              (intake_id,company_id,dataset_key,sequence,previous_sha256,idempotency_key,grant_key,grant_sha256,content_sha256,source_sha256,source_bytes,record)
              values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.intake_id,
                    record.company_id,
                    record.dataset_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.request.grant_key,
                    record.request.expected_grant_sha256,
                    record.content_sha256,
                    record.source_sha256,
                    raw,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_finance_review(self, record: FinanceReview, intake: PrivateIntake) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_intake_reviews
              (review_id,company_id,intake_id,intake_sha256,sequence,previous_sha256,idempotency_key,grant_key,grant_sha256,content_sha256,decision,actor_type,record)
              values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.review_id,
                    record.company_id,
                    record.intake_id,
                    intake.content_sha256,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    intake.request.grant_key,
                    record.request.expected_grant_sha256,
                    record.content_sha256,
                    record.request.decision,
                    record.actor_type,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_private_grant(self, record: GrantEvent) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into private_processing_grants
                (event_id,company_id,grant_key,sequence,previous_sha256,idempotency_key,action,actor_type,content_sha256,recorded_at,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.event_id,
                    record.company_id,
                    record.grant_key,
                    record.sequence,
                    record.request.expected_previous_sha256,
                    record.request.idempotency_key,
                    record.request.action,
                    record.actor_type,
                    record.content_sha256,
                    record.recorded_at,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def create_investment_case(self, company_id: str, case_id: str, label: str, currency: str) -> InvestmentCase:
        with self.approval_transaction(), self._tx() as cur:
            self.get_company(company_id)
            record = new_case(company_id, case_id, label, currency)
            row = cur.execute(
                """insert into investment_cases(case_id,company_id,label,currency,classification,created_by,created_at,version)
                values (%s,%s,%s,%s,%s,%s,%s,0) on conflict (case_id) do nothing returning case_id""",
                (case_id, company_id, label, currency, record.classification, record.created_by, record.created_at),
            ).fetchone()
            if row is None:
                raise Conflict("Case identity already exists")
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

    @staticmethod
    def _investment_case(row: Any) -> InvestmentCase:
        return InvestmentCase.model_validate(
            {
                **row,
                "current_revision_id": _s(row["current_revision_id"]),
                "original_revision_id": _s(row["original_revision_id"]),
            }
        )

    def get_investment_case(self, case_id: str) -> InvestmentCase:
        with self._tx() as cur:
            row = cur.execute("select * from investment_cases where case_id = %s", (case_id,)).fetchone()
            if row is None:
                raise NotFound(case_id)
            return self._investment_case(row)

    def _save_case_revision(self, record: CaseRevision, case: InvestmentCase) -> None:
        with self._tx() as cur:
            cur.execute(
                """insert into case_revisions(revision_id,company_id,case_id,sequence,parent_revision_id,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.revision_id,
                    record.company_id,
                    case.case_id,
                    record.sequence,
                    record.parent_revision_id,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )
            cur.execute(
                "update investment_cases set version=%s,current_revision_id=%s,original_revision_id=coalesce(original_revision_id,%s) where case_id=%s",
                (record.sequence, record.revision_id, record.revision_id, case.case_id),
            )

    def _save_execution_event(self, record: ExecutionEvent) -> None:
        request = record.request
        payload = request.payload
        support = (
            payload.assignment
            if isinstance(payload, Delivery)
            else payload.delivery
            if isinstance(payload, Acceptance)
            else payload.acceptance
            if isinstance(payload, ClaimLink)
            else None
        )
        with self._tx() as cur:
            cur.execute(
                """insert into case_execution_events(event_id,company_id,case_id,baseline_id,baseline_sha256,mode,kind,stream_key,sequence,previous_id,ingestion_key,actor_type,effective_on,supporting_event_id,supporting_sha256,attribution_id,attribution_sha256,content_sha256,recorded_at,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.event_id,
                    record.company_id,
                    record.case_id,
                    request.baseline_id,
                    request.baseline_sha256,
                    request.mode,
                    payload.kind,
                    record.stream_key,
                    record.sequence,
                    request.expected_previous_id,
                    request.ingestion_key,
                    record.actor_type,
                    request.effective_on,
                    support.event_id if support else None,
                    support.sha256 if support else None,
                    payload.attribution_id if isinstance(payload, ClaimLink) else None,
                    payload.attribution_sha256 if isinstance(payload, ClaimLink) else None,
                    record.content_sha256,
                    record.recorded_at,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_case_observation(self, record: Observation) -> None:
        request = record.request
        with self._tx() as cur:
            cur.execute(
                "insert into case_observations (observation_id,company_id,case_id,baseline_id,baseline_sha256,period_start,period_end,sequence,previous_id,ingestion_key,content_sha256,recorded_at,record) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    record.observation_id,
                    record.company_id,
                    record.case_id,
                    request.baseline_id,
                    request.baseline_sha256,
                    request.observed.start,
                    request.observed.end,
                    record.sequence,
                    request.expected_previous_id,
                    request.ingestion_key,
                    record.content_sha256,
                    record.recorded_at,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_case_attribution(self, record: Attribution) -> None:
        request = record.request
        with self._tx() as cur:
            cur.execute(
                "insert into case_attributions (attribution_id,company_id,case_id,observation_id,observation_sha256,mode,actor_type,sequence,previous_id,ingestion_key,content_sha256,recorded_at,record) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    record.attribution_id,
                    record.company_id,
                    record.case_id,
                    request.observation_id,
                    request.observation_sha256,
                    request.mode,
                    record.actor_type,
                    record.sequence,
                    request.expected_previous_id,
                    request.ingestion_key,
                    record.content_sha256,
                    record.recorded_at,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def _save_close_baseline(self, record: CloseBaseline) -> None:
        request = record.request
        with self._tx() as cur:
            cur.execute(
                """insert into case_close_baselines(baseline_id,company_id,case_id,sequence,revision_id,revision_sha256,review_id,mode,previous_id,actor_type,content_sha256,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.baseline_id,
                    record.company_id,
                    record.case_id,
                    record.sequence,
                    request.revision_id,
                    request.revision_sha256,
                    request.review_id,
                    request.mode,
                    request.expected_previous_id,
                    record.actor_type,
                    record.content_sha256,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )

    def get_case_revision(self, revision_id: str) -> CaseRevision:
        try:
            uuid.UUID(revision_id)
        except ValueError as exc:
            raise NotFound(revision_id) from exc
        with self._tx() as cur:
            row = cur.execute("select record from case_revisions where revision_id = %s", (revision_id,)).fetchone()
            if row is None:
                raise NotFound(revision_id)
            return CaseRevision.model_validate(row["record"])

    def list_case_revisions(self, case_id: str) -> list[CaseRevision]:
        with self._tx() as cur:
            if cur.execute("select 1 from investment_cases where case_id=%s", (case_id,)).fetchone() is None:
                raise NotFound(case_id)
            return [
                CaseRevision.model_validate(row["record"])
                for row in cur.execute(
                    "select record from case_revisions where case_id = %s order by sequence", (case_id,)
                ).fetchall()
            ]

    def list_close_baselines(self, case_id: str) -> list[CloseBaseline]:
        self.get_investment_case(case_id)
        with self._tx() as cur:
            return [
                CloseBaseline.model_validate(row["record"])
                for row in cur.execute(
                    "select record from case_close_baselines where case_id=%s order by mode,sequence", (case_id,)
                ).fetchall()
            ]

    def list_execution_events(self, case_id: str) -> list[ExecutionEvent]:
        self.get_investment_case(case_id)
        with self._tx() as cur:
            return [
                ExecutionEvent.model_validate(row["record"])
                for row in cur.execute(
                    "select record from case_execution_events where case_id=%s order by recorded_at,event_id",
                    (case_id,),
                ).fetchall()
            ]

    def case_execution(self, case_id: str, baseline_id: str, as_of: date) -> dict[str, Any]:
        row = self._case_snapshot(case_id)
        case = InvestmentCase.model_validate(row["case_record"])
        baselines = [CloseBaseline.model_validate(r) for r in row["baselines"]]
        baseline = next((b for b in baselines if b.baseline_id == baseline_id), None)
        if baseline is None:
            raise NotFound(baseline_id)
        revision = next(
            CaseRevision.model_validate(r) for r in row["revisions"] if r["revision_id"] == baseline.request.revision_id
        )
        return execution_report(
            case,
            baseline,
            revision,
            [CaseReview.model_validate(r) for r in row["reviews"]],
            baselines,
            [ExecutionEvent.model_validate(r) for r in row["execution_events"]],
            [Observation.model_validate(r) for r in row["observations"]],
            [Attribution.model_validate(r) for r in row["attributions"]],
            as_of,
        )

    def list_case_observations(self, case_id: str) -> list[Observation]:
        self.get_investment_case(case_id)
        with self._tx() as cur:
            return [
                Observation.model_validate(row["record"])
                for row in cur.execute(
                    "select record from case_observations where case_id=%s order by recorded_at,observation_id",
                    (case_id,),
                ).fetchall()
            ]

    def list_case_attributions(self, case_id: str) -> list[Attribution]:
        self.get_investment_case(case_id)
        with self._tx() as cur:
            return [
                Attribution.model_validate(row["record"])
                for row in cur.execute(
                    "select record from case_attributions where case_id=%s order by recorded_at,attribution_id",
                    (case_id,),
                ).fetchall()
            ]

    def _case_snapshot(self, case_id: str) -> dict[str, Any]:
        # One statement gives a coherent committed snapshot without requiring a
        # write lock or UPDATE grants from a read-only database identity.
        with self._tx() as cur:
            row = cur.execute(
                """
                select to_jsonb(c) as case_record,
                  (select coalesce(jsonb_agg(record order by sequence),'[]') from case_revisions where case_id=c.case_id) as revisions,
                  (select coalesce(jsonb_agg(record order by recorded_at,review_id),'[]') from case_reviews where case_id=c.case_id) as reviews,
                  (select coalesce(jsonb_agg(record order by mode,sequence),'[]') from case_close_baselines where case_id=c.case_id) as baselines,
                  (select coalesce(jsonb_agg(record order by recorded_at,observation_id),'[]') from case_observations where case_id=c.case_id) as observations,
                  (select coalesce(jsonb_agg(record order by recorded_at,attribution_id),'[]') from case_attributions where case_id=c.case_id) as attributions,
                  (select coalesce(jsonb_agg(record order by recorded_at,event_id),'[]') from case_execution_events where case_id=c.case_id) as execution_events
                from investment_cases c where case_id=%s
                """,
                (case_id,),
            ).fetchone()
            if row is None:
                raise NotFound(case_id)
            return dict(row)

    def case_realization(self, case_id: str, baseline_id: str) -> dict[str, Any]:
        row = self._case_snapshot(case_id)
        case = InvestmentCase.model_validate(row["case_record"])
        baselines = [CloseBaseline.model_validate(r) for r in row["baselines"]]
        baseline = next((b for b in baselines if b.baseline_id == baseline_id), None)
        if baseline is None:
            raise NotFound(baseline_id)
        return realization_report(
            case,
            baseline,
            [CaseRevision.model_validate(r) for r in row["revisions"]],
            [CaseReview.model_validate(r) for r in row["reviews"]],
            baselines,
            [Observation.model_validate(r) for r in row["observations"]],
            [Attribution.model_validate(r) for r in row["attributions"]],
        )

    def list_case_reviews(self, case_id: str) -> list[CaseReview]:
        with self._tx() as cur:
            if cur.execute("select 1 from investment_cases where case_id=%s", (case_id,)).fetchone() is None:
                raise NotFound(case_id)
            return [
                CaseReview.model_validate(row["record"])
                for row in cur.execute(
                    "select record from case_reviews where case_id=%s order by recorded_at,review_id", (case_id,)
                ).fetchall()
            ]

    def review_case_revision(self, revision_id: str, request: ReviewRequest) -> CaseReview:
        with self.approval_transaction(), self._tx() as cur:
            revision = self.get_case_revision(revision_id)
            row = cur.execute(
                "select * from investment_cases where case_id=%s for update", (revision.case_id,)
            ).fetchone()
            if row is None:
                raise NotFound(revision.case_id)
            case = self._investment_case(row)
            if case.current_revision_id != revision_id and request.decision != "withdraw":
                raise Conflict("Cannot review a stale case revision")
            previous = None
            if request.supersedes_review_id:
                prior = cur.execute(
                    "select record from case_reviews where review_id=%s", (request.supersedes_review_id,)
                ).fetchone()
                if prior is None:
                    raise NotFound(request.supersedes_review_id)
                previous = CaseReview.model_validate(prior["record"])
            record = prepare_review(case, revision, request, previous)
            # The case row lock serializes review and revision writes, including corrections.
            if (
                previous is None
                and cur.execute(
                    "select 1 from case_reviews where revision_id=%s and mode=%s and actor=%s and supersedes_review_id is null",
                    (revision_id, record.mode, record.actor),
                ).fetchone()
            ):
                raise Conflict("Reviewer already recorded a receipt; append a correction explicitly")
            if (
                previous is not None
                and cur.execute(
                    "select 1 from case_reviews where supersedes_review_id=%s", (previous.review_id,)
                ).fetchone()
            ):
                raise Conflict("Receipt already superseded; correct the latest receipt")
            cur.execute(
                """insert into case_reviews(review_id,company_id,case_id,revision_id,revision_sha256,mode,decision,actor,actor_type,recorded_at,supersedes_review_id,record)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    record.review_id,
                    record.company_id,
                    record.case_id,
                    record.revision_id,
                    record.revision_sha256,
                    record.mode,
                    record.decision,
                    record.actor,
                    record.actor_type,
                    record.recorded_at,
                    record.supersedes_review_id,
                    Jsonb(record.model_dump(mode="json")),
                ),
            )
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

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def approval_transaction(self) -> Iterator[None]:
        with self._tx() as cur:
            token = _APPROVAL_CURSOR.set((id(self), cur))
            try:
                yield
            finally:
                _APPROVAL_CURSOR.reset(token)

    @contextmanager
    def _tx(self) -> Iterator[Any]:
        current = _APPROVAL_CURSOR.get()
        if current is not None and current[0] == id(self):
            yield current[1]
            return
        scope = ",".join(sorted(security.allowed_companies()))
        with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("select set_config('pvc.companies', %s, true)", (scope,))
            lease = LEASE.get()
            if (
                lease
                and not cur.execute(
                    "select 1 from workflow_runs where run_id = %s and locked_by = %s "
                    "and locked_at > now() - interval '15 minutes' for update",
                    lease,
                ).fetchone()
            ):
                raise LeaseLost(lease[0])
            yield cur

    # companies ---------------------------------------------------------------------------------------------
    def upsert_company(self, profile: CompanyProfile) -> None:
        security.require(profile.company_id)
        with self._tx() as cur:
            cur.execute(
                """insert into companies (company_id, name, profile) values (%s, %s, %s)
                   on conflict (company_id) do update set name = excluded.name, profile = excluded.profile""",
                (profile.company_id, profile.name, Jsonb(profile.model_dump(mode="json"))),
            )

    def get_company(self, company_id: str) -> CompanyProfile:
        security.require(company_id)
        with self._tx() as cur:
            row = cur.execute("select profile from companies where company_id = %s", (company_id,)).fetchone()
        if not row:
            raise NotFound(company_id)
        return CompanyProfile.model_validate(row["profile"])

    def list_companies(self) -> list[str]:
        with self._tx() as cur:
            return [r["company_id"] for r in cur.execute("select company_id from companies order by 1").fetchall()]

    # evidence ----------------------------------------------------------------------------------------------
    def add_evidence(self, record: EvidenceRecord) -> str:
        security.require(record.company_id)
        with self._tx() as cur:
            if not cur.execute("select 1 from companies where company_id = %s", (record.company_id,)).fetchone():
                raise NotFound(f"Company {record.company_id} is not onboarded")
            # Ownership is checked and locked before the external object-store write.
            key = self.evidence_store.put_original(record.company_id, record.evidence_id, record.content)
            cur.execute(
                """insert into evidence (evidence_id, company_id, source_uri, source_type, as_of, retrieved_at,
                     content_hash, storage_key, size_bytes, metadata)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict do nothing""",
                (
                    record.evidence_id,
                    record.company_id,
                    record.source_uri,
                    record.source_type,
                    record.as_of,
                    record.retrieved_at,
                    record.content_hash,
                    key,
                    len(record.content),
                    Jsonb(record.metadata),
                ),
            )
        return record.evidence_id

    @staticmethod
    def _ev(row: dict[str, Any]) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=str(row["evidence_id"]),
            company_id=row["company_id"],
            source_uri=row["source_uri"],
            source_type=row["source_type"],
            retrieved_at=row["retrieved_at"],
            as_of=row["as_of"],
            content_hash=row["content_hash"],
            run_id=_s(row["run_id"]),
            metadata={**row["metadata"], "storage_key": row["storage_key"], "size_bytes": row["size_bytes"]},
        )

    def get_evidence(self, evidence_id: str) -> EvidenceRef:
        with self._tx() as cur:
            row = cur.execute("select * from evidence where evidence_id = %s", (evidence_id,)).fetchone()
        if not row:
            raise NotFound(evidence_id)
        return self._ev(row)

    def list_evidence(self, company_id: str, evidence_ids: list[str] | None = None) -> list[EvidenceRef]:
        security.require(company_id)
        with self._tx() as cur:
            if evidence_ids is None:
                rows = cur.execute(
                    "select * from evidence where company_id = %s order by evidence_id", (company_id,)
                ).fetchall()
            else:
                rows = cur.execute(
                    "select * from evidence where company_id = %s and evidence_id = any(%s::uuid[]) "
                    "order by evidence_id",
                    (company_id, evidence_ids),
                ).fetchall()
        return [self._ev(r) for r in rows]

    def evidence_for_opportunity(self, company_id: str, opportunity_id: str) -> list[EvidenceRef]:
        security.require(company_id)
        with self._tx() as cur:
            rows = cur.execute(
                """select e.* from evidence e join opportunity_evidence oe on oe.evidence_id = e.evidence_id
                   join opportunities o on o.opportunity_id = oe.opportunity_id
                   where o.company_id = %s and o.opportunity_id = %s order by e.evidence_id""",
                (company_id, opportunity_id),
            ).fetchall()
        if not rows:
            self.get_opportunity(company_id, opportunity_id)
        return [self._ev(r) for r in rows]

    def evidence_content(self, evidence_id: str) -> bytes:
        ev = self.get_evidence(evidence_id)
        return self.evidence_store.get_original(ev.company_id, evidence_id)

    # runs --------------------------------------------------------------------------------------------------
    @staticmethod
    def _run(row: dict[str, Any]) -> RunRecord:
        return RunRecord(
            run_id=str(row["run_id"]),
            company_id=row["company_id"],
            project_type=row["project_type"],
            status=Status(row["status"]),
            current_step=row["current_step"],
            completed_steps=row["completed_steps"],
            state=row["state"],
            idempotency_key=row["idempotency_key"],
            requested_by=row["requested_by"],
            reference_date=row["reference_date"],
            params=row["params"],
            resume_requested_at=row["resume_requested_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

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
        with self._tx() as cur:
            if not cur.execute("select 1 from companies where company_id = %s", (company_id,)).fetchone():
                raise NotFound(f"Company {company_id} is not onboarded")
            row = cur.execute(
                """insert into workflow_runs (run_id, company_id, project_type, status, idempotency_key, requested_by,
                     reference_date, params)
                   values (%s, %s, %s, 'pending', %s, %s, %s, %s)
                   on conflict (company_id, idempotency_key) do nothing returning *""",
                (
                    str(uuid.uuid4()),
                    company_id,
                    project_type,
                    idempotency_key,
                    requested_by,
                    reference_date,
                    Jsonb(params or {}),
                ),
            ).fetchone()
            if row:
                return self._run(row), True
            row = cur.execute(
                "select * from workflow_runs where company_id = %s and idempotency_key = %s",
                (company_id, idempotency_key),
            ).fetchone()
            return self._run(row), False

    def get_run(self, run_id: str) -> RunRecord:
        with self._tx() as cur:
            row = cur.execute("select * from workflow_runs where run_id = %s", (run_id,)).fetchone()
        if not row:
            raise NotFound(run_id)
        return self._run(row)

    def save_run_state(self, state: RunState) -> None:
        with self._tx() as cur:
            n = cur.execute(
                """update workflow_runs set status = %s, current_step = %s, completed_steps = %s, state = %s,
                     updated_at = now() where run_id = %s""",
                (
                    state.status.value,
                    state.current_step,
                    Jsonb(list(state.completed_steps)),
                    Jsonb(state.to_json()),
                    state.run_id,
                ),
            ).rowcount
        if n == 0:
            raise NotFound(state.run_id)

    def list_runs(self, company_id: str | None = None, status: Status | None = None) -> list[RunRecord]:
        if company_id:
            security.require(company_id)
        q, args = "select * from workflow_runs where true", []
        if company_id:
            q += " and company_id = %s"
            args.append(company_id)
        if status:
            q += " and status = %s"
            args.append(status.value)
        with self._tx() as cur:
            return [self._run(r) for r in cur.execute(q + " order by created_at", args).fetchall()]

    def request_resume(self, run_id: str) -> None:
        with self._tx() as cur:
            n = cur.execute(
                "update workflow_runs set resume_requested_at = now(), updated_at = now() where run_id = %s", (run_id,)
            ).rowcount
        if n == 0:
            raise NotFound(run_id)

    def claim_runnable(self, worker_id: str, limit: int = 5) -> list[RunRecord]:
        with self._tx() as cur:
            rows = cur.execute(
                """update workflow_runs set locked_by = %s, locked_at = now(), resume_requested_at = null
                   where run_id in (
                     select run_id from workflow_runs
                     where (status in ('pending', 'running')
                            or (resume_requested_at is not null and status not in ('complete', 'rejected')))
                       and coalesce(params->>'mode', 'automated') <> 'interactive'
                       and (locked_by is null or locked_at < now() - interval '15 minutes')
                     order by created_at for update skip locked limit %s)
                   returning *""",
                (worker_id, limit),
            ).fetchall()
        return [self._run(r) for r in rows]

    def acquire_run(self, run_id: str, worker_id: str) -> bool:
        """Take the run lock for a direct execution (CLI). Fails if another live holder has it."""
        self.get_run(run_id)
        with self._tx() as cur:
            row = cur.execute(
                """update workflow_runs set locked_by = %s, locked_at = now()
                   where run_id = %s
                     and (locked_by is null or locked_by = %s or locked_at < now() - interval '15 minutes')
                   returning run_id""",
                (worker_id, run_id, worker_id),
            ).fetchone()
        return row is not None

    def renew_lease(self, run_id: str, worker_id: str) -> bool:
        """Heartbeat: extend the lease. False means the lock was lost to another worker."""
        with self._tx() as cur:
            row = cur.execute(
                "update workflow_runs set locked_at = now() where run_id = %s and locked_by = %s and locked_at > now() - interval '15 minutes' returning run_id",
                (run_id, worker_id),
            ).fetchone()
        return row is not None

    def release_run(self, run_id: str, worker_id: str | None = None) -> None:
        with self._tx() as cur:
            if worker_id is None:
                cur.execute("update workflow_runs set locked_by = null, locked_at = null where run_id = %s", (run_id,))
            else:
                cur.execute(
                    "update workflow_runs set locked_by = null, locked_at = null where run_id = %s and locked_by = %s",
                    (run_id, worker_id),
                )

    # findings ----------------------------------------------------------------------------------------------
    def add_finding(self, finding: Finding) -> None:
        security.require(finding.company_id)
        with self._tx() as cur:
            run = cur.execute("select company_id from workflow_runs where run_id = %s", (finding.run_id,)).fetchone()
            if not run:
                raise NotFound(finding.run_id)
            if run["company_id"] != finding.company_id:
                raise security.ScopeError("Finding company does not match run company")
            if cur.execute("select 1 from findings where finding_id = %s", (finding.finding_id,)).fetchone():
                return  # idempotent: deterministic ids make re-runs safe
            cur.execute(
                """insert into findings (finding_id, run_id, company_id, finding_type, title, statement, confidence,
                     assumptions, metadata) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    finding.finding_id,
                    finding.run_id,
                    finding.company_id,
                    finding.finding_type.value,
                    finding.title,
                    finding.statement,
                    finding.confidence.value,
                    Jsonb(finding.assumptions),
                    Jsonb(finding.metadata),
                ),
            )
            links = [(e, "supports") for e in finding.evidence_ids] + [
                (e, "contradicts") for e in finding.contradicting_evidence_ids
            ]
            for eid, rel in links:
                self._require_evidence(cur, finding.company_id, eid)
                cur.execute(
                    "insert into finding_evidence (finding_id, evidence_id, relation) values (%s, %s, %s)",
                    (finding.finding_id, eid, rel),
                )

    @staticmethod
    def _require_evidence(cur: Any, company_id: str, evidence_id: str) -> None:
        if not cur.execute(
            "select 1 from evidence where evidence_id = %s and company_id = %s", (evidence_id, company_id)
        ).fetchone():
            raise NotFound(f"Evidence {evidence_id} not found for company {company_id}")

    def list_findings(self, run_id: str) -> list[Finding]:
        self.get_run(run_id)
        with self._tx() as cur:
            rows = cur.execute(
                """select f.*,
                     coalesce(array_agg(fe.evidence_id::text) filter (where fe.relation = 'supports'), '{}') as sup,
                     coalesce(array_agg(fe.evidence_id::text) filter (where fe.relation = 'contradicts'), '{}') as con
                   from findings f left join finding_evidence fe on fe.finding_id = f.finding_id
                   where f.run_id = %s group by f.finding_id order by f.created_at, f.finding_id""",
                (run_id,),
            ).fetchall()
        return [
            Finding(
                finding_id=str(r["finding_id"]),
                run_id=str(r["run_id"]),
                company_id=r["company_id"],
                finding_type=r["finding_type"],
                title=r["title"],
                statement=r["statement"],
                confidence=r["confidence"],
                evidence_ids=sorted(r["sup"]),
                contradicting_evidence_ids=sorted(r["con"]),
                assumptions=r["assumptions"],
                metadata=r["metadata"],
            )
            for r in rows
        ]

    # opportunities -----------------------------------------------------------------------------------------
    def add_opportunity(self, opp: Opportunity, proposer: str, flow_through_rule: str = "") -> None:
        security.require(opp.company_id)
        scen = {k: getattr(opp, k).model_dump(mode="json") for k in ("low", "base", "high")}
        with self._tx() as cur:
            run = cur.execute("select company_id from workflow_runs where run_id = %s", (opp.run_id,)).fetchone()
            if not run:
                raise NotFound(opp.run_id)
            if run["company_id"] != opp.company_id:
                raise security.ScopeError("Opportunity company does not match run company")
            if cur.execute("select 1 from opportunities where opportunity_id = %s", (opp.opportunity_id,)).fetchone():
                return  # idempotent
            cur.execute(
                """insert into opportunities (opportunity_id, run_id, company_id, lever, title, baseline_metric,
                     baseline_value, ebitda_flow_through, flow_through_rule, scenarios, annual_run_cost, one_time_cost,
                     confidence, rationale, assumptions, metric_params, proposer)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    opp.opportunity_id,
                    opp.run_id,
                    opp.company_id,
                    opp.lever.value,
                    opp.title,
                    opp.baseline_metric,
                    opp.baseline_value,
                    opp.ebitda_flow_through,
                    flow_through_rule,
                    Jsonb(scen),
                    opp.annual_run_cost,
                    opp.one_time_cost,
                    opp.confidence.value,
                    opp.rationale,
                    Jsonb(opp.assumptions),
                    Jsonb(opp.metric_params),
                    proposer,
                ),
            )
            for eid in opp.evidence_ids:
                self._require_evidence(cur, opp.company_id, eid)
                cur.execute(
                    "insert into opportunity_evidence (opportunity_id, evidence_id) values (%s, %s)",
                    (opp.opportunity_id, eid),
                )

    @staticmethod
    def _opp(r: dict[str, Any]) -> Opportunity:
        sc = r["scenarios"]
        return Opportunity(
            opportunity_id=str(r["opportunity_id"]),
            run_id=str(r["run_id"]),
            company_id=r["company_id"],
            lever=r["lever"],
            title=r["title"],
            baseline_metric=r["baseline_metric"],
            baseline_value=r["baseline_value"],
            ebitda_flow_through=r["ebitda_flow_through"],
            low=ScenarioInputs(**sc["low"]),
            base=ScenarioInputs(**sc["base"]),
            high=ScenarioInputs(**sc["high"]),
            annual_run_cost=r["annual_run_cost"],
            one_time_cost=r["one_time_cost"],
            confidence=r["confidence"],
            rationale=r["rationale"],
            assumptions=r["assumptions"],
            evidence_ids=sorted(r["ev"]),
            metric_params=r["metric_params"],
        )

    _OPP_SQL = """select o.*, coalesce(array_agg(oe.evidence_id::text) filter (where oe.evidence_id is not null), '{}') ev
                  from opportunities o left join opportunity_evidence oe on oe.opportunity_id = o.opportunity_id"""

    def get_opportunity(self, company_id: str, opportunity_id: str) -> Opportunity:
        security.require(company_id)
        with self._tx() as cur:
            row = cur.execute(
                self._OPP_SQL + " where o.company_id = %s and o.opportunity_id = %s group by o.opportunity_id",
                (company_id, opportunity_id),
            ).fetchone()
        if not row:
            raise NotFound(opportunity_id)
        return self._opp(row)

    def list_opportunities(self, run_id: str) -> list[Opportunity]:
        self.get_run(run_id)
        with self._tx() as cur:
            rows = cur.execute(
                self._OPP_SQL + " where o.run_id = %s group by o.opportunity_id "
                "order by o.created_at, o.opportunity_id",
                (run_id,),
            ).fetchall()
        return [self._opp(r) for r in rows]

    def save_value_case(self, company_id: str, run_id: str, vc: ValueCase, policy_version: str) -> None:
        security.require(company_id)
        with self._tx() as cur:
            cur.execute(
                "update value_cases set superseded_at = now() where opportunity_id = %s and superseded_at is null",
                (vc.opportunity_id,),
            )
            cur.execute(
                """insert into value_cases (value_case_id, opportunity_id, run_id, company_id, annual_ebitda_low,
                     annual_ebitda_base, annual_ebitda_high, one_time_cost, ev_multiple, ev_impact_base, calc_version,
                     inputs_hash, policy_version) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()),
                    vc.opportunity_id,
                    run_id,
                    company_id,
                    vc.annual_ebitda_low,
                    vc.annual_ebitda_base,
                    vc.annual_ebitda_high,
                    vc.one_time_cost,
                    vc.ev_multiple,
                    vc.ev_impact_base,
                    vc.calc_version,
                    vc.inputs_hash,
                    policy_version,
                ),
            )

    @staticmethod
    def _vc(r: dict[str, Any]) -> ValueCase:
        return ValueCase(
            opportunity_id=str(r["opportunity_id"]),
            annual_ebitda_low=r["annual_ebitda_low"],
            annual_ebitda_base=r["annual_ebitda_base"],
            annual_ebitda_high=r["annual_ebitda_high"],
            one_time_cost=r["one_time_cost"],
            ev_multiple=r["ev_multiple"],
            ev_impact_base=r["ev_impact_base"],
            calc_version=r["calc_version"],
            inputs_hash=r["inputs_hash"],
        )

    def get_value_case(self, company_id: str, opportunity_id: str) -> ValueCase:
        security.require(company_id)
        with self._tx() as cur:
            row = cur.execute(
                "select * from value_cases where company_id = %s and opportunity_id = %s and superseded_at is null",
                (company_id, opportunity_id),
            ).fetchone()
        if not row:
            raise NotFound(f"No value case for {opportunity_id}")
        return self._vc(row)

    def list_value_cases(self, run_id: str) -> list[ValueCase]:
        self.get_run(run_id)
        with self._tx() as cur:
            rows = cur.execute(
                "select * from value_cases where run_id = %s and superseded_at is null order by created_at", (run_id,)
            ).fetchall()
        return [self._vc(r) for r in rows]

    def save_priorities(self, run_id: str, company_id: str, scores: list[PriorityScore]) -> None:
        security.require(company_id)
        with self._tx() as cur:
            cur.execute("delete from priority_scores where run_id = %s", (run_id,))
            for p in scores:
                cur.execute(
                    """insert into priority_scores (run_id, opportunity_id, company_id, rank, score, components,
                         run_rate_ebitda_base, in_year_ebitda_base, start_month)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        run_id,
                        p.opportunity_id,
                        company_id,
                        p.rank,
                        p.score,
                        Jsonb({k: str(v) for k, v in p.components.items()}),
                        p.run_rate_ebitda_base,
                        p.in_year_ebitda_base,
                        p.start_month,
                    ),
                )

    def list_priorities(self, run_id: str) -> list[PriorityScore]:
        with self._tx() as cur:
            rows = cur.execute("select * from priority_scores where run_id = %s order by rank", (run_id,)).fetchall()
        return [
            PriorityScore(
                opportunity_id=str(r["opportunity_id"]),
                rank=r["rank"],
                score=r["score"],
                components=r["components"],
                run_rate_ebitda_base=r["run_rate_ebitda_base"],
                in_year_ebitda_base=r["in_year_ebitda_base"],
                start_month=r["start_month"],
            )
            for r in rows
        ]

    # plans / approvals -------------------------------------------------------------------------------------
    def save_plan(self, record: PlanRecord) -> None:
        security.require(record.company_id)
        with self._tx() as cur:
            cur.execute(
                "update plans set status = 'superseded' where run_id = %s and status = 'proposed' and plan_id <> %s",
                (record.run_id, record.plan_id),
            )
            cur.execute(
                """insert into plans (plan_id, run_id, company_id, status, plan, approved_plan, created_at, approved_at)
                   values (%s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (plan_id) do update set status = excluded.status, plan = excluded.plan""",
                (
                    record.plan_id,
                    record.run_id,
                    record.company_id,
                    record.status,
                    Jsonb(record.plan),
                    Jsonb(record.approved_plan) if record.approved_plan is not None else None,
                    record.created_at,
                    record.approved_at,
                ),
            )

    @staticmethod
    def _plan(r: dict[str, Any]) -> PlanRecord:
        return PlanRecord(
            plan_id=str(r["plan_id"]),
            run_id=str(r["run_id"]),
            company_id=r["company_id"],
            status=r["status"],
            plan=r["plan"],
            approved_plan=r["approved_plan"],
            created_at=r["created_at"],
            approved_at=r["approved_at"],
        )

    def get_plan(self, plan_id: str) -> PlanRecord:
        with self._tx() as cur:
            row = cur.execute("select * from plans where plan_id = %s", (plan_id,)).fetchone()
        if not row:
            raise NotFound(plan_id)
        return self._plan(row)

    def latest_plan(self, run_id: str) -> PlanRecord | None:
        self.get_run(run_id)
        with self._tx() as cur:
            row = cur.execute(
                "select * from plans where run_id = %s and status <> 'superseded' order by created_at desc limit 1",
                (run_id,),
            ).fetchone()
        return self._plan(row) if row else None

    def update_plan_status(self, plan_id: str, status: str, approved_plan: dict[str, Any] | None = None) -> None:
        with self._tx() as cur:
            if status == "approved":
                n = cur.execute(
                    "update plans set status = %s, approved_plan = coalesce(%s, plan), approved_at = now() "
                    "where plan_id = %s",
                    (status, Jsonb(approved_plan) if approved_plan else None, plan_id),
                ).rowcount
            else:
                n = cur.execute("update plans set status = %s where plan_id = %s", (status, plan_id)).rowcount
        if n == 0:
            raise NotFound(plan_id)

    @staticmethod
    def _appr(r: dict[str, Any]) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=str(r["approval_id"]),
            run_id=str(r["run_id"]),
            company_id=r["company_id"],
            artifact_type=r["artifact_type"],
            artifact_id=str(r["artifact_id"]),
            decision=ApprovalDecision(r["decision"]) if r["decision"] else None,
            decided_by=r["decided_by"],
            rationale=r["rationale"],
            edits=r["edits"],
            diff=r["diff"],
            requested_at=r["requested_at"],
            decided_at=r["decided_at"],
            escalated_at=r["escalated_at"],
        )

    def create_approval_request(
        self, run_id: str, company_id: str, artifact_type: str, artifact_id: str
    ) -> ApprovalRecord:
        security.require(company_id)
        with self._tx() as cur:
            row = cur.execute(
                "select * from approvals where run_id = %s and artifact_id = %s and decision is null",
                (run_id, artifact_id),
            ).fetchone()
            if row:
                return self._appr(row)
            row = cur.execute(
                """insert into approvals (approval_id, run_id, company_id, artifact_type, artifact_id)
                   values (%s, %s, %s, %s, %s) returning *""",
                (str(uuid.uuid4()), run_id, company_id, artifact_type, artifact_id),
            ).fetchone()
        return self._appr(row)

    def record_decision(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        rationale: str | None,
        edits: dict[str, Any] | None = None,
        diff: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        with self._tx() as cur:
            row = cur.execute(
                """update approvals set decision = %s, decided_by = %s, rationale = %s, edits = %s, diff = %s,
                     decided_at = now() where approval_id = %s and decision is null returning *""",
                (decision.value, decided_by, rationale, Jsonb(edits or {}), Jsonb(diff or {}), approval_id),
            ).fetchone()
            if row:
                cur.execute(
                    "update workflow_runs set resume_requested_at = now(), updated_at = now() "
                    "where run_id = %s and coalesce(params->>'mode', 'automated') <> 'interactive'",
                    (row["run_id"],),
                )
                return self._appr(row)
            exists = cur.execute("select decision from approvals where approval_id = %s", (approval_id,)).fetchone()
        if exists:
            raise Conflict(f"Approval {approval_id} already decided ({exists['decision']})")
        raise NotFound(approval_id)

    def latest_approval(self, run_id: str) -> ApprovalRecord | None:
        items = self.list_approvals(run_id)
        return items[-1] if items else None

    def list_approvals(self, run_id: str) -> list[ApprovalRecord]:
        self.get_run(run_id)
        with self._tx() as cur:
            rows = cur.execute("select * from approvals where run_id = %s order by requested_at", (run_id,)).fetchall()
        return [self._appr(r) for r in rows]

    def pending_approvals(self) -> list[ApprovalRecord]:
        with self._tx() as cur:
            rows = cur.execute("select * from approvals where decision is null order by requested_at").fetchall()
        return [self._appr(r) for r in rows]

    def mark_escalated(self, approval_id: str) -> None:
        with self._tx() as cur:
            if (
                cur.execute("update approvals set escalated_at = now() where approval_id = %s", (approval_id,)).rowcount
                == 0
            ):
                raise NotFound(approval_id)

    # audit -------------------------------------------------------------------------------------------------
    def append_audit(self, event: AuditEvent) -> None:
        security.require(event.company_id)
        with self._tx() as cur:
            cur.execute(
                """insert into audit_events (run_id, company_id, step, actor, event_type, payload, created_at)
                   values (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    event.run_id,
                    event.company_id,
                    event.step,
                    event.actor,
                    event.event_type,
                    Jsonb(event.payload),
                    event.created_at,
                ),
            )

    def list_audit(self, *, run_id: str | None = None, company_id: str | None = None) -> list[AuditEvent]:
        if company_id:
            security.require(company_id)
        q, args = "select * from audit_events where true", []
        if run_id:
            q += " and run_id = %s"
            args.append(run_id)
        if company_id:
            q += " and company_id = %s"
            args.append(company_id)
        with self._tx() as cur:
            rows = cur.execute(q + " order by event_id", args).fetchall()
        return [
            AuditEvent(
                run_id=_s(r["run_id"]),
                company_id=r["company_id"],
                step=r["step"],
                actor=r["actor"],
                event_type=r["event_type"],
                payload=r["payload"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # KPIs --------------------------------------------------------------------------------------------------
    def save_kpi_definitions(self, defs: list[KpiDefinition]) -> None:
        for d in defs:
            security.require(d.company_id)
        with self._tx() as cur:
            for d in defs:
                cur.execute(
                    "update kpi_definitions set active = false where company_id = %s and metric = %s and "
                    "metric_params = %s and active and kpi_id <> %s",
                    (d.company_id, d.metric, Jsonb(d.metric_params), d.kpi_id),
                )
                cur.execute(
                    """insert into kpi_definitions (kpi_id, company_id, plan_id, run_id, metric, metric_params,
                         description, baseline, day_100_target, run_rate_target, direction, cadence_days, source,
                         evidence_ids, start_date, active, created_at)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on conflict (kpi_id) do update set active = excluded.active""",
                    (
                        d.kpi_id,
                        d.company_id,
                        d.plan_id,
                        d.run_id,
                        d.metric,
                        Jsonb(d.metric_params),
                        d.description,
                        d.baseline,
                        d.day_100_target,
                        d.run_rate_target,
                        d.direction,
                        d.cadence_days,
                        d.source,
                        Jsonb(d.evidence_ids),
                        d.start_date,
                        d.active,
                        d.created_at,
                    ),
                )

    def list_kpi_definitions(self, company_id: str, active_only: bool = True) -> list[KpiDefinition]:
        security.require(company_id)
        q = "select * from kpi_definitions where company_id = %s" + (" and active" if active_only else "")
        with self._tx() as cur:
            rows = cur.execute(q + " order by kpi_id", (company_id,)).fetchall()
        return [
            KpiDefinition(**{**r, "kpi_id": str(r["kpi_id"]), "plan_id": str(r["plan_id"]), "run_id": str(r["run_id"])})
            for r in rows
        ]

    def add_kpi_observation(self, obs: KpiObservation) -> None:
        security.require(obs.company_id)
        with self._tx() as cur:
            cur.execute(
                """insert into kpi_observations (observation_id, kpi_id, company_id, observed_at, period_end, value,
                     target, status, variance, evidence_ids) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    obs.observation_id,
                    obs.kpi_id,
                    obs.company_id,
                    obs.observed_at,
                    obs.period_end,
                    obs.value,
                    obs.target,
                    obs.status,
                    obs.variance,
                    Jsonb(obs.evidence_ids),
                ),
            )

    def list_kpi_observations(self, company_id: str, kpi_id: str | None = None) -> list[KpiObservation]:
        security.require(company_id)
        q, args = "select * from kpi_observations where company_id = %s", [company_id]
        if kpi_id:
            q += " and kpi_id = %s"
            args.append(kpi_id)
        with self._tx() as cur:
            rows = cur.execute(q + " order by kpi_id, observed_at", args).fetchall()
        return [
            KpiObservation(**{**r, "observation_id": str(r["observation_id"]), "kpi_id": str(r["kpi_id"])})
            for r in rows
        ]

    def add_kpi_alert(self, alert: KpiAlert) -> None:
        security.require(alert.company_id)
        with self._tx() as cur:
            cur.execute(
                """insert into kpi_alerts (alert_id, kpi_id, company_id, observation_id, rule, detail, created_at)
                           values (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    alert.alert_id,
                    alert.kpi_id,
                    alert.company_id,
                    alert.observation_id,
                    alert.rule,
                    alert.detail,
                    alert.created_at,
                ),
            )

    def list_kpi_alerts(self, company_id: str) -> list[KpiAlert]:
        security.require(company_id)
        with self._tx() as cur:
            rows = cur.execute(
                "select * from kpi_alerts where company_id = %s order by created_at", (company_id,)
            ).fetchall()
        return [
            KpiAlert(
                **{
                    **r,
                    "alert_id": str(r["alert_id"]),
                    "kpi_id": str(r["kpi_id"]),
                    "observation_id": str(r["observation_id"]),
                }
            )
            for r in rows
        ]

    def add_notification(self, n: Notification) -> None:
        security.require(n.company_id)
        with self._tx() as cur:
            cur.execute(
                """insert into notifications (notification_id, company_id, channel, subject, body, created_at,
                             delivered_at, status) values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing""",
                (n.notification_id, n.company_id, n.channel, n.subject, n.body, n.created_at, n.delivered_at, n.status),
            )

    def claim_notification(self, n: Notification, owner: str) -> bool:
        self.add_notification(n)
        with self._tx() as cur:
            row = cur.execute(
                "update notifications set locked_by = %s, locked_at = now() "
                "where notification_id = %s and status <> 'delivered' "
                "and (locked_by is null or locked_at < now() - interval '5 minutes') "
                "returning notification_id",
                (owner, n.notification_id),
            ).fetchone()
        return row is not None

    def finish_notification(self, notification_id: str, owner: str, *, delivered: bool) -> None:
        with self._tx() as cur:
            changed = cur.execute(
                "update notifications set status = %s, "
                "delivered_at = case when %s then now() else null end, "
                "locked_by = null, locked_at = null "
                "where notification_id = %s and locked_by = %s",
                ("delivered" if delivered else "pending", delivered, notification_id, owner),
            ).rowcount
            if not changed:
                raise LeaseLost(notification_id)

    def list_notifications(self, company_id: str) -> list[Notification]:
        security.require(company_id)
        with self._tx() as cur:
            rows = cur.execute(
                "select * from notifications where company_id = %s order by created_at", (company_id,)
            ).fetchall()
        return [Notification(**{**r, "notification_id": str(r["notification_id"])}) for r in rows]

    # deletion ----------------------------------------------------------------------------------------------
    def delete_company_data(self, company_id: str) -> dict[str, int]:
        security.require(company_id)
        # Evidence objects first: if object storage fails, the database is untouched and offboarding can be re-run
        # (both deletions are idempotent). The reverse order could leave orphaned evidence with no record of it.
        counts: dict[str, int] = {"evidence_objects": self.evidence_store.delete_company(company_id)}
        with self._tx() as cur:
            # Serialize offboarding with grants, custody and finance decisions.
            cur.execute("select company_id from companies where company_id=%s for update", (company_id,))
            counts["private_source_bytes"] = cur.execute(
                "select coalesce(sum(octet_length(source_bytes)),0) as n from private_intakes where company_id=%s",
                (company_id,),
            ).fetchone()["n"]
            # Individual revisions/receipts cannot be deleted by pvc_app. Approved
            # whole-company offboarding cascades from the existing company deletion.
            for table in (
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
                counts[table] = cur.execute(
                    f"select count(*) as n from {table} where company_id=%s", (company_id,)
                ).fetchone()["n"]
            for table in (
                "kpi_alerts",
                "kpi_observations",
                "kpi_definitions",
                "notifications",
                "approvals",
                "priority_scores",
                "value_cases",
            ):
                counts[table] = cur.execute(f"delete from {table} where company_id = %s", (company_id,)).rowcount
            cur.execute("delete from plans where company_id = %s", (company_id,))
            counts["opportunities"] = cur.execute(
                "delete from opportunities where company_id = %s", (company_id,)
            ).rowcount
            counts["findings"] = cur.execute("delete from findings where company_id = %s", (company_id,)).rowcount
            counts["evidence"] = cur.execute("delete from evidence where company_id = %s", (company_id,)).rowcount
            counts["runs"] = cur.execute("delete from workflow_runs where company_id = %s", (company_id,)).rowcount
            cur.execute("delete from companies where company_id = %s", (company_id,))
        return counts
