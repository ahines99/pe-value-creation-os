"""Private browser decisions preserve scoped sources and exact review versions."""

import hashlib
import json
from datetime import datetime
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pe_value_os import security
from pe_value_os.api import app as api
from pe_value_os.api import private_review_views as views
from pe_value_os.diligence import private_review
from tests.test_private_attribution import clock as private_clock  # noqa: F401
from tests.test_private_attribution import complete, finance_review, save
from tests.test_private_observations import clock as measurement_clock  # noqa: F401
from tests.test_private_records import COMPANY, ENV, FINANCE, OPERATOR, actor, revoke


@pytest.fixture(autouse=True)
def review_clock(monkeypatch, request):
    measured = request.getfixturevalue("private_clock")

    class Clock(datetime):
        @classmethod
        def now(cls, zone):
            return measured.value

    monkeypatch.setattr(private_review, "datetime", Clock)
    return measured


def packet(repo, proposal, *, person=FINANCE, environment=ENV):
    with security.principal_scope(person):
        return repo.private_attribution_review_packet(COMPANY, proposal.revision_id, environment)


@pytest.fixture
def client(repo, monkeypatch):
    people = {
        "operator": OPERATOR,
        "finance": FINANCE,
        "model": actor(kind="model"),
        "foreign": actor(company="foreign"),
    }
    tokens = {
        name: dict(
            sub=p.subject,
            pvc_companies=list(p.companies),
            pvc_roles=list(p.roles),
            pvc_principal_type=p.principal_type,
            scope=" ".join(p.scopes),
            client_id=p.client_id,
        )
        for name, p in people.items()
    }
    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps(tokens))
    monkeypatch.setenv("PVC_PROCESSING_ENVIRONMENT_ID", ENV)
    api.reset_auth()
    api.set_ctx(SimpleNamespace(repo=repo))
    try:
        with TestClient(api.app) as browser:
            yield browser
    finally:
        api.set_ctx(None)
        api.reset_auth()


def headers(person="finance"):
    return {"Authorization": "Bearer " + person}


class Hidden(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.fields = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("type") == "hidden":
            self.fields[values["name"]] = values.get("value", "")


def submitted(html, decision="accept"):
    return {
        **Hidden(html).fields,
        "decision": decision,
        "rationale": "Fictional finance decision",
        **{key: "Fictional reviewed assessment; independent verification absent" for key in views.ASSESSMENTS},
    }


def test_packet_separates_financial_facts_claims_acceptance_and_permission(repo, review_clock):
    case = complete(repo, review_clock)
    proposal = save(repo, case)
    result = packet(repo, proposal)
    assert result["checks"] == dict(
        baseline_supported=True, observation_supported=True, proposal_supported=True, finance_acceptance_supported=False
    )
    assert result["can_record_substantive_review"] and not result["can_withdraw_review"]
    assert result["observation"]["result"]["totals"]["actual"]["mapped_ebitda"] == "730"
    assert result["proposal"]["result"]["totals"]["proposed_attribution"]["mapped_ebitda"] == "10"
    assert not result["execution"]["recorded_authorization_currently_supported"]  # November authorization expired.
    assert not result["delivery_costs_reconciled_to_ledger"] and not result["causal_impact_proven"]
    supplied = result.pop("packet_sha256")
    assert private_review.packet_fingerprint(result) == supplied
    finance_review(repo, proposal)
    reviewed = packet(repo, proposal)
    assert reviewed["checks"]["finance_acceptance_supported"] and reviewed["can_withdraw_review"]
    assert not packet(repo, proposal, person=OPERATOR)["can_record_substantive_review"]


def test_review_index_uses_latest_proposals_and_labels_recorded_decisions(repo, review_clock):
    case = complete(repo, review_clock)
    proposal = save(repo, case)
    finance_review(repo, proposal)
    with security.principal_scope(FINANCE):
        cards = repo.private_review_index(COMPANY)
    assert len(cards) == 1 and cards[0]["decision"] == "accept"
    html = views.index_page(cards)
    assert "Recorded finance decision: Accepted" in html and views.review_path(COMPANY, proposal.revision_id) in html
    assert "Fictional rehearsal" in html


def test_rendered_packet_preserves_units_limits_and_escapes_untrusted_notes(repo, review_clock):
    case = complete(repo, review_clock)
    proposal = save(repo, case)
    value = packet(repo, proposal)
    value["company_name"] = "<script>company</script>"
    value["currency"] = "EUR"
    value["proposal"]["request"]["method_and_limits"] = "<img src=x onerror=alert(1)>"
    html = views.review_page(value, "csrf", "nonce", submitted={"rationale": "</textarea><script>note</script>"})
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;company" in html and "&lt;/textarea&gt;" in html
    assert "EUR units" in html and "$" not in html
    for text in (
        "730",
        "700",
        "610",
        "590",
        "Monthly accounting components",
        "Frozen plan",
        "Counterfactual design",
        "Valuation sensitivity and limits",
        "Reported costs have not been reconciled",
        "Accept reviewed claims",
    ):
        assert text in html
    assert "No currently supported operating authorization" in html
    assert "Fictional private-workflow rehearsal" in html


def test_authenticated_browser_can_review_and_withdraw_after_revocation(repo, review_clock, client, monkeypatch):
    case = complete(repo, review_clock)
    proposal = save(repo, case)
    path = views.review_path(COMPANY, proposal.revision_id)
    client.cookies.set("pvc_dev_session", "finance")
    opened = client.get(path)
    assert opened.status_code == 200 and opened.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in opened.headers["content-security-policy"]
    response = client.post(path + "/decision", data=submitted(opened.text), follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == path
    reviewed = client.get(path)
    assert "Reviewed claim" in reviewed.text and "Withdraw acceptance" in reviewed.text
    revoke(repo, case.grant)
    monkeypatch.delenv("PVC_PROCESSING_ENVIRONMENT_ID")
    historical = client.get(path)
    assert historical.status_code == 200 and "Historical values only" in historical.text
    assert "Accept reviewed claims" not in historical.text and "Withdraw acceptance" in historical.text
    result = client.post(path + "/decision", data=submitted(historical.text, "withdraw"), follow_redirects=False)
    assert result.status_code == 303
    with security.principal_scope(FINANCE):
        decisions = repo.list_private_attribution_reviews(COMPANY, proposal.revision_id)
    assert [r.request.decision for r in decisions] == ["accept", "withdraw"]
    assert decisions[0].request.evidence.reference.startswith("workspace-review-note:")
    assert "no external document authentication" in decisions[0].request.evidence.attestation
    history = client.get(path).text
    assert decisions[0].content_sha256 in history and decisions[1].content_sha256 in history
    assert "Fictional reviewed assessment; independent verification absent" in history
    assert decisions[0].request.evidence.reference in history


@pytest.mark.parametrize(
    "problem", ["csrf", "missing_assessment", "stale_review", "duplicate", "oversize", "media_type"]
)
def test_browser_write_guards_prevent_unreviewed_or_stale_decisions(repo, review_clock, client, problem):
    case = complete(repo, review_clock)
    proposal = save(repo, case)
    path = views.review_path(COMPANY, proposal.revision_id)
    opened = client.get(path, headers=headers())
    fields = submitted(opened.text)
    if problem == "csrf":
        fields["csrf"] = "invalid-\u2603"
    elif problem == "missing_assessment":
        fields["alternative_explanations"] = ""
    elif problem == "stale_review":
        finance_review(repo, proposal)
    if problem == "duplicate":
        response = client.post(
            path + "/decision",
            content="csrf=a&csrf=b",
            headers={**headers(), "Content-Type": "application/x-www-form-urlencoded"},
        )
    elif problem == "oversize":
        response = client.post(
            path + "/decision",
            content=b"x" * (64 * 1024 + 1),
            headers={**headers(), "Content-Type": "application/x-www-form-urlencoded"},
        )
    elif problem == "media_type":
        response = client.post(path + "/decision", json=fields, headers=headers())
    else:
        response = client.post(path + "/decision", data=fields, headers=headers())
    assert (
        response.status_code
        == {
            "csrf": 403,
            "missing_assessment": 422,
            "stale_review": 409,
            "duplicate": 422,
            "oversize": 413,
            "media_type": 415,
        }[problem]
    )
    with security.principal_scope(FINANCE):
        assert len(repo.list_private_attribution_reviews(COMPANY, proposal.revision_id)) == (
            1 if problem == "stale_review" else 0
        )
    if problem in {"missing_assessment", "stale_review"}:
        assert "Fictional finance decision" in response.text


def test_human_scope_and_finance_roles_precede_form_parsing(repo, review_clock, client):
    case = complete(repo, review_clock)
    proposal = save(repo, case)
    path = views.review_path(COMPANY, proposal.revision_id)
    assert client.get(path).status_code == 401
    for person in ("model", "foreign"):
        assert client.get(path, headers=headers(person)).status_code == 404
        assert (
            client.post(path + "/decision", content=b"unparsed-private-text", headers=headers(person)).status_code
            == 404
        )
    assert client.get("/private-reviews", headers=headers("model")).status_code == 404
    assert (
        client.post(path + "/decision", content=b"unparsed-private-text", headers=headers("operator")).status_code
        == 404
    )
    assert "Accept reviewed claims" not in client.get(path, headers=headers("operator")).text


def test_review_notes_fingerprint_binds_exact_assessment_and_versions():
    fields = dict(
        csrf="unhashed",
        idempotency_key="note",
        expected_previous_sha256="",
        expected_attribution_sha256="a" * 64,
        expected_execution_head_sha256="b" * 64,
        decision="accept",
        rationale="Rationale",
        **{key: key for key in views.ASSESSMENTS},
    )
    request = private_review.review_note_request(fields)
    note = dict(
        decision="accept",
        rationale="Rationale",
        assessment={key: key for key in views.ASSESSMENTS},
        attribution_sha256="a" * 64,
        execution_head_sha256="b" * 64,
        previous_review_sha256=None,
    )
    expected = hashlib.sha256(json.dumps(note, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert request.evidence.sha256 == expected
    assert private_review.review_note_request({**fields, "csrf": "changed"}).evidence.sha256 == expected
    assert private_review.review_note_request({**fields, "rationale": "Changed"}).evidence.sha256 != expected
    with pytest.raises(ValueError, match="unknown"):
        private_review.review_note_request({**fields, "external_verified": "true"})
    changes = private_review.review_note_request({**fields, "decision": "request_changes"})
    assert changes.assessment is None and "Alternative explanations: alternative_explanations" in changes.rationale
    assert "Additional review notes" in changes.rationale


def test_empty_private_index_does_not_claim_real_or_fictional_company_records():
    html = views.index_page([])
    assert "No private claims to review" in html
    assert "Private review records; source origin shown per case" in html
    assert "Permissioned private company data" not in html and "Synthetic company data" not in html
