"""PVC-110..118: adapter conformance suite, vendor adapters, warehouse adapter, entity resolution, freshness."""

from __future__ import annotations

import csv
import io
import json

import anyio
import pytest

from pe_value_os import security
from pe_value_os.adapters.base import SourceError, TransientSourceError
from pe_value_os.adapters.composite import CompanySources, CompositeAdapter
from pe_value_os.adapters.csv_export import CsvExportAdapter
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.hubspot_crm import HubSpotCrmAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.adapters.stripe_billing import StripeBillingAdapter
from pe_value_os.adapters.zendesk_support import ZendeskConfig, ZendeskSupportAdapter
from pe_value_os.domain import entity_resolution as er
from pe_value_os.domain.source_models import Customer, DatasetKind
from pe_value_os.egress import EgressDenied
from pe_value_os.observability import configure_logging
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext
from tests.vendor_sim import FIX, VendorSim

configure_logging(stream=io.StringIO())
CID = "beacon-pricing"


@pytest.fixture(autouse=True)
def _egress(monkeypatch):
    monkeypatch.setenv("PVC_EGRESS_ALLOWLIST", "api.stripe.com,api.hubapi.com,acme.zendesk.com")


def vendors(sim, page=50):
    t = sim.transport()
    return (
        StripeBillingAdapter("sk_test", transport=t, page_size=page),
        HubSpotCrmAdapter("pat", transport=t, page_size=page),
        ZendeskSupportAdapter("acme", "ops@x", "tok", ZendeskConfig(901, 902, {1}), transport=t),
    )


def composite(tmp_path, sim=None):
    sim = sim or VendorSim()
    root = sim.write_base_export(tmp_path / "export")
    stripe, hubspot, zendesk = vendors(sim)
    cs = CompanySources(
        base=CsvExportAdapter(root),
        sources={
            DatasetKind.INVOICES: stripe,
            DatasetKind.PRICE_BOOKS: stripe,
            DatasetKind.CONCESSIONS: stripe,
            DatasetKind.CUSTOMERS: hubspot,
            DatasetKind.CRM_OPPORTUNITIES: hubspot,
            DatasetKind.CHURN: hubspot,
            DatasetKind.SUPPORT: zendesk,
        },
        id_systems={DatasetKind.ARR: "stripe", DatasetKind.USAGE: "stripe", DatasetKind.CONTRACTS: "stripe"},
    )
    return CompositeAdapter({CID: cs}), sim


# --- conformance suite (PVC-110): every adapter must pass -------------------------------------------------------
def adapters(tmp_path, kind):
    if kind == "fixture":
        return FixtureAdapter()
    if kind == "csv_export":
        return CsvExportAdapter(FIX)
    return composite(tmp_path)[0]


@pytest.mark.parametrize("kind", ["fixture", "csv_export", "composite"])
def test_conformance(kind, tmp_path):
    adapter = adapters(tmp_path, kind)
    repo = InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev"))
    with security.principal_scope(security.system_principal(CID)):
        first = adapter.load(CID)
        repo.upsert_company(first.profile)
        d1 = adapter.load(CID, sink=repo)
        d2 = adapter.load(CID, sink=repo)
        stored = {e.evidence_id for e in repo.list_evidence(CID)}
    assert d1.company_id == CID and d1.reference_date
    for k, ds in d1.datasets.items():
        assert ds.evidence_id in stored, k  # every dataset registered as evidence
        assert ds.evidence_id == d2.datasets[k].evidence_id, k  # deterministic for identical content
        assert all(r.company_id == CID for r in ds.records), k
    required = {
        DatasetKind.PNL,
        DatasetKind.ARR,
        DatasetKind.CUSTOMERS,
        DatasetKind.INVOICES,
        DatasetKind.PRICE_BOOKS,
        DatasetKind.CONTRACTS,
        DatasetKind.CHURN,
        DatasetKind.SUPPORT,
        DatasetKind.HEADCOUNT,
    }
    assert required <= set(d1.datasets)


def test_csv_export_refuses_other_companies_rows(tmp_path):
    root = VendorSim().write_base_export(tmp_path)
    arr = root / CID / "arr.csv"
    arr.write_text(arr.read_text().replace(f"{CID},", "cedar-churn,", 1))
    with pytest.raises(SourceError, match="other companies"):
        CsvExportAdapter(root).load(CID)


# --- vendor adapters --------------------------------------------------------------------------------------------
def test_vendor_pagination_is_complete(tmp_path):
    sim = VendorSim()
    stripe, hubspot, zendesk = vendors(sim, page=7)
    s = stripe.load_datasets(CID, None)
    assert len(s[DatasetKind.INVOICES].records) == len(list(csv.DictReader((FIX / CID / "invoices.csv").open())))
    assert len(s[DatasetKind.PRICE_BOOKS].records) == len(sim.prices)
    h = hubspot.load_datasets(CID, None)
    assert len(h[DatasetKind.CUSTOMERS].records) == len(sim.hs_companies)
    z = zendesk.load_datasets(CID, None)
    assert len(z[DatasetKind.SUPPORT].records) == len(sim.tickets)
    assert sum("starting_after" in c for c in sim.calls) > 5 and sum("after=" in c for c in sim.calls) > 5
    assert len(zendesk.organizations()) == len(sim.orgs)


def test_stripe_amounts_converted_from_cents(tmp_path):
    stripe, _, _ = vendors(VendorSim())
    inv = stripe.load_datasets(CID, None)[DatasetKind.INVOICES].records
    fx = {(r["invoice_id"]): r for r in csv.DictReader((FIX / CID / "invoices.csv").open())}
    for r in inv[:50]:
        src = fx[r.invoice_id]
        assert str(r.net_amount) == src["net_amount"] and str(r.on_invoice_discount) == src["on_invoice_discount"]


@pytest.mark.parametrize("code,exc", [(429, TransientSourceError), (503, TransientSourceError), (401, SourceError)])
def test_vendor_errors_are_classified(code, exc):
    sim = VendorSim()
    sim.fail["/v1/invoices"] = code
    stripe, _, _ = vendors(sim)
    with pytest.raises(exc) as info:
        stripe.load_datasets(CID, None)
    assert (info.type is TransientSourceError) == (exc is TransientSourceError)


def test_vendor_hosts_must_be_on_egress_allow_list(monkeypatch):
    monkeypatch.setenv("PVC_EGRESS_ALLOWLIST", "api.hubapi.com")
    stripe, _, _ = vendors(VendorSim())
    with pytest.raises(EgressDenied):
        stripe.load_datasets(CID, None)


def test_zendesk_mapping():
    _, _, zendesk = vendors(VendorSim())
    recs = zendesk.load_datasets(CID, None)[DatasetKind.SUPPORT].records
    src = {int(t["ticket_id"].split("-")[-1]): t for t in csv.DictReader((FIX / CID / "support.csv").open())}
    for r in recs[:100]:
        t = src[int(r.ticket_id)]
        assert (r.category, r.tier, str(r.handle_minutes), r.severity) == (
            t["category"],
            t["tier"],
            t["handle_minutes"],
            t["severity"],
        )


# --- round trip: composite sources reproduce the fixture's value cases ------------------------------------------
def _value_cases(adapter, tmp_path):
    ctx = RunContext(repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path)), adapter=adapter, policy=get_policy())
    with security.principal_scope(security.system_principal(CID)):
        rec, _ = primary.start(ctx, CID, "t")
        st = anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        out = sorted(
            (
                o.lever.value,
                o.baseline_metric,
                json.dumps(o.metric_params),
                str(ctx.repo.get_value_case(CID, o.opportunity_id).annual_ebitda_base),
            )
            for o in ctx.repo.list_opportunities(rec.run_id)
        )
    return st, out


def test_composite_round_trip_matches_fixture(tmp_path):
    adapter, _ = composite(tmp_path)
    st_c, vc_c = _value_cases(adapter, tmp_path / "c")
    st_f, vc_f = _value_cases(FixtureAdapter(), tmp_path / "f")
    assert st_c.status == st_f.status
    assert vc_c == vc_f and vc_c
    with security.principal_scope(security.system_principal(CID)):
        data = adapter.load(CID)
    rep = data.entity_resolution
    assert rep["review_queue"] == 0 and rep["unresolved_rows"] == {} and rep["methods"]["domain"] > 0


# --- entity resolution (PVC-117) -----------------------------------------------------------------------------------
def cust(cid, name, domain):
    return Customer(
        company_id="x",
        customer_id=cid,
        name=name,
        segment="smb",
        size_band="s",
        acquisition_channel="inbound",
        first_contract_date="2025-01-01",
        domain=domain,
    )


def test_resolution_rules():
    customers = [
        cust("1", "Acme Inc", "acme.com"),
        cust("2", "Beta LLC", "beta.io"),
        cust("3", "Beta LLC", "beta.com"),
        cust("4", "Acme Holdings", "ACME.com"),
    ]
    foreign = [
        er.ForeignEntity("stripe", "cus_a", "whatever", "billing@www.acme.com"),
        er.ForeignEntity("stripe", "cus_b", "Beta, LLC", None),
        er.ForeignEntity("stripe", "cus_c", "Gamma", None),
        er.ForeignEntity("zendesk", "77", "Beta LLC", "beta.io"),
    ]
    r = er.Resolver(overrides={"stripe:cus_c": "2"}).resolve(customers, foreign)
    assert r.duplicates == {"4": "1"}  # same normalized domain
    assert r.resolve("stripe", "cus_a") == "1" and r.resolve("zendesk", "77") == "2"
    assert r.resolve("stripe", "cus_c") == "2"  # human override
    assert r.resolve("stripe", "cus_b") is None
    assert [(i.foreign_id, i.reason) for i in r.review_queue] == [("cus_b", "ambiguous_name")]


def test_name_only_match_needs_review_unless_enabled():
    customers = [cust("1", "Delta Tools Ltd", "delta.io")]
    fe = [er.ForeignEntity("stripe", "cus_d", "DELTA TOOLS", None)]
    assert er.Resolver().resolve(customers, fe).review_queue[0].reason == "name_match_needs_review"
    assert er.Resolver(accept_name_matches=True).resolve(customers, fe).resolve("stripe", "cus_d") == "1"


def test_duplicate_entities_merged_and_unresolved_flagged(tmp_path):
    data = FixtureAdapter().load("delta-broken")
    customers = data.records(DatasetKind.CUSTOMERS)
    res = er.Resolver().resolve(customers, [er.ForeignEntity("stripe", "cus_zzz", "Nobody", "nobody.example")])
    rep = er.apply(data, res, {DatasetKind.ARR: "canonical"})
    assert rep["duplicates_merged"] == 5
    assert not any(r.customer_id.endswith("-dup") for r in data.records(DatasetKind.ARR))
    data.entity_resolution = rep
    from pe_value_os.domain import sufficiency

    gaps = {g.code for g in sufficiency.check(data, "retention", get_policy()).gaps}
    assert "duplicate_entities" not in gaps and "unresolved_entities" in gaps


# --- freshness (PVC-118) ---------------------------------------------------------------------------------------------
def test_freshness_ages_and_stale_list():
    from pe_value_os import freshness

    stale = freshness.record(FixtureAdapter().load("delta-broken"), 45)
    assert stale == ["invoices"]
    ages = freshness.source_ages(FixtureAdapter().load("acme-healthy"))
    assert set(ages.values()) == {10}


# --- warehouse adapter (PVC-111) ---------------------------------------------------------------------------------
@pytest.mark.postgres
def test_warehouse_adapter_matches_fixture(pg_database):
    import psycopg

    from pe_value_os.adapters.warehouse import WarehouseAdapter

    admin, _ = pg_database
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute("drop schema if exists wh cascade")
        conn.execute("create schema wh")
        manifest = json.loads((FIX / CID / "manifest.json").read_text())
        for name in manifest["datasets"]:
            path = FIX / CID / f"{name}.csv"
            header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
            conn.execute(f"create table wh.pvc_{name} ({', '.join(f'{c} text' for c in header)})")
            with conn.cursor().copy(f"copy wh.pvc_{name} from stdin with (format csv, header true)") as cp:
                cp.write(path.read_bytes())
        conn.execute("create table wh.pvc_company_profile (company_id text, profile_json text, reference_date date)")
        conn.execute(
            "insert into wh.pvc_company_profile values (%s, %s, %s)",
            (CID, (FIX / CID / "company.json").read_text(), manifest["reference_date"]),
        )
        conn.execute("create table wh.pvc_dataset_freshness (company_id text, dataset text, as_of timestamp)")
        for name, meta in manifest["datasets"].items():
            conn.execute("insert into wh.pvc_dataset_freshness values (%s, %s, %s)", (CID, name, meta["as_of"]))
    wh = WarehouseAdapter(admin.replace("postgresql://", "postgresql+psycopg://"), schema="wh")
    got = wh.load(CID)
    ref = FixtureAdapter().load(CID)
    assert wh.list_companies() == [CID]
    for kind, ds in ref.datasets.items():
        a = sorted(r.model_dump_json() for r in got.datasets[kind].records)
        b = sorted(r.model_dump_json() for r in ds.records)
        assert a == b, kind
        assert got.datasets[kind].as_of == ds.as_of, kind


class _FakeS3:
    """Records put_object calls; head/get raise the injected not-found error."""

    class exceptions:
        ClientError = KeyError

    def __init__(self):
        self.objects: dict[str, dict] = {}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Metadata": self.objects[Key].get("Metadata", {})}

    def put_object(self, **kw):
        self.objects[kw["Key"]] = kw


def test_s3_store_uses_customer_managed_key_when_configured():
    from pe_value_os.adapters.evidence_store import ImmutableEvidenceError, S3EvidenceStore

    s3 = _FakeS3()
    store = S3EvidenceStore("bucket", client=s3, kms_key_id="arn:aws:kms:us-east-1:111122223333:key/k")
    key = store.put_original("acme", "ev1", b"abc")
    assert s3.objects[key]["ServerSideEncryption"] == "aws:kms"
    assert s3.objects[key]["SSEKMSKeyId"].endswith("key/k")
    assert store.put_original("acme", "ev1", b"abc") == key  # idempotent for identical bytes
    with pytest.raises(ImmutableEvidenceError):
        store.put_original("acme", "ev1", b"different")

    plain = _FakeS3()
    S3EvidenceStore("bucket", client=plain).put_derived("acme", "ev1", "text")
    (obj,) = plain.objects.values()
    assert "ServerSideEncryption" not in obj and "SSEKMSKeyId" not in obj  # bucket default encryption applies
