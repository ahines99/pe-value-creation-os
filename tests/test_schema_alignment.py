"""PVC-010: Pydantic contracts and PostgreSQL columns stay aligned."""

import pytest

from pe_value_os.domain.kpi_models import KpiAlert, KpiDefinition, KpiObservation, Notification
from pe_value_os.domain.models import AuditEvent, EvidenceRef, Finding
from pe_value_os.domain.project_models import Opportunity, ValueCase

pytestmark = pytest.mark.postgres

# model -> (table, fields stored elsewhere or derived, columns that are storage-only)
CASES = [
    (EvidenceRef, "evidence", {"metadata"}, {"storage_key", "size_bytes", "metadata"}),
    (Finding, "findings", {"evidence_ids", "contradicting_evidence_ids"}, {"created_at"}),
    (
        Opportunity,
        "opportunities",
        {"low", "base", "high", "evidence_ids"},
        {"scenarios", "flow_through_rule", "proposer", "created_at"},
    ),
    (
        ValueCase,
        "value_cases",
        set(),
        {"value_case_id", "run_id", "company_id", "policy_version", "superseded_at", "created_at"},
    ),
    (AuditEvent, "audit_events", set(), {"event_id"}),
    (KpiDefinition, "kpi_definitions", set(), set()),
    (KpiObservation, "kpi_observations", set(), set()),
    (KpiAlert, "kpi_alerts", set(), set()),
    (Notification, "notifications", set(), {"locked_by", "locked_at"}),
]


@pytest.mark.parametrize("model,table,model_only,column_only", CASES, ids=[c[1] for c in CASES])
def test_model_fields_match_columns(pg_database, model, table, model_only, column_only):
    import psycopg

    admin_url, _ = pg_database
    with psycopg.connect(admin_url) as conn:
        cols = {
            r[0]
            for r in conn.execute(
                "select column_name from information_schema.columns where table_name = %s", (table,)
            ).fetchall()
        }
    fields = set(model.model_fields)
    assert fields - model_only == cols - column_only, (
        f"model-only: {sorted(fields - model_only - cols)}, column-only: {sorted(cols - column_only - fields)}"
    )
