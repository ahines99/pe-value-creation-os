"""Content hashes and predecessor links shared by append-only diligence records.

Stored rows and published exhibits depend on this exact canonical form: sorted
keys, the default `json.dumps` separators and no `default=`. Do not change it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypeVar

from .models import Record

R = TypeVar("R", bound=Record)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def content_hash(record: Record) -> str:
    """Hash every field except the stored hash itself."""
    return canonical_sha256(record.model_dump(mode="json", exclude={"content_sha256"}))


def seal(model: type[R], payload: dict[str, Any]) -> R:
    """Validate a new record with its content hash; payload values may still be models."""
    draft = model.model_construct(**{**payload, "content_sha256": "0" * 64})
    return model.model_validate({**payload, "content_sha256": content_hash(draft)})


def seal_json(model: type[R], raw: dict[str, Any]) -> R:
    """Validate a new record whose payload is already JSON-shaped; the hash covers `raw` as given."""
    return model.model_validate({**raw, "content_sha256": canonical_sha256(raw)})


def verify_link(record: Any, hash_error: str, link_error: str) -> None:
    """Reject changed content, or a sequence that disagrees with its predecessor binding."""
    if content_hash(record) != record.content_sha256:
        raise ValueError(hash_error)
    if (record.sequence == 1) != (record.request.expected_previous_sha256 is None):
        raise ValueError(link_error)
