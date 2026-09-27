"""PVC-015 and PVC-059: contract and tool schemas are snapshot-tested; tool descriptions meet a quality bar.

Regenerate after a reviewed change with:  PVC_UPDATE_SNAPSHOTS=1 pytest tests/test_snapshots.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anyio
import pytest
from mcp import Client

from pe_value_os.domain import kpi_models, models, project_models, runs, source_models
from pe_value_os.mcp_server import build_server

SNAP = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("PVC_UPDATE_SNAPSHOTS") == "1"

CONTRACTS = {
    "EvidenceRef": models.EvidenceRef,
    "Finding": models.Finding,
    "AuditEvent": models.AuditEvent,
    "OpportunityProposal": project_models.OpportunityProposal,
    "Opportunity": project_models.Opportunity,
    "ValueCase": project_models.ValueCase,
    "PriorityScore": project_models.PriorityScore,
    "Plan": project_models.Plan,
    "KpiDefinition": kpi_models.KpiDefinition,
    "KpiObservation": kpi_models.KpiObservation,
    "KpiAlert": kpi_models.KpiAlert,
    "Notification": kpi_models.Notification,
    "RunRecord": runs.RunRecord,
    "ApprovalRecord": runs.ApprovalRecord,
    "PlanRecord": runs.PlanRecord,
    "CompanyProfile": source_models.CompanyProfile,
    **{f"source.{k.value}": t for k, t in source_models.RECORD_TYPES.items()},
}


def check(name: str, current: dict) -> None:
    path = SNAP / f"{name}.json"
    text = json.dumps(current, indent=2, sort_keys=True) + "\n"
    if UPDATE or not path.exists():
        SNAP.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        if not UPDATE:
            pytest.fail(f"Created missing snapshot {path.name}; review and commit it")
        return
    assert path.read_text(encoding="utf-8") == text, (
        f"Schema for {name} changed. If intended, run PVC_UPDATE_SNAPSHOTS=1 and follow docs/data_contracts.md"
    )


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_contract_schema_snapshot(name):
    check(f"contract.{name}", CONTRACTS[name].model_json_schema())


def _tools():
    async def go():
        async with Client(build_server()) as c:
            return (await c.list_tools()).tools

    return anyio.run(go)


def test_tool_schema_snapshot():
    tools = {
        t.name: {"description": t.description, "input": t.input_schema, "output": t.output_schema} for t in _tools()
    }
    check("tools", tools)


def test_tool_descriptions_quality():
    for t in _tools():
        d = (t.description or "").strip()
        assert len(d) >= 20, f"{t.name}: description too short"
        assert d.endswith((".", ")")), f"{t.name}: description should be full sentences"
        props = t.input_schema.get("properties", {})
        if "company_id" in props or "run_id" in props or t.name in ("healthcheck", "get_benchmarks"):
            continue
        pytest.fail(f"{t.name}: every data tool must be scoped by company_id or run_id")
    by = {t.name: (t.description or "") for t in _tools()}
    assert "fractions" in by["propose_opportunity"] and "server fills in the baseline" in by["propose_opportunity"]
    assert "EBITDA" in by["size_value_case"] and "never from the caller" in by["size_value_case"]
    assert "no tool can approve" in by["request_approval"]
    assert "Never returns any single company" in by["get_benchmarks"]
