"""Building blocks shared by real source adapters (PVC-110).

- `DatasetSource`: an adapter that provides some datasets for a company (vendor APIs provide a subset).
- `dataset_from_records`: validates rows, registers canonical content as evidence (deterministic ids), and
  returns a `Dataset`.
- `ApiClient`: egress-checked HTTP with retry-able classification: 429/5xx/timeouts -> TransientSourceError,
  401/403/404 and other 4xx -> SourceError.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from ..domain.source_models import RECORD_TYPES, Dataset, DatasetKind, parse_rows, to_csv
from ..egress import checked_client
from .base import EvidenceSink, SourceError, TransientSourceError, make_evidence


class DatasetSource(Protocol):
    name: str
    provides: frozenset[DatasetKind]

    def load_datasets(self, company_id: str, sink: EvidenceSink | None) -> dict[DatasetKind, Dataset]: ...


def dataset_from_records(
    kind: DatasetKind,
    company_id: str,
    rows: Iterable[dict[str, Any]],
    *,
    source_uri: str,
    as_of: datetime | None,
    sink: EvidenceSink | None,
    raw_payload: Any = None,
) -> Dataset:
    """Validate mapped rows and register evidence.

    Evidence content is the raw vendor payload when given (canonical JSON), otherwise the canonical CSV of the
    validated records, so identical source content always yields the same evidence id.
    """
    rows = [{**r, "company_id": company_id} for r in rows]
    records, errors = parse_rows(RECORD_TYPES[kind], rows, source_uri)
    if raw_payload is not None:
        content = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    else:
        content = to_csv(records).encode()
    as_of = as_of or datetime.now(UTC).replace(microsecond=0)
    ev = make_evidence(company_id, source_uri, f"dataset:{kind.value}", content, as_of, {"dataset": kind.value})
    if sink:
        sink.add_evidence(ev)
    return Dataset(
        kind=kind, records=records, evidence_id=ev.evidence_id, as_of=as_of, source_uri=source_uri, row_errors=errors
    )


class ApiClient:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = checked_client(
            base_url=self.base_url, headers=headers, timeout=timeout, **({"transport": transport} if transport else {})
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = self.client.get(path, params=params)
        except httpx.TimeoutException as e:
            raise TransientSourceError(f"timeout calling {path}") from e
        except httpx.TransportError as e:
            raise TransientSourceError(f"network error calling {path}: {type(e).__name__}") from e
        if r.status_code == 429 or r.status_code >= 500:
            raise TransientSourceError(f"{r.status_code} from {path}")
        if r.status_code >= 400:
            raise SourceError(f"{r.status_code} from {path}")
        try:
            return r.json()
        except ValueError as e:
            raise SourceError(f"non-JSON response from {path}") from e

    def close(self) -> None:
        self.client.close()
