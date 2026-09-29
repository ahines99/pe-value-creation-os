"""Private preflight rejects unsafe batches without granting authority or leaking inputs."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from pydantic import ValidationError

from pe_value_os import security
from pe_value_os.cli import main
from pe_value_os.diligence import private_intake as intake

NOW = datetime(2026, 9, 29, 18, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "pilot-intake"


@pytest.fixture
def inputs():
    policy = intake.parse_private(intake.IntakePolicy, (FIXTURES / "policy.json").read_bytes())
    manifest = intake.parse_private(intake.IntakeManifest, (FIXTURES / "manifest.json").read_bytes())
    return policy, manifest, (FIXTURES / "ledger.json").read_bytes()


@pytest.fixture(autouse=True)
def operator():
    principal = security.Principal(
        "human:fixture-operator",
        frozenset({"pilot-fixture"}),
        frozenset({"operator"}),
        "human",
        frozenset({"pvc.read"}),
    )
    with security.principal_scope(principal):
        yield principal


def rewrite(inputs, mutate):
    policy, manifest, raw = inputs
    body = json.loads(raw)
    mutate(body)
    updated = json.dumps(body).encode()
    manifest = manifest.model_copy(
        update={
            "source_sha256": hashlib.sha256(updated).hexdigest(),
            "record_count": len(body["rows"]),
        }
    )
    return policy, manifest, updated


def codes(report):
    return {i.code for i in report.issues}


def test_worked_debits_credits_and_cash_reconcile_but_grant_no_authority(inputs):
    report = intake.assess_intake(*inputs, now=NOW)
    assert report.status == "ready_for_finance_review"
    amounts = {c.component: c.observed for c in report.controls}
    assert amounts == {
        "revenue": Decimal("980.00"),
        "operating_expense": Decimal("-300.00"),
        "implementation_expense": Decimal("-50.00"),
        "operating_cash": Decimal("600.00"),
        "working_capital_cash": Decimal("40.00"),
        "capex_cash": Decimal("-100.00"),
    }
    assert all(c.difference == 0 for c in report.controls)
    assert next(c.source_rows for c in report.controls if c.component == "revenue") == 2
    assert report.classification == "permissioned_private"
    assert not report.data_admitted and not report.authorization_verified
    assert not report.finance_reviewed and not report.operating_action_authorized
    with pytest.raises(ValueError, match="cannot be exported"):
        report.require_public()


def test_public_renderer_cannot_publish_private_intake_receipt(inputs, tmp_path):
    from pe_value_os.diligence.render import build_public_report

    report = intake.assess_intake(*inputs, now=NOW)
    source = tmp_path / "private-intake.json"
    source.write_text(report.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError):
        build_public_report(source, tmp_path / "public" / "report")
    assert not (tmp_path / "public").exists()


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_mapping_sign_must_be_an_explicit_integer(inputs, value):
    policy, _, _ = inputs
    raw = policy.model_dump(mode="json")
    raw["mappings"][0]["multiplier"] = value
    with pytest.raises(ValueError):
        intake.IntakePolicy.model_validate(raw)


@pytest.mark.parametrize(
    "change,expected",
    [
        (lambda b: b["rows"].append(b["rows"][0].copy()), "duplicate_source_row"),
        (lambda b: b["rows"][0].update(entity_id="another-entity"), "row_scope_mismatch"),
        (lambda b: b["rows"][0].update(currency="EUR"), "row_scope_mismatch"),
        (lambda b: b["rows"][0].update(account_code="UNKNOWN"), "unmapped_account"),
        (lambda b: b["rows"][0].update(period="2026-02-01"), "row_period_outside_scope"),
        (lambda b: b["rows"][0].update(period="2026-01-02"), "row_period_outside_scope"),
        (lambda b: b["rows"].pop(), "missing_component_rows"),
        (lambda b: b["rows"][0].update(amount="1000.01"), "control_total_mismatch"),
        (lambda b: b["rows"][0].update(amount="1000.001"), "invalid_ledger_schema"),
        (lambda b: b["rows"][0].update(amount=1000.01), "invalid_ledger_schema"),
        (lambda b: b["rows"][0].update(amount=True), "invalid_ledger_schema"),
        (lambda b: b["rows"][0].update(amount="NaN"), "invalid_ledger_schema"),
        (lambda b: b["rows"][0].update(customer_email="private-canary@example.invalid"), "invalid_ledger_schema"),
    ],
)
def test_entire_batch_quarantined_for_row_defects_without_echoing_input(inputs, change, expected):
    report = intake.assess_intake(*rewrite(inputs, change), now=NOW)
    assert report.status == "quarantined" and expected in codes(report)
    assert not report.data_admitted
    assert "private-canary" not in report.model_dump_json()
    if expected == "duplicate_source_row":
        assert next(i.row_numbers for i in report.issues if i.code == expected) == (1, 8)


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"company_id": "another-company"}, "company_scope_mismatch"),
        ({"policy_sha256": "0" * 64}, "policy_fingerprint_mismatch"),
        ({"source_sha256": "0" * 64}, "source_fingerprint_mismatch"),
        ({"record_count": 8}, "record_count_mismatch"),
        ({"data_cutoff": "2026-02-28"}, "cutoff_mismatch"),
        ({"extracted_at": "2026-09-30T18:00:00Z"}, "extraction_outside_processing_window"),
        ({"extracted_at": "2025-12-31T18:00:00Z"}, "extraction_outside_processing_window"),
    ],
)
def test_manifest_boundaries(inputs, change, expected):
    policy, manifest, raw = inputs
    manifest = intake.IntakeManifest.model_validate({**manifest.model_dump(mode="json"), **change})
    report = intake.assess_intake(policy, manifest, raw, now=NOW)
    assert report.status == "quarantined" and expected in codes(report)
    if expected != "record_count_mismatch":
        assert not report.controls


def test_expiry_and_retention_are_enforced_at_the_boundary(inputs):
    policy, _, _ = inputs
    assert "outside_processing_window" in codes(intake.assess_intake(*inputs, now=policy.expires_at))
    assert "retention_expired" in codes(intake.assess_intake(*inputs, now=policy.retain_until))
    with pytest.raises(ValueError, match="timezone"):
        intake.assess_intake(*inputs, now=NOW.replace(tzinfo=None))


def test_duplicate_json_keys_are_rejected_even_when_the_file_hash_matches(inputs):
    policy, manifest, raw = inputs
    raw = raw.replace(b'"amount": "1000.00"', b'"amount": "999.00", "amount": "1000.00"')
    manifest = manifest.model_copy(update={"source_sha256": hashlib.sha256(raw).hexdigest()})
    assert codes(intake.assess_intake(policy, manifest, raw, now=NOW)) == {"invalid_ledger_schema"}
    with pytest.raises(ValueError, match="duplicate"):
        intake.parse_private(intake.IntakePolicy, b'{"company_id":"a","company_id":"b"}')


@pytest.mark.parametrize("field", ["controls", "mappings"])
def test_policy_requires_unique_complete_controls_and_account_mapping(inputs, field):
    policy, _, _ = inputs
    raw = policy.model_dump(mode="json")
    raw[field].append(raw[field][0])
    with pytest.raises(ValidationError):
        intake.IntakePolicy.model_validate(raw)
    raw = policy.model_dump(mode="json")
    raw[field].pop()
    with pytest.raises(ValidationError):
        intake.IntakePolicy.model_validate(raw)


@pytest.mark.parametrize(
    "principal",
    [
        security.Principal("human:other", frozenset({"other-company"}), frozenset({"operator"}), "human"),
        security.Principal("model", frozenset({"pilot-fixture"}), frozenset({"operator"}), "model"),
        security.Principal("service", frozenset({"pilot-fixture"}), frozenset({"operator"})),
        security.Principal("human:reader", frozenset({"pilot-fixture"}), frozenset(), "human"),
        security.Principal(
            "human:no-scope", frozenset({"pilot-fixture"}), frozenset({"operator"}), "human", frozenset()
        ),
    ],
)
def test_company_human_role_and_oauth_scope_required(inputs, principal):
    with security.principal_scope(principal), pytest.raises(security.ScopeError):
        intake.assess_intake(*inputs, now=NOW)


def test_explicit_zero_is_required_not_inferred_from_no_rows(inputs):
    policy, manifest, raw = inputs
    body = policy.model_dump(mode="json")
    body["controls"][-1]["amount"] = "0"
    policy = intake.IntakePolicy.model_validate(body)
    manifest = manifest.model_copy(update={"policy_sha256": intake.fingerprint(policy)})
    updated = rewrite((policy, manifest, raw), lambda b: b["rows"].pop())
    assert "missing_component_rows" in codes(intake.assess_intake(*updated, now=NOW))
    updated = rewrite((policy, manifest, raw), lambda b: b["rows"][-1].update(amount="0"))
    assert intake.assess_intake(*updated, now=NOW).status == "ready_for_finance_review"


def test_low_caller_decimal_precision_does_not_change_reconciliation(inputs):
    with localcontext() as context:
        context.prec = 3
        report = intake.assess_intake(*inputs, now=NOW)
    assert report.status == "ready_for_finance_review"
    assert next(c.observed for c in report.controls if c.component == "revenue") == Decimal("980.00")


def test_control_difference_retains_cents_under_low_caller_precision(inputs):
    changed = rewrite(inputs, lambda b: b["rows"][0].update(amount="1000000.01"))
    with localcontext() as context:
        context.prec = 3
        report = intake.assess_intake(*changed, now=NOW)
    revenue = next(c for c in report.controls if c.component == "revenue")
    assert revenue.difference == Decimal("999000.01")
    assert report.status == "quarantined"


def test_large_balances_cancel_without_losing_the_small_business_difference(inputs):
    def add_offsetting_rows(body):
        template = body["rows"][0]
        body["rows"].insert(0, {**template, "source_row_id": "large-debit", "amount": "9999999999999999999999.99"})
        body["rows"].append({**template, "source_row_id": "large-credit", "amount": "-9999999999999999999999.99"})

    with localcontext() as context:
        context.prec = 6
        report = intake.assess_intake(*rewrite(inputs, add_offsetting_rows), now=NOW)
    assert report.status == "ready_for_finance_review"
    assert next(c.observed for c in report.controls if c.component == "revenue") == Decimal("980.00")


def test_source_size_limit_prevents_parsing_even_with_a_matching_hash(inputs, monkeypatch):
    monkeypatch.setattr(intake, "MAX_BYTES", 10)
    report = intake.assess_intake(*inputs, now=NOW)
    assert codes(report) == {"source_size_limit"} and not report.controls


def install_files(tmp_path, monkeypatch, inputs):
    monkeypatch.chdir(tmp_path)
    policy, manifest, raw = inputs
    paths = [tmp_path / name for name in ("policy.json", "manifest.json", "ledger.json")]
    paths[0].write_text(policy.model_dump_json(), encoding="utf-8")
    paths[1].write_text(manifest.model_dump_json(), encoding="utf-8")
    paths[2].write_bytes(raw)

    class Clock:
        @staticmethod
        def now(zone):
            return NOW

    monkeypatch.setattr(intake, "datetime", Clock)
    return paths


def test_private_receipt_preserves_old_inputs_and_rejects_overwrite(inputs, tmp_path, monkeypatch):
    paths = install_files(tmp_path, monkeypatch, inputs)
    before = [p.read_bytes() for p in paths]
    result = intake.check_files(*paths, "review-one")
    destination = tmp_path / "var/permissioned-pilot/review-one.json"
    assert intake.IntakeReport.model_validate_json(destination.read_bytes()) == result
    with pytest.raises(FileExistsError):
        intake.check_files(*paths, "review-one")
    assert [p.read_bytes() for p in paths] == before
    intake.check_files(*paths, "review-two")
    assert len(list(destination.parent.glob("*.json"))) == 2


def test_running_inside_docs_keeps_receipts_out_of_the_static_tree(inputs, tmp_path, monkeypatch):
    paths = install_files(tmp_path, monkeypatch, inputs)
    (tmp_path / ".git").write_text("gitdir: fixture-only", encoding="utf-8")
    docs = tmp_path / "docs/portfolio"
    docs.mkdir(parents=True)
    monkeypatch.chdir(docs)
    intake.check_files(*paths, "nested-cwd")
    assert (tmp_path / "var/permissioned-pilot/nested-cwd.json").exists()
    assert not (docs / "var").exists()


@pytest.mark.parametrize("name", ["../../docs/exposed", "../public-diligence/exposed"])
def test_public_path_escape_is_rejected(inputs, tmp_path, monkeypatch, name):
    paths = install_files(tmp_path, monkeypatch, inputs)
    with pytest.raises(ValueError, match="within"):
        intake.check_files(*paths, name)
    assert not (tmp_path / "docs").exists()


def test_receipt_cannot_overwrite_an_input(inputs, tmp_path, monkeypatch):
    paths = install_files(tmp_path, monkeypatch, inputs)
    root = tmp_path / "var/permissioned-pilot"
    root.mkdir(parents=True)
    paths[2] = root / "ledger.json"
    paths[2].write_bytes(inputs[2])
    before = paths[2].read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        intake.check_files(*paths, "ledger")
    assert paths[2].read_bytes() == before


def test_symlinked_receipt_root_is_rejected(inputs, tmp_path, monkeypatch):
    paths = install_files(tmp_path, monkeypatch, inputs)
    outside = tmp_path / "public"
    outside.mkdir()
    (tmp_path / "var").mkdir()
    try:
        (tmp_path / "var/permissioned-pilot").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS requires symlink privilege")
    with pytest.raises(ValueError, match="symbolic"):
        intake.check_files(*paths, "exposed")
    assert not list(outside.iterdir())


def test_unauthorized_operator_cannot_open_ledger(inputs, tmp_path, monkeypatch):
    paths = install_files(tmp_path, monkeypatch, inputs)
    paths[2].unlink()
    with (
        security.principal_scope(security.Principal("model", frozenset({"pilot-fixture"}))),
        pytest.raises(security.ScopeError),
    ):
        intake.check_files(*paths, "denied")
    assert not (tmp_path / "var").exists()


@pytest.mark.parametrize("field,value", [("company_id", "another-company"), ("policy_sha256", "0" * 64)])
def test_mismatched_manifest_cannot_open_ledger(inputs, tmp_path, monkeypatch, field, value):
    paths = install_files(tmp_path, monkeypatch, inputs)
    manifest = json.loads(paths[1].read_bytes())
    manifest[field] = value
    paths[1].write_text(json.dumps(manifest), encoding="utf-8")
    paths[2].unlink()
    with pytest.raises(ValueError, match="before opening"):
        intake.check_files(*paths, "denied")
    assert not (tmp_path / "var").exists()


def test_expired_processing_window_cannot_open_ledger(inputs, tmp_path, monkeypatch):
    paths = install_files(tmp_path, monkeypatch, inputs)

    class Clock:
        @staticmethod
        def now(zone):
            return inputs[0].expires_at

    monkeypatch.setattr(intake, "datetime", Clock)
    paths[2].unlink()
    with pytest.raises(ValueError, match="before opening"):
        intake.check_files(*paths, "expired")
    assert not (tmp_path / "var").exists()


def test_cli_only_prints_safe_status_and_keeps_failed_validation_values_private(inputs, tmp_path, monkeypatch, capsys):
    paths = install_files(tmp_path, monkeypatch, inputs)
    monkeypatch.setenv("PVC_OPERATOR_COMPANIES", "pilot-fixture")
    args = ["pilot-intake-check", "--policy", str(paths[0]), "--manifest", str(paths[1]), "--ledger", str(paths[2])]
    assert main(args) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "ready_for_finance_review",
        "issue_count": 0,
        "authorization_verified": False,
        "data_admitted": False,
    }
    assert "pilot-fixture" not in output.out and "980" not in output.out
    paths[0].write_text('{"purpose":"private-canary"}', encoding="utf-8")
    assert main(args) == 2
    output = capsys.readouterr()
    assert "private-canary" not in output.err and str(tmp_path) not in output.err


def test_cli_has_no_implicit_demo_scope(inputs, tmp_path, monkeypatch, capsys):
    paths = install_files(tmp_path, monkeypatch, inputs)
    monkeypatch.delenv("PVC_OPERATOR_COMPANIES", raising=False)
    monkeypatch.setenv("PVC_ENV", "dev")
    assert (
        main(["pilot-intake-check", "--policy", str(paths[0]), "--manifest", str(paths[1]), "--ledger", str(paths[2])])
        == 2
    )
    assert not (tmp_path / "var").exists()
    assert "pilot-fixture" not in capsys.readouterr().err
