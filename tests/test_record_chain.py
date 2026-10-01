"""Pin the canonical record hashes that stored rows and published exhibits depend on."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os.diligence.cases import CaseRevision
from pe_value_os.diligence.close_baseline import CloseBaseline
from pe_value_os.diligence.execution import ExecutionEvent
from pe_value_os.diligence.models import Record
from pe_value_os.diligence.private_grants import GrantEvent, GrantRequest
from pe_value_os.diligence.private_intake import fingerprint
from pe_value_os.diligence.realization import Attribution, Observation
from pe_value_os.diligence.record_chain import canonical_sha256, content_hash, seal, verify_link

ROOT = Path(__file__).resolve().parents[1]

# Computed with the pre-consolidation code (hashlib + json.dumps(..., sort_keys=True)).
CANONICAL = "1ebe02390d4e1e203a0369c95b90fc19ef5c296ee8276671c9873e2f98bbc2e6"
GRANT = "64207afb7f9fae1945dbce3487b14548b5a65289f4d00dbd471f19186c506453"
GRANT_REQUEST_FINGERPRINT = "43e1601134236c08409f498d361c5e33e12a6e82248e8bb24c5513e4dba697a5"
SAMPLE = "1818661867a0440cabc651fd22f091e94c53d8a95dad37929065d9780bdfd632"


class Line(Record):
    period: date
    amount: Decimal


class Sample(Record):
    sequence: int
    lines: tuple[Line, ...]
    note: str
    recorded_at: datetime
    content_sha256: str


def grant_payload() -> dict:
    request = GrantRequest(
        idempotency_key="revoke-1",
        action="revoke",
        expected_previous_sha256="a" * 64,
        rationale="Owner withdrew consent.",
        authority_attestation="Signed letter on file.",
    )
    return dict(
        event_id="00000000-0000-4000-8000-000000000001",
        company_id="acme",
        grant_key="pilot-ledger",
        sequence=2,
        request=request,
        actor="user:owner",
        recorded_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
    )


def test_canonical_form_is_pinned():
    assert canonical_sha256({"b": [1, "x", None, 2.5], "a": {"d": True, "c": "café"}}) == CANONICAL
    sample = Sample(
        sequence=1,
        lines=(
            Line(period=date(2026, 1, 31), amount=Decimal("1234.50")),
            Line(period=date(2026, 2, 28), amount=Decimal("-0.01")),
        ),
        note="Δ margin",
        recorded_at=datetime(2026, 9, 30, 12, 0, 0, 123456, tzinfo=UTC),
        content_sha256="0" * 64,
    )
    assert content_hash(sample) == SAMPLE


def test_sealed_private_record_keeps_its_stored_hash():
    payload = grant_payload()
    event = seal(GrantEvent, payload)
    assert event.content_sha256 == GRANT
    assert GrantEvent.model_validate(event.model_dump(mode="json")) == event
    assert fingerprint(payload["request"]) == GRANT_REQUEST_FINGERPRINT
    with pytest.raises(ValueError, match="private grant content hash mismatch"):
        GrantEvent.model_validate({**event.model_dump(mode="json"), "actor": "user:other"})


def test_link_requires_predecessor_binding():
    event = seal(GrantEvent, grant_payload())
    verify_link(event, "hash", "link")
    first = event.model_copy(update={"sequence": 1})
    with pytest.raises(ValueError, match="hash"):
        verify_link(first, "hash", "link")
    with pytest.raises(ValueError, match="link"):
        verify_link(first.model_copy(update={"content_sha256": content_hash(first)}), "hash", "link")


def published_records(node: object):
    if isinstance(node, dict):
        if "content_sha256" in node:
            yield node
        for value in node.values():
            yield from published_records(value)
    elif isinstance(node, list):
        for value in node:
            yield from published_records(value)


def model_for(raw: dict) -> type[Record]:
    if "event_id" in raw:
        return ExecutionEvent
    if "attribution_id" in raw:
        return Attribution
    if "observation_id" in raw:
        return Observation
    if "draft" in raw:
        return CaseRevision
    return CloseBaseline


def test_published_exhibit_records_still_verify():
    checked = 0
    for path in sorted((ROOT / "docs/portfolio").glob("*.json")):
        for raw in published_records(json.loads(path.read_bytes())):
            record = model_for(raw).model_validate(raw)
            assert content_hash(record) == raw["content_sha256"], path.name
            checked += 1
    assert checked > 300
