"""Independent browser-boundary checks for portfolio intake and evidence navigation."""

from __future__ import annotations

from pe_value_os.adapters.base import make_evidence
from pe_value_os.workflows import primary

from .test_executive_ui import COMPANY, OTHER, Document, approval_state, headers, post_form, scope
from .test_executive_ui import executive as executive


def test_queued_company_without_intake_has_useful_portfolio_and_review(executive):
    ctx, _, client = executive
    with scope(OTHER):
        queued, _ = primary.start(ctx, OTHER, "human:executive-test")
    response = client.get("/", headers=headers("both"))
    assert response.status_code == 200
    assert f"/runs/{queued.run_id}/review" in response.text
    assert "collecting and analyzing evidence" in response.text
    review = client.get(f"/runs/{queued.run_id}/review", headers=headers("both"))
    assert review.status_code == 200
    assert "A decision-ready plan is not available" in review.text
    assert not Document(review.text).decision_forms()
    assert client.get(f"/companies/{OTHER}/kpis?run_id={queued.run_id}", headers=headers("both")).status_code == 200


def test_empty_authorized_portfolio_does_not_expose_other_company(executive):
    _, _, client = executive
    page = client.get("/", headers=headers("other"))
    assert page.status_code == 200
    assert "Your portfolio starts here" in page.text
    assert COMPANY not in page.text


def test_evidence_context_cannot_claim_another_authorized_company(executive):
    ctx, run_id, client = executive
    with scope(COMPANY, OTHER):
        evidence_id = ctx.repo.list_evidence(COMPANY)[0].evidence_id
        other, _ = primary.start(ctx, OTHER, "human:executive-test")
    valid = client.get(f"/evidence/{evidence_id}/review?run_id={run_id}", headers=headers("both"))
    assert valid.status_code == 200
    assert f"/runs/{run_id}/review#evidence" in valid.text
    wrong_context = client.get(f"/evidence/{evidence_id}/review?run_id={other.run_id}", headers=headers("both"))
    assert wrong_context.status_code == 404


def test_csv_preview_is_bounded_and_original_remains_exact(executive):
    ctx, run_id, client = executive
    header = ",".join(f"column-{i}" for i in range(12))
    row = ",".join(["<img src=x onerror=alert(1)>", *[f"cell-{i}" for i in range(11)]])
    content = (header + "\n" + "\n".join([row] * 20)).encode()
    record = make_evidence(COMPANY, "fixture://tables/inspection.csv", "fixture", content, None)
    with scope():
        evidence_id = ctx.repo.add_evidence(record)
    preview = client.get(f"/evidence/{evidence_id}/review?run_id={run_id}", headers=headers())
    assert preview.status_code == 200
    assert "<img src=x" not in preview.text
    document = Document(preview.text)
    assert sum(tag == "td" for tag, _ in document.elements) == 120
    assert sum(tag == "th" for tag, _ in document.elements) == 10
    raw = client.get(f"/evidence/{evidence_id}", headers=headers())
    assert raw.content == content
    assert raw.headers["x-content-hash"] == record.content_hash
    assert "nosniff" == raw.headers["x-content-type-options"]


def test_duplicate_browser_decision_does_not_create_another_audit_event(executive):
    ctx, run_id, client = executive
    assert post_form(client, run_id, "approved", rationale="Review complete").status_code == 303
    replay = client.post(
        f"/runs/{run_id}/approvals",
        headers=headers(),
        json={"decision": "approved", "rationale": "Repeated browser request"},
    )
    assert replay.status_code == 422
    approvals, events = approval_state(ctx, run_id)
    assert len([a for a in approvals if a.decision]) == 1
    assert len(events) == 1


def test_development_cookie_cannot_open_production_pages(executive, monkeypatch):
    _, run_id, client = executive
    client.cookies.set("pvc_dev_session", "approver")
    monkeypatch.setenv("PVC_ENV", "prod")
    for path in ("/", f"/runs/{run_id}/review", f"/companies/{COMPANY}/kpis"):
        assert client.get(path).status_code == 401
    response = client.post("/dev/login", data={"token": "approver", "csrf": "unused"})
    assert response.status_code == 404
