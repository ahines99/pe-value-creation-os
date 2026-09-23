"""PVC-093/094/095/100/101/102: logs, redaction, traces, metrics, egress allow-list, secret hygiene."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import anyio
import httpx
import pytest

from pe_value_os import approvals, observability, security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.domain.runs import ApprovalDecision
from pe_value_os.egress import EgressDenied, check_url, checked_client
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "companies"


def _run(tmp_path, cid="beacon-pricing"):
    ctx = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev")), adapter=FixtureAdapter(), policy=get_policy()
    )
    with security.principal_scope(security.system_principal(cid)):
        rec, _ = primary.start(ctx, cid, "human:t")
        st = anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        if st.status.value != "awaiting_approval":
            return ctx, rec.run_id
        approvals.decide(
            ctx,
            rec.run_id,
            security.Principal(
                subject="human:ap", companies=frozenset({cid}), roles=frozenset({"approver"}), principal_type="human"
            ),
            ApprovalDecision.APPROVED,
            rationale="ok",
        )
        anyio.run(lambda: primary.resume(ctx, rec.run_id, "system:worker", backoff_s=0))
    return ctx, rec.run_id


def test_logs_are_json_with_context_and_contain_no_sensitive_values(tmp_path):
    buf = io.StringIO()
    observability.configure_logging(stream=buf)
    try:
        _, run_id = _run(tmp_path, "delta-broken")
        _run(tmp_path / "b", "beacon-pricing")
    finally:
        observability.configure_logging(stream=io.StringIO())
    lines = [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines and all("event" in x and "timestamp" in x for x in lines)
    assert any(x.get("run_id") == run_id and x.get("step") for x in lines)
    text = buf.getvalue()
    names = [r["name"] for r in csv.DictReader((FIX / "beacon-pricing" / "customers.csv").open(encoding="utf-8"))]
    assert not any(n in text for n in names[:200]), "customer names leaked into logs"
    arr_values = {r["arr"] for r in csv.DictReader((FIX / "beacon-pricing" / "arr.csv").open(encoding="utf-8"))}
    assert not any(v in text for v in list(arr_values)[:500] if len(v) >= 7), "ARR amounts leaked into logs"
    docs = (FIX / "delta-broken" / "documents.csv").read_text(encoding="utf-8")
    assert "IMPORTANT INSTRUCTIONS" in docs and "IMPORTANT INSTRUCTIONS" not in text


def test_redaction_hashes_unknown_fields():
    out = observability.redact({"run_id": "r1", "customer_name": "Jane Doe", "amount": 12345.67, "count": 3})
    assert out["run_id"] == "r1" and out["count"] == 3
    assert out["customer_name"].startswith("h:") and "Jane" not in out["customer_name"]
    assert out["amount"].startswith("h:")


def test_traces_follow_run_step_branch_tool_hierarchy(tmp_path):
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        pytest.skip("tracer provider already installed by another test")
    observability.configure_tracing(exporter)
    _, run_id = _run(tmp_path)
    spans = exporter.get_finished_spans()
    by_name = {s.name: s for s in spans}
    assert {"run", "step:intake", "step:diagnostics", "branch:pricing"} <= set(by_name)
    run_span = next(s for s in spans if s.name == "run" and s.attributes.get("run_id") == run_id)
    step = next(s for s in spans if s.name == "step:intake" and s.attributes.get("run_id") == run_id)
    assert step.parent is not None and step.parent.span_id == run_span.context.span_id
    branch = by_name["branch:pricing"]
    assert branch.parent is not None


def test_metrics_record_runs_steps_and_approvals(tmp_path):
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    observability.configure_metrics(reader)
    try:
        _run(tmp_path)
        data = reader.get_metrics_data()
        names = {m.name for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
        assert {"pvc.runs", "pvc.step.duration", "pvc.approval.turnaround", "pvc.approval.decisions"} <= names
    finally:
        observability._metrics = None


def test_egress_allow_list(monkeypatch):
    monkeypatch.setenv("PVC_EGRESS_ALLOWLIST", "hooks.slack.com,*.example-idp.com")
    check_url("https://api.anthropic.com/v1/messages")
    check_url("https://hooks.slack.com/services/x")
    check_url("https://login.example-idp.com/.well-known/jwks.json")
    for bad in (
        "https://evil.example.com",
        "http://169.254.169.254/latest/meta-data",
        "https://api.anthropic.com.evil.io",
    ):
        with pytest.raises(EgressDenied):
            check_url(bad)
    sent = []
    transport = httpx.MockTransport(lambda req: sent.append(req) or httpx.Response(200))
    with checked_client(transport=transport) as c:
        c.get("https://hooks.slack.com/ok")
        with pytest.raises(EgressDenied):
            c.get("https://exfil.example.net/steal")
    assert [str(r.url) for r in sent] == ["https://hooks.slack.com/ok"]


SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
]


def test_no_secrets_in_skills_prompts_policy_or_source():
    roots = [ROOT / "skills", ROOT / "src", ROOT / "evals", ROOT / ".claude-plugin"]
    hits = []
    for root in roots:
        for f in root.rglob("*"):
            if f.is_file() and f.suffix in {".md", ".py", ".toml", ".json", ".sql", ".yml", ".yaml"}:
                text = f.read_text(encoding="utf-8", errors="ignore")
                hits += [f"{f.relative_to(ROOT)}: {p.pattern}" for p in SECRET_PATTERNS if p.search(text)]
    assert hits == []


def test_config_reads_secrets_only_from_environment():
    src = (ROOT / "src" / "pe_value_os").rglob("*.py")
    offenders = [str(f) for f in src if re.search(r"ANTHROPIC_API_KEY\s*=\s*['\"]", f.read_text(encoding="utf-8"))]
    assert offenders == []
