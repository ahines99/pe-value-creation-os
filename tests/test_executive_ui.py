"""Executive review regressions backed by real fixture workflows and persisted decisions.

These checks assert data and browser behavior, not a particular stylesheet or layout.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from html.parser import HTMLParser

import anyio
import pytest
from fastapi.testclient import TestClient

from pe_value_os import kpi, security
from pe_value_os.adapters.base import EvidenceRecord, content_hash, evidence_id_for
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.api import app as api
from pe_value_os.domain.models import Finding
from pe_value_os.domain.runs import Status
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext

COMPANY = "beacon-pricing"
OTHER = "cedar-churn"


class Document(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def inputs(self, name):
        return [attrs for tag, attrs in self.elements if tag == "input" and attrs.get("name") == name]

    def decision_forms(self):
        return [
            attrs
            for tag, attrs in self.elements
            if tag == "form" and str(attrs.get("action", "")).endswith("/approvals/form")
        ]


def headers(identity="approver"):
    return {"Authorization": f"Bearer {identity}"}


def scope(*companies):
    return security.principal_scope(security.system_principal(*(companies or (COMPANY,))))


def start(ctx, company=COMPANY):
    with scope(company):
        run, _ = primary.start(ctx, company, "human:executive-test")
        state = anyio.run(lambda: primary.execute(ctx, run.run_id, backoff_s=0))
        assert state.status == Status.AWAITING_APPROVAL
        return run.run_id


def resume(ctx, run_id, company=COMPANY):
    with scope(company):
        return anyio.run(lambda: primary.resume(ctx, run_id, "system:test-worker"))


@pytest.fixture
def executive(tmp_path, monkeypatch):
    base = {
        "sub": "human:executive-test",
        "pvc_companies": [COMPANY],
        "pvc_roles": ["approver"],
        "pvc_principal_type": "human",
        "scope": "pvc.read pvc.approve",
        "azp": "approval-ui",
    }
    tokens = {
        "approver": base,
        "other": base | {"pvc_companies": [OTHER]},
        "both": base | {"pvc_companies": [COMPANY, OTHER]},
        "analyst": base | {"pvc_roles": ["analyst"], "scope": "pvc.read"},
        "model": base | {"pvc_principal_type": "model"},
        "wrong-client": base | {"azp": "mcp-client"},
    }
    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.setenv("PVC_API_CLIENT_IDS", "approval-ui")
    ctx = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "evidence")),
        adapter=FixtureAdapter(),
        policy=get_policy(),
    )
    api.set_ctx(ctx)
    api.reset_auth()
    run_id = start(ctx)
    with TestClient(api.app) as client:
        yield ctx, run_id, client
    api.set_ctx(None)
    api.reset_auth()


def form_token(client, run_id, identity="approver"):
    response = client.get(f"/runs/{run_id}/review", headers=headers(identity))
    assert response.status_code == 200
    fields = Document(response.text).inputs("csrf")
    assert len(fields) == 1
    return fields[0]["value"]


def post_form(client, run_id, decision, **values):
    return client.post(
        f"/runs/{run_id}/approvals/form",
        headers=headers(),
        data={"csrf": form_token(client, run_id), "decision": decision, **values},
        follow_redirects=False,
    )


def approval_state(ctx, run_id):
    with scope():
        return ctx.repo.list_approvals(run_id), [
            e for e in ctx.repo.list_audit(run_id=run_id) if e.event_type == "approval_decided"
        ]


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_browser_decision_persists_and_worker_completes(executive, decision):
    ctx, run_id, client = executive
    response = post_form(client, run_id, decision, rationale="Investment committee decision")
    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{run_id}/review"
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision.value == decision
    assert len(events) == 1
    receipt = client.get(response.headers["location"], headers=headers())
    expected_status = "approval_recorded" if decision == "approved" else "rejection_recorded"
    assert f"data-status='{expected_status}'" in receipt.text
    assert "data-status='awaiting_approval'" not in receipt.text
    assert "<dt>Workflow status</dt><dd><code>awaiting_approval</code></dd>" in receipt.text
    replay = client.post(
        f"/runs/{run_id}/approvals/form",
        headers=headers(),
        data={"csrf": client.cookies["pvc_csrf"], "decision": decision, "rationale": "Repeated browser submission"},
    )
    assert replay.status_code == 422 and replay.headers["content-type"].startswith("text/html")
    repeated_records, repeated_events = approval_state(ctx, run_id)
    assert len(repeated_records) == len(records) and len(repeated_events) == 1
    assert resume(ctx, run_id).status == (Status.COMPLETE if decision == "approved" else Status.REJECTED)
    page = client.get(response.headers["location"], headers=headers())
    assert not Document(page.text).decision_forms()
    with scope():
        definitions = ctx.repo.list_kpi_definitions(COMPANY)
    assert bool(definitions) == (decision == "approved")


def test_request_changes_from_browser_excludes_selected_initiative_and_creates_new_round(executive):
    ctx, run_id, client = executive
    with scope():
        original = ctx.repo.latest_plan(run_id)
        drop = original.plan["workstreams"][0]["initiatives"][0]
    response = post_form(
        client,
        run_id,
        "changes_requested",
        rationale="Rework customer response before sizing this initiative",
        remove_initiatives=drop["opportunity_id"],
    )
    assert response.status_code == 303
    records, _ = approval_state(ctx, run_id)
    assert records[-1].edits["exclude_opportunities"] == [drop["opportunity_id"]]
    receipt = client.get(response.headers["location"], headers=headers())
    assert "data-status='revisions_queued'" in receipt.text
    assert "data-status='awaiting_approval'" not in receipt.text
    assert "<dt>Workflow status</dt><dd><code>awaiting_approval</code></dd>" in receipt.text
    assert resume(ctx, run_id).status == Status.AWAITING_APPROVAL
    with scope():
        revised = ctx.repo.latest_plan(run_id)
        assert ctx.repo.get_plan(original.plan_id).status == "superseded"
        retained = [i for ws in revised.plan["workstreams"] for i in ws["initiatives"]]
        assert drop["opportunity_id"] not in {i["opportunity_id"] for i in retained}
        assert Decimal(revised.plan["total_run_rate_ebitda_base"]) == sum(
            (Decimal(i["run_rate_ebitda_base"]) for i in retained), Decimal(0)
        ).quantize(Decimal("0.01"))
    assert revised.plan_id != original.plan_id
    records, _ = approval_state(ctx, run_id)
    assert len(records) == 2 and records[-1].decision is None
    assert post_form(client, run_id, "approved").status_code == 303
    assert resume(ctx, run_id).status == Status.COMPLETE


def test_edited_approval_displays_only_approved_financial_scope_before_and_after_worker(executive):
    ctx, run_id, client = executive
    with scope():
        original = ctx.repo.latest_plan(run_id).plan
        drop = original["workstreams"][0]["initiatives"][0]
    response = post_form(
        client,
        run_id,
        "approved",
        rationale="Approve remaining workstreams; defer this initiative",
        remove_initiatives=drop["opportunity_id"],
    )
    assert response.status_code == 303
    records, _ = approval_state(ctx, run_id)
    approved = records[-1].edits["approved_plan"]
    expected = Decimal(approved["total_run_rate_ebitda_base"])
    assert expected == sum(
        (
            Decimal(i["run_rate_ebitda_base"])
            for ws in original["workstreams"]
            for i in ws["initiatives"]
            if i["opportunity_id"] != drop["opportunity_id"]
        ),
        Decimal(0),
    )
    for processed in (False, True):
        if processed:
            assert resume(ctx, run_id).status == Status.COMPLETE
        page = client.get(f"/runs/{run_id}/review", headers=headers())
        assert page.status_code == 200
        doc = Document(page.text)
        headline = [attrs for _, attrs in doc.elements if attrs.get("data-metric") == "run-rate-ebitda"]
        assert len(headline) == 1 and Decimal(headline[0]["data-value"]) == expected
        assert headline[0]["data-currency"] == "USD"
        excluded = [attrs for _, attrs in doc.elements if attrs.get("data-opportunity-id") == drop["opportunity_id"]]
        assert excluded and all(attrs["data-included"] == "false" for attrs in excluded)
        assert not doc.decision_forms()
        home = Document(client.get("/", headers=headers()).text)
        totals = [attrs for _, attrs in home.elements if attrs.get("data-metric") == "portfolio-run-rate-ebitda"]
        assert len(totals) == 1 and Decimal(totals[0]["data-value"]) == expected
    with scope():
        assert ctx.repo.latest_plan(run_id).approved_plan == approved
        assert {d.metric for d in ctx.repo.list_kpi_definitions(COMPANY)} == {
            k["metric"] for ws in approved["workstreams"] for k in ws["kpis"]
        }


@pytest.mark.parametrize("decision", ["rejected", "changes_requested"])
def test_missing_rationale_returns_recoverable_html_without_persisting_decision(executive, decision):
    ctx, run_id, client = executive
    with scope():
        drop = ctx.repo.latest_plan(run_id).plan["workstreams"][0]["initiatives"][0]["opportunity_id"]
    response = post_form(client, run_id, decision, remove_initiatives=drop)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    doc = Document(response.text)
    assert doc.decision_forms()
    assert any(a.get("role") == "alert" for _, a in doc.elements)
    assert any(a.get("value") == drop and "checked" in a for a in doc.inputs("remove_initiatives"))
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision is None and not events
    fixed = client.post(
        f"/runs/{run_id}/approvals/form",
        headers=headers(),
        data={
            "csrf": doc.inputs("csrf")[0]["value"],
            "decision": decision,
            "rationale": "Committee supplied the missing rationale",
            "remove_initiatives": drop,
        },
        follow_redirects=False,
    )
    assert fixed.status_code == 303


@pytest.mark.parametrize("decision", ["approved", "changes_requested"])
def test_forged_selection_is_rejected_without_decision(executive, decision):
    ctx, run_id, client = executive
    response = post_form(client, run_id, decision, rationale="A valid rationale", remove_initiatives=str(uuid.uuid4()))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision is None and not events


def test_json_change_request_cannot_exclude_another_runs_opportunity(executive):
    ctx, run_id, client = executive
    other_run = start(ctx)
    with scope():
        foreign = ctx.repo.list_opportunities(other_run)[0].opportunity_id
    response = client.post(
        f"/runs/{run_id}/approvals",
        headers=headers(),
        json={
            "decision": "changes_requested",
            "rationale": "This selection belongs to a different review",
            "exclude_opportunities": [foreign],
        },
    )
    assert response.status_code == 422
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision is None and not events


@pytest.mark.parametrize("token", ["analyst", "model", "wrong-client"])
def test_decision_controls_match_authorization_and_direct_post_is_denied(executive, token):
    ctx, run_id, client = executive
    page = client.get(f"/runs/{run_id}/review", headers=headers(token))
    assert page.status_code == 200
    assert not Document(page.text).decision_forms()
    response = client.post(f"/runs/{run_id}/approvals", headers=headers(token), json={"decision": "approved"})
    assert response.status_code == 403
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision is None and not events


def test_expired_csrf_shows_html_preserves_rationale_and_never_decides(executive):
    ctx, run_id, client = executive
    stale = form_token(client, run_id)
    form_token(client, run_id)
    response = client.post(
        f"/runs/{run_id}/approvals/form",
        headers=headers(),
        data={"decision": "rejected", "csrf": stale, "rationale": "Preserve this review note"},
    )
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "Preserve this review note" in response.text
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision is None and not events


@pytest.mark.parametrize("decision", [None, "not-a-decision"])
def test_missing_or_invalid_browser_decision_is_html_validation(executive, decision):
    ctx, run_id, client = executive
    data = {"csrf": form_token(client, run_id), "rationale": "Retain the entered rationale"}
    if decision is not None:
        data["decision"] = decision
    response = client.post(f"/runs/{run_id}/approvals/form", headers=headers(), data=data)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert "Retain the entered rationale" in response.text
    assert Document(response.text).decision_forms()
    records, events = approval_state(ctx, run_id)
    assert records[-1].decision is None and not events


def test_scoped_review_and_evidence_preview_escape_source_content(executive):
    ctx, run_id, client = executive
    payload = b'<script>alert("evidence")</script><img src=x onerror=alert(1)>'
    digest = content_hash(payload)
    eid = evidence_id_for(COMPANY, digest)
    with scope():
        ctx.repo.add_evidence(
            EvidenceRecord(eid, COMPANY, 'fixture://memo-<img onerror="x">.txt', "document", None, digest, payload)
        )
        ctx.repo.add_finding(
            Finding(
                finding_id=str(uuid.uuid4()),
                run_id=run_id,
                company_id=COMPANY,
                finding_type="data_gap",
                title='<img src=x onerror="alert(2)">',
                statement="Untrusted management note",
                confidence="low",
            )
        )
    for path in (f"/runs/{run_id}/review", f"/evidence/{eid}/review"):
        assert client.get(path, headers=headers("other")).status_code == 404
        assert client.get(path).status_code == 401
        response = client.get(path, headers=headers())
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        doc = Document(response.text)
        assert not any(tag == "script" or any(k.startswith("on") for k in attrs) for tag, attrs in doc.elements)
        assert "&lt;" in response.text
        assert response.headers["cache-control"] == "no-store"
    raw = client.get(f"/evidence/{eid}", headers=headers())
    assert raw.content == payload and raw.headers["x-content-hash"] == digest
    assert client.get(f"/evidence/{eid}", headers=headers("other")).status_code == 404


def test_kpi_run_filter_preserves_historical_observations_and_rejects_wrong_company(executive):
    ctx, first, client = executive
    assert post_form(client, first, "approved").status_code == 303
    resume(ctx, first)
    with scope():
        first_defs = ctx.repo.list_kpi_definitions(COMPANY)
        for definition in first_defs:
            ctx.repo.save_kpi_definitions([definition.model_copy(update={"description": "Historical KPI marker"})])
        kpi.refresh_company(ctx.repo, ctx.adapter, COMPANY, ctx.policy, force=True)
    second = start(ctx)
    assert post_form(client, second, "approved").status_code == 303
    resume(ctx, second)
    with scope():
        for definition in ctx.repo.list_kpi_definitions(COMPANY):
            ctx.repo.save_kpi_definitions([definition.model_copy(update={"description": "Current KPI marker"})])
    historical = client.get(f"/companies/{COMPANY}/kpis?run_id={first}", headers=headers())
    current = client.get(f"/companies/{COMPANY}/kpis?run_id={second}", headers=headers())
    assert historical.status_code == current.status_code == 200
    assert "Historical KPI marker" in historical.text and "Current KPI marker" not in historical.text
    assert "Current KPI marker" in current.text and "Historical KPI marker" not in current.text
    assert "Selected approved plan" in historical.text
    assert "Most recently activated plan" not in historical.text
    wrong_run = start(ctx, OTHER)
    assert client.get(f"/companies/{COMPANY}/kpis?run_id={wrong_run}", headers=headers("both")).status_code == 404
    assert client.get(f"/companies/{COMPANY}/kpis?run_id={first}", headers=headers("other")).status_code == 404


def test_portfolio_uses_latest_company_run_once_and_keeps_currency_totals_separate(executive):
    ctx, historical, client = executive
    latest = start(ctx)
    other_run = start(ctx, OTHER)
    with scope(COMPANY, OTHER):
        # Presentation must respect profile currency, without implicitly performing FX conversion.
        ctx.repo.upsert_company(ctx.repo.get_company(OTHER).model_copy(update={"currency": "EUR"}))
        expected_usd = Decimal(ctx.repo.latest_plan(latest).plan["total_run_rate_ebitda_base"])
        expected_eur = Decimal(ctx.repo.latest_plan(other_run).plan["total_run_rate_ebitda_base"])
    page = client.get("/", headers=headers("both"))
    assert page.status_code == 200
    doc = Document(page.text)
    totals = [attrs for _, attrs in doc.elements if attrs.get("data-metric") == "portfolio-run-rate-ebitda"]
    assert len(totals) == 2
    assert {attrs["data-currency"]: Decimal(attrs["data-value"]) for attrs in totals} == {
        "USD": expected_usd,
        "EUR": expected_eur,
    }
    links = {attrs.get("href") for tag, attrs in doc.elements if tag == "a"}
    assert {f"/runs/{r}/review" for r in (historical, latest, other_run)} <= links
    own = client.get("/", headers=headers())
    assert other_run not in own.text and "EUR" not in own.text


def test_kpi_display_distinguishes_fraction_month_and_ticket_units(executive):
    ctx, run_id, client = executive
    assert post_form(client, run_id, "approved").status_code == 303
    resume(ctx, run_id)
    with scope():
        template = ctx.repo.list_kpi_definitions(COMPANY)[0]
        definitions = [
            template.model_copy(
                update={
                    "kpi_id": str(uuid.uuid4()),
                    "metric": metric,
                    "description": description,
                    "baseline": value,
                    "day_100_target": value,
                    "run_rate_target": value,
                }
            )
            for metric, description, value in (
                ("grr", "Retention ratio unit fixture", Decimal("0.8123")),
                ("cac_payback_months", "Payback duration unit fixture", Decimal("12.25")),
                ("tier1_tickets_per_customer_month", "Ticket volume unit fixture", Decimal("0.125")),
            )
        ]
        ctx.repo.save_kpi_definitions(definitions)
    response = client.get(f"/companies/{COMPANY}/kpis?run_id={run_id}", headers=headers())
    assert response.status_code == 200
    text = " ".join(Document(response.text).text)
    assert "81.2%" in text
    assert "12.25 months" in text
    assert "0.125 tickets / customer / month" in text
    assert "None yet" in text  # A target is not a measured result.
