"""Regression coverage for tenant ingestion, credential routing and exception redaction."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import ClassVar

import httpx
import jwt
import pytest

from pe_value_os import auth, observability, security
from pe_value_os.adapters.base import SourceError, StagedEvidence
from pe_value_os.adapters.csv_export import CsvExportAdapter
from pe_value_os.adapters.evidence_store import ImmutableEvidenceError, S3EvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.sources import ApiClient, dataset_from_records
from pe_value_os.adapters.warehouse import WarehouseAdapter
from pe_value_os.domain.source_models import DatasetKind
from pe_value_os.egress import checked_client
from tests.helpers import make_data


def export(root, filename="pnl.csv", content=None):
    company = root / "a"
    company.mkdir()
    (company / "company.json").write_text(make_data(company_id="a").profile.model_dump_json())
    (company / "manifest.json").write_text(
        json.dumps(
            {
                "reference_date": "2026-02-10",
                "datasets": {"pnl": {"file": filename, "as_of": "2026-02-01"}},
            }
        )
    )
    if content is not None:
        (company / "pnl.csv").write_text(content)
    return company


@pytest.mark.parametrize("tenant,amount", [("b", "10"), ("b", "invalid"), ("", "10")])
@pytest.mark.parametrize("adapter_type", [CsvExportAdapter, FixtureAdapter])
def test_foreign_raw_csv_rows_publish_nothing(tmp_path, tenant, amount, adapter_type):
    export(
        tmp_path, content=f"company_id,month,account,amount,currency\n{tenant},2026-01-01,cogs_hosting,{amount},USD\n"
    )
    sink = StagedEvidence()
    with pytest.raises(SourceError):
        adapter_type(tmp_path).load("a", sink)
    assert sink.records == []


def test_manifest_escape_and_symlink_publish_nothing(tmp_path):
    company = export(tmp_path, filename="../outside.csv")
    (tmp_path / "outside.csv").write_text("foreign secret")
    sink = StagedEvidence()
    with pytest.raises(SourceError, match="escapes"):
        CsvExportAdapter(tmp_path).load("a", sink)
    assert not sink.records
    # The link target must be checked even when the manifest itself stays in the tenant directory.
    (company / "manifest.json").write_text(json.dumps({"datasets": {"pnl": {"file": "linked.csv"}}}))
    try:
        (company / "linked.csv").symlink_to(tmp_path / "outside.csv")
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or elevated privilege")
    with pytest.raises(SourceError, match="escapes"):
        CsvExportAdapter(tmp_path).load("a", sink)
    assert not sink.records


def test_later_foreign_dataset_discards_previously_valid_staged_sources(tmp_path):
    company = export(tmp_path, content="company_id,month,account,amount,currency\na,2026-01-01,cogs_hosting,10,USD\n")
    manifest = json.loads((company / "manifest.json").read_text())
    manifest["datasets"]["customers"] = {"file": "customers.csv", "as_of": "2026-02-01"}
    (company / "manifest.json").write_text(json.dumps(manifest))
    (company / "customers.csv").write_text("company_id,name\nb,foreign secret\n")
    sink = StagedEvidence()
    with pytest.raises(SourceError):
        CsvExportAdapter(tmp_path).load("a", sink)
    assert not sink.records


def test_dataset_mapping_never_relabels_foreign_invalid_rows():
    sink = StagedEvidence()
    with pytest.raises(SourceError):
        dataset_from_records(
            DatasetKind.PNL,
            "a",
            [{"company_id": "b", "amount": "invalid"}],
            source_uri="test://pnl",
            as_of=None,
            sink=sink,
        )
    assert not sink.records


@pytest.mark.parametrize("foreign_profile", [True, False])
def test_warehouse_rejects_foreign_profile_or_rows_before_publishing(monkeypatch, foreign_profile):
    adapter = WarehouseAdapter.__new__(WarehouseAdapter)
    adapter.schema, adapter.datasets = "pvc", [DatasetKind.PNL]
    monkeypatch.setattr(adapter, "_exists", lambda name: name in {"pvc_company_profile", "pvc_pnl"})

    def query(sql, params):
        if "profile_json" in sql:
            return [
                {
                    "profile_json": make_data(company_id="b" if foreign_profile else "a").profile.model_dump_json(),
                    "reference_date": date(2026, 2, 10),
                }
            ]
        return [{"company_id": "b", "amount": "invalid"}]

    monkeypatch.setattr(adapter, "_query", query)
    sink = StagedEvidence()
    with pytest.raises(SourceError):
        adapter.load("a", sink)
    assert not sink.records


@pytest.mark.parametrize(
    "overrides",
    [
        {"pvc_companies": "abc"},
        {"pvc_companies": ["a,b"]},
        {"pvc_companies": [1]},
        {"pvc_companies": ["../a"]},
        {"pvc_companies": [" a"]},
        {"pvc_roles": "approver"},
        {"pvc_roles": [True]},
        {"scope": {"pvc.read": True}},
        {"pvc_principal_type": []},
    ],
)
def test_noncanonical_authorization_claims_rejected(overrides):
    with pytest.raises(jwt.InvalidTokenError):
        auth.principal_from_claims({"sub": "user", "pvc_companies": ["a"], **overrides})


def test_principal_rejects_comma_ambiguous_company_scope():
    with pytest.raises(ValueError):
        security.system_principal("a,b")


def test_vendor_pagination_never_sends_credentials_to_second_allowed_host(monkeypatch):
    monkeypatch.setenv("PVC_EGRESS_ALLOWLIST", "vendor.test,other.test")
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(200, json={})

    api = ApiClient("https://vendor.test", {"Authorization": "Bearer fixture"}, transport=httpx.MockTransport(response))
    try:
        api.get("https://vendor.test/page/2")
        for url in (
            "https://other.test/page",
            "//other.test/page",
            "http://vendor.test/page",
            "https://vendor.test:444/page",
        ):
            with pytest.raises(SourceError):
                api.get(url)
    finally:
        api.close()
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer fixture"


def test_jwks_redirect_is_checked_before_destination_request(monkeypatch):
    monkeypatch.setenv("PVC_EGRESS_ALLOWLIST", "idp.test")
    requests = []

    def response(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://untrusted.test/keys"})

    monkeypatch.setattr(
        auth, "checked_client", lambda **kw: checked_client(transport=httpx.MockTransport(response), **kw)
    )
    with pytest.raises(jwt.PyJWKClientConnectionError):
        auth.CheckedJWKClient("https://idp.test/keys").fetch_data()
    assert requests == ["https://idp.test/keys"]


def test_exported_exception_has_no_message_stack_or_status_description(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(observability, "_tracer", lambda: provider.get_tracer("test"))
    secret = "customer-secret-928374"
    with pytest.raises(RuntimeError):
        with observability.span("test", detail=secret):
            raise RuntimeError(secret)
    (span,) = exporter.get_finished_spans()
    assert secret not in span.to_json()
    assert not span.events and span.status.description is None
    assert span.attributes["error_type"] == "RuntimeError"
    provider.shutdown()


@pytest.mark.parametrize("same_content", [True, False])
def test_s3_competing_create_is_conditional_and_verified(same_content):
    class Conflict(Exception):
        response: ClassVar[dict] = {"Error": {"Code": "PreconditionFailed"}}

    class Missing(Conflict):
        response: ClassVar[dict] = {"Error": {"Code": "NoSuchKey"}}

    class Client:
        class exceptions:
            ClientError = Conflict

        def __init__(self):
            self.created = False

        def head_object(self, **kw):
            if not self.created:
                raise Missing()
            return {"Metadata": {"sha256": hashlib.sha256(b"same" if same_content else b"other").hexdigest()}}

        def put_object(self, **kw):
            assert kw["IfNoneMatch"] == "*"
            self.created = True
            raise Conflict()

    store = S3EvidenceStore("bucket", client=Client())
    if same_content:
        assert store.put_original("a", "ev", b"same") == "evidence/a/ev/original"
    else:
        with pytest.raises(ImmutableEvidenceError):
            store.put_original("a", "ev", b"same")
