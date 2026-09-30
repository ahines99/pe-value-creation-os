"""Private executive review packets and human-authored review-note fingerprints."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .private_attribution import AttributionAssessment, AttributionReviewRequest
from .private_execution import EvidenceBinding


def review_note_request(fields: dict[str, str]) -> AttributionReviewRequest:
    """The fingerprint covers the submitted note, never an unprovided external file."""
    allowed = {
        "csrf",
        "idempotency_key",
        "expected_previous_sha256",
        "expected_attribution_sha256",
        "expected_execution_head_sha256",
        "decision",
        "rationale",
        *AttributionAssessment.model_fields,
    }
    if set(fields) - allowed:
        raise ValueError("unknown private review form field")
    decision = fields.get("decision", "")
    assessment = (
        AttributionAssessment.model_validate(
            {key: fields.get(key, "").strip() for key in AttributionAssessment.model_fields}
        )
        if decision == "accept"
        else None
    )
    rationale = fields.get("rationale", "").strip()
    if decision != "accept":
        supplemental = [
            f"{key.replace('_', ' ').capitalize()}: {fields[key].strip()}"
            for key in AttributionAssessment.model_fields
            if fields.get(key, "").strip()
        ]
        if supplemental:
            rationale += "\n\nAdditional review notes:\n" + "\n".join(supplemental)
    note = dict(
        decision=decision,
        rationale=rationale,
        assessment=assessment.model_dump(mode="json") if assessment else None,
        attribution_sha256=fields.get("expected_attribution_sha256", ""),
        execution_head_sha256=fields.get("expected_execution_head_sha256") or None,
        previous_review_sha256=fields.get("expected_previous_sha256") or None,
    )
    fingerprint = hashlib.sha256(json.dumps(note, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return AttributionReviewRequest.model_validate(
        dict(
            idempotency_key=fields.get("idempotency_key", ""),
            expected_previous_sha256=note["previous_review_sha256"],
            expected_attribution_sha256=note["attribution_sha256"],
            expected_execution_head_sha256=note["execution_head_sha256"],
            decision=decision,
            rationale=note["rationale"],
            assessment=assessment,
            evidence=EvidenceBinding(
                reference="workspace-review-note:" + fingerprint,
                sha256=fingerprint,
                attestation="Notes authored by the authenticated reviewer in the private workspace. The fingerprint covers the submitted decision, rationale, assessment and exact review bindings; no external document authentication is asserted.",
            ),
        )
    )


def packet_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def packet_fingerprint(packet: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
