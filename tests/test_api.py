"""PVC-060, PVC-062, PVC-063, PVC-124: approval API, review page, plan edits, KPI page."""

from __future__ import annotations

import io
import json
import re

import anyio
import pytest
from fastapi.testclient import TestClient

from pe_value_os import security
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.api import app as api
from pe_value_os.domain.runs import Status
from pe_value_os.observability import configure_logging
from pe_value_os.policy import get_policy
from pe_value_os.workflows import primary
from pe_value_os.workflows.steps import RunContext

configure_logging(stream=io.StringIO())

TOKENS = {
    "approver-beacon": {
        "sub": "human:jo",
        "pvc_companies": ["beacon-pricing"],
        "pvc_roles": ["approver"],
        "pvc_principal_type": "human",
        "scope": "pvc.read pvc.approve",
    },
    "analyst-beacon": {
        "sub": "human:al",
        "pvc_companies": ["beacon-pricing"],
        "pvc_roles": ["analyst"],
        "pvc_principal_type": "human",
    },
    "model-beacon": {
        "sub": "model:claude",
        "pvc_companies": ["beacon-pricing"],
        "pvc_roles": ["approver"],
        "pvc_principal_type": "model",
        "scope": "pvc.read pvc.approve",
    },
    "approver-mcp-token": {  # right person and role, but a token without the approve scope (e.g. issued to MCP)
        "sub": "human:jo",
        "pvc_companies": ["beacon-pricing"],
        "pvc_roles": ["approver"],
        "pvc_principal_type": "human",
        "scope": "pvc.read pvc.write",
    },
    "approver-cedar": {
        "sub": "human:ce",
        "pvc_companies": ["cedar-churn"],
        "pvc_roles": ["approver"],
        "pvc_principal_type": "human",
        "scope": "pvc.read pvc.approve",
    },
}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_browser_demo_login_scoping_and_csrf(env):
    _, run_id, client = env
    landing = client.get("/")
    assert landing.status_code == 200
    assert "Local showcase sign-in" in landing.text
    csrf = client.cookies["pvc_login_csrf"]
    assert client.post("/dev/login", data={"token": "approver-beacon", "csrf": "wrong"}).status_code == 403
    csrf = client.cookies["pvc_login_csrf"]
    assert client.post("/dev/login", data={"token": "invalid", "csrf": csrf}).status_code == 401
    csrf = client.cookies["pvc_login_csrf"]
    login = client.post("/dev/login", data={"token": "approver-beacon", "csrf": csrf}, follow_redirects=False)
    assert login.status_code == 303
    assert "HttpOnly" in login.headers["set-cookie"]
    workspace = client.get("/")
    assert run_id in workspace.text
    assert "cedar-churn" not in workspace.text
    assert client.get(f"/runs/{run_id}/review").status_code == 200
    client.cookies.delete("pvc_csrf")
    assert client.post(f"/runs/{run_id}/approvals/form", data={"decision": "approved", "csrf": ""}).status_code in {
        403,
        422,
    }


def test_development_cookie_is_not_production_auth(env, monkeypatch):
    _, _, client = env
    client.cookies.set("pvc_dev_session", "approver-beacon")
    monkeypatch.setenv("PVC_ENV", "prod")
    assert client.get("/").status_code == 401
    assert client.post("/dev/login", data={"token": "approver-beacon", "csrf": "x"}).status_code == 404


def test_demo_login_recovers_from_bad_token_and_expired_form(env):
    _, run_id, client = env
    client.get("/")
    original_csrf = client.cookies["pvc_login_csrf"]
    bad = client.post("/dev/login", data={"token": "do-not-echo-this-secret", "csrf": original_csrf})
    assert bad.status_code == 401
    assert bad.headers["content-type"].startswith("text/html")
    assert "role='alert'" in bad.text and "not recognized" in bad.text
    assert "settings.json" in bad.text and "do-not-echo-this-secret" not in bad.text
    assert "pvc_dev_session" not in client.cookies
    assert client.cookies["pvc_login_csrf"] != original_csrf
    expired = client.post("/dev/login", data={"token": "approver-beacon", "csrf": original_csrf})
    assert expired.status_code == 403 and "sign-in page expired" in expired.text
    assert "pvc_dev_session" not in client.cookies
    recovered = client.post(
        "/dev/login",
        data={"token": " \tapprover-beacon\r\n", "csrf": client.cookies["pvc_login_csrf"]},
    )
    assert recovered.status_code == 200 and run_id in recovered.text
    assert client.cookies["pvc_dev_session"] == "approver-beacon"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(TOKENS))
    ctx = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev")), adapter=FixtureAdapter(), policy=get_policy()
    )
    api.set_ctx(ctx)
    api.reset_auth()
    with security.principal_scope(security.system_principal("beacon-pricing", "cedar-churn")):
        rec, _ = primary.start(ctx, "beacon-pricing", "human:jo")
        anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
    yield ctx, rec.run_id, TestClient(api.app)
    api.set_ctx(None)


def resume(ctx, run_id):
    with security.principal_scope(security.system_principal("beacon-pricing")):
        return anyio.run(lambda: primary.resume(ctx, run_id, "system:worker"))


def test_auth_required(env):
    _, run_id, client = env
    assert client.get(f"/runs/{run_id}").status_code == 401
    assert client.get(f"/runs/{run_id}", headers=H("garbage")).status_code == 401
    assert client.get(f"/runs/{run_id}", headers=H("approver-beacon")).json()["status"] == "awaiting_approval"


def test_other_company_cannot_see_run(env):
    _, run_id, client = env
    assert client.get(f"/runs/{run_id}", headers=H("approver-cedar")).status_code == 404
    r = client.post(f"/runs/{run_id}/approvals", headers=H("approver-cedar"), json={"decision": "approved"})
    assert r.status_code == 404


def test_only_human_approvers_can_decide(env):
    ctx, run_id, client = env
    for tok in ("model-beacon", "analyst-beacon"):
        r = client.post(f"/runs/{run_id}/approvals", headers=H(tok), json={"decision": "approved"})
        assert r.status_code == 403, r.text
    assert all(a.decision is None for a in _approvals(ctx, run_id))


def _approvals(ctx, run_id):
    with security.principal_scope(security.system_principal("beacon-pricing")):
        return ctx.repo.list_approvals(run_id)


def test_rationale_required_for_reject_and_changes(env):
    _, run_id, client = env
    for d in ("rejected", "changes_requested"):
        r = client.post(f"/runs/{run_id}/approvals", headers=H("approver-beacon"), json={"decision": d})
        assert r.status_code == 422 and "rationale" in r.text


def test_approve_with_edits_records_diff_and_resumes(env):
    ctx, run_id, client = env
    with security.principal_scope(security.system_principal("beacon-pricing")):
        plan = ctx.repo.latest_plan(run_id).plan
    drop = next(i for ws in plan["workstreams"] for i in ws["initiatives"] if i["title"].startswith("Enforce"))
    r = client.post(
        f"/runs/{run_id}/approvals",
        headers=H("approver-beacon"),
        json={"decision": "approved", "rationale": "hold uplifts", "remove_initiatives": [drop["opportunity_id"]]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decided_by"] == "human:jo" and body["diff"]["removed_titles"] == [drop["title"]]
    assert (
        client.post(
            f"/runs/{run_id}/approvals", headers=H("approver-beacon"), json={"decision": "approved"}
        ).status_code
        == 422
    )  # already decided
    st = resume(ctx, run_id)
    assert st.status == Status.COMPLETE
    with security.principal_scope(security.system_principal("beacon-pricing")):
        approved = ctx.repo.latest_plan(run_id).approved_plan
        kpi_opps = {k.metric for k in ctx.repo.list_kpi_definitions("beacon-pricing")}
        audit = [e for e in ctx.repo.list_audit(run_id=run_id) if e.event_type == "approval_decided"]
    titles = [i["title"] for ws in approved["workstreams"] for i in ws["initiatives"]]
    assert drop["title"] not in titles
    assert "renewal_uplift_realization" not in kpi_opps  # the removed initiative's KPI is not activated
    assert audit and audit[0].payload["changed"] is True
    stats = client.get("/metrics/approvals", headers=H("approver-beacon")).json()
    assert stats == {"decisions": 1, "changed_or_rejected": 1, "override_rate": 1.0}


def test_review_page_and_csrf_form(env):
    ctx, run_id, client = env
    r = client.get(f"/runs/{run_id}/review", headers=H("approver-beacon"))
    assert r.status_code == 200 and "Plan review" in r.text and "Discount governance in mid_market" in r.text
    assert "<script" not in r.text.lower()
    csrf = re.search(r"name='csrf' value='([^']+)'", r.text).group(1)
    bad = client.post(
        f"/runs/{run_id}/approvals/form", headers=H("approver-beacon"), data={"decision": "approved", "csrf": "wrong"}
    )
    assert bad.status_code == 403
    csrf = client.cookies["pvc_csrf"]
    ok = client.post(
        f"/runs/{run_id}/approvals/form",
        headers=H("approver-beacon"),
        data={"decision": "rejected", "csrf": csrf, "rationale": "not now"},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert resume(ctx, run_id).status == Status.REJECTED
    viewer = client.get(f"/runs/{run_id}/review", headers=H("analyst-beacon"))
    assert "data-status='rejected'" in viewer.text and "not now" in viewer.text


def test_review_page_escapes_untrusted_text(env):
    ctx, run_id, client = env
    from pe_value_os.domain.models import Finding, FindingType

    with security.principal_scope(security.system_principal("beacon-pricing")):
        ctx.repo.add_finding(
            Finding(
                finding_id="99999999-9999-9999-9999-999999999999",
                run_id=run_id,
                company_id="beacon-pricing",
                finding_type=FindingType.DATA_GAP,
                title="<script>alert(1)</script>",
                statement="x",
                confidence="low",
            )
        )
    r = client.get(f"/runs/{run_id}/review", headers=H("approver-beacon"))
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text


def test_evidence_download_is_scoped(env):
    ctx, run_id, client = env
    with security.principal_scope(security.system_principal("beacon-pricing")):
        ev = ctx.repo.list_opportunities(run_id)[0].evidence_ids[0]
    r = client.get(f"/evidence/{ev}", headers=H("approver-beacon"))
    assert r.status_code == 200 and r.headers["x-content-hash"] and len(r.content) > 100
    assert client.get(f"/evidence/{ev}", headers=H("approver-cedar")).status_code == 404


def test_kpi_page(env):
    ctx, run_id, client = env
    client.post(f"/runs/{run_id}/approvals", headers=H("approver-beacon"), json={"decision": "approved"})
    resume(ctx, run_id)
    from pe_value_os import kpi

    with security.principal_scope(security.system_principal("beacon-pricing")):
        kpi.refresh_company(ctx.repo, ctx.adapter, "beacon-pricing", ctx.policy, force=True)
    r = client.get("/companies/beacon-pricing/kpis", headers=H("approver-beacon"))
    assert r.status_code == 200 and "Average new-deal discount" in r.text
    # The fixture data ends before today's approval, so every reading is a baseline, not progress.
    assert (
        "Pre-plan reading" in r.text and "Awaiting post-plan data" in r.text and "data-status='on_track'" not in r.text
    )
    assert client.get("/companies/beacon-pricing/kpis", headers=H("approver-cedar")).status_code == 404


def test_kpi_status_uses_only_readings_after_the_plan_started():
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from pe_value_os.api.review_views import _kpi_card
    from pe_value_os.domain.kpi_models import KpiDefinition, KpiObservation

    d = KpiDefinition(
        kpi_id="k",
        company_id="c",
        plan_id="p",
        run_id="r",
        metric="gross_margin",
        description="Gross margin",
        baseline=Decimal("0.70"),
        day_100_target=Decimal("0.72"),
        run_rate_target=Decimal("0.75"),
        direction="increase",
        cadence_days=30,
        source="fixture",
        start_date=date(2026, 9, 30),
        created_at=datetime(2026, 9, 30, tzinfo=UTC),
    )

    def obs(period_end, status):
        return KpiObservation(
            observation_id=str(period_end),
            kpi_id="k",
            company_id="c",
            observed_at=datetime(2026, 11, 5, tzinfo=UTC),
            period_end=period_end,
            value=Decimal("0.70"),
            target=Decimal("0.70"),
            status=status,
            variance=Decimal(0),
        )

    before = [obs(date(2026, 8, 1), "on_track"), obs(date(2026, 9, 1), "on_track")]  # September ends on the start date
    card = _kpi_card(d, before)
    assert (
        "Awaiting post-plan data" in card and "data-status='on_track'" not in card and "% of the baseline" not in card
    )
    card = _kpi_card(d, [*before, obs(date(2026, 10, 1), "off_track")])
    assert "data-status='off_track'" in card and "% of the baseline" in card


def test_approving_with_every_initiative_removed_is_refused(env):
    ctx, run_id, client = env
    with security.principal_scope(security.system_principal("beacon-pricing")):
        plan = ctx.repo.latest_plan(run_id).plan
    every = [i["opportunity_id"] for ws in plan["workstreams"] for i in ws["initiatives"]]
    r = client.post(
        f"/runs/{run_id}/approvals",
        headers=H("approver-beacon"),
        json={"decision": "approved", "remove_initiatives": every},
    )
    assert r.status_code == 422 and "nothing to approve" in r.text
    form = client.post(
        f"/runs/{run_id}/approvals/form",
        headers=H("approver-beacon"),
        data={"decision": "approved", "csrf": _csrf(client, run_id), "remove_initiatives": every},
    )
    assert form.status_code == 422 and "nothing to approve" in form.text and "<form" in form.text
    assert all(a.decision is None for a in _approvals(ctx, run_id))


def _csrf(client, run_id):
    client.get(f"/runs/{run_id}/review", headers=H("approver-beacon"))
    return client.cookies["pvc_csrf"]


def test_json_decisions_need_a_bearer_token(env):
    ctx, run_id, client = env
    client.cookies.set("pvc_dev_session", "approver-beacon")
    r = client.post(f"/runs/{run_id}/approvals", json={"decision": "approved"})
    assert r.status_code == 403 and "bearer" in r.text
    assert all(a.decision is None for a in _approvals(ctx, run_id))


def test_browsers_get_sign_in_or_an_error_page_and_api_clients_get_json(env):
    _, run_id, client = env
    browser = {"Accept": "text/html,application/xhtml+xml"}
    signed_out = client.get(f"/runs/{run_id}/review", headers=browser, follow_redirects=False)
    assert signed_out.status_code == 303 and signed_out.headers["location"] == "/"
    assert client.get(f"/runs/{run_id}").json()["detail"]
    other = client.get(f"/runs/{run_id}/review", headers={**browser, **H("approver-cedar")})
    assert (
        other.status_code == 404 and other.headers["content-type"].startswith("text/html") and "Not found" in other.text
    )
    missing = client.get("/runs/no-such-run/review", headers={**browser, **H("approver-beacon")})
    assert missing.status_code == 404 and "Back to portfolio" in missing.text
    api_missing = client.get("/runs/no-such-run", headers=H("approver-beacon"))
    assert api_missing.status_code == 404 and api_missing.headers["content-type"].startswith("application/json")


def test_money_and_labels_read_as_text():
    from pe_value_os.api.presentation import label, money

    assert money("380649.7") == "380,650" and money("12.5") == "12.50" and money("7") == "7"
    assert money("3642580.8", compact=True) == "3.6m" and money("5000000", compact=True) == "5.0m"
    assert label("s_and_m_expense") == "S&amp;M expense" and label("ai_automation") == "AI automation"
    assert label("legacy_price_book_arr") == "Legacy price book ARR"
    assert label("tier1_tickets_per_customer_month") == "Tier-1 tickets per customer month"


def test_approval_needs_approve_scope_and_allowed_client(env, monkeypatch):
    ctx, run_id, client = env
    r = client.post(f"/runs/{run_id}/approvals", headers=H("approver-mcp-token"), json={"decision": "approved"})
    assert r.status_code == 403 and "pvc.approve" in r.text
    monkeypatch.setenv("PVC_API_CLIENT_IDS", "approval-ui")
    r = client.post(f"/runs/{run_id}/approvals", headers=H("approver-beacon"), json={"decision": "approved"})
    assert r.status_code == 403 and "approval UI client" in r.text  # dev token has no azp
    assert all(a.decision is None for a in _approvals(ctx, run_id))


def test_api_rejects_tokens_minted_for_the_mcp_audience(monkeypatch):
    from datetime import UTC, datetime, timedelta

    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from pe_value_os.auth import AuthConfigError, verifier_from_env

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setenv("PVC_ENV", "staging")
    monkeypatch.setenv("PVC_AUTH_ISSUER", "https://idp.example.test")
    monkeypatch.setenv("PVC_AUTH_AUDIENCE", "https://mcp.example.test/mcp")
    monkeypatch.setenv("PVC_AUTH_PUBLIC_KEY", pub.decode())
    monkeypatch.delenv("PVC_API_AUDIENCE", raising=False)
    with pytest.raises(AuthConfigError):
        verifier_from_env(for_api=True)  # fails closed without a separate API audience
    monkeypatch.setenv("PVC_API_AUDIENCE", "https://mcp.example.test/mcp")
    with pytest.raises(AuthConfigError):
        verifier_from_env(for_api=True)  # and refuses to share the MCP audience
    monkeypatch.setenv("PVC_API_AUDIENCE", "https://approvals.example.test")
    now = datetime.now(UTC)
    claims = {
        "iss": "https://idp.example.test",
        "sub": "human:jo",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "scope": "pvc.read pvc.approve",
        "pvc_principal_type": "human",
        "pvc_roles": ["approver"],
    }
    mcp_token = jwt.encode({**claims, "aud": "https://mcp.example.test/mcp"}, key, algorithm="RS256")
    api_token = jwt.encode(
        {**claims, "aud": "https://approvals.example.test", "azp": "approval-ui"}, key, algorithm="RS256"
    )
    v = verifier_from_env(for_api=True)
    with pytest.raises(jwt.InvalidAudienceError):
        v.decode(mcp_token)
    assert v.decode(api_token)["azp"] == "approval-ui"


def test_decision_desk_keeps_an_earlier_assessment_awaiting_approval(env):
    ctx, first, client = env
    with security.principal_scope(security.system_principal("beacon-pricing")):
        rec, _ = primary.start(ctx, "beacon-pricing", "human:jo", params={"note": "second"})
        anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
    page = client.get("/", headers=H("approver-beacon")).text
    assert f"/runs/{first}/review'>Review and decide" in page and "Earlier assessment of" in page
    assert re.search(r"Decisions required</p><div class='metric-value'>2<", page)
