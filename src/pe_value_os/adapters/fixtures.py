"""Fixture-backed source adapter (PVC-035): reads generated companies as if they were source systems."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ..domain.dataset import CompanyData
from ..domain.source_models import RECORD_TYPES, CompanyProfile, Dataset, DatasetKind, parse_csv
from .base import EvidenceSink, SourceError, make_evidence

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "companies"


class FixtureAdapter:
    name = "fixtures"

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else DEFAULT_ROOT

    def list_companies(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if (p / "manifest.json").exists())

    def _dir(self, company_id: str) -> Path:
        d = self.root / company_id
        if not (d / "manifest.json").exists():
            raise SourceError(f"Unknown fixture company {company_id!r}")
        return d

    def reference_date(self, company_id: str) -> date:
        manifest = json.loads((self._dir(company_id) / "manifest.json").read_text(encoding="utf-8"))
        return date.fromisoformat(manifest["reference_date"])

    def load(self, company_id: str, sink: EvidenceSink | None = None) -> CompanyData:
        d = self._dir(company_id)
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        profile_bytes = (d / "company.json").read_bytes()
        profile = CompanyProfile.model_validate_json(profile_bytes)
        prof_ev = make_evidence(
            company_id, f"fixture://{company_id}/company.json", "company_profile", profile_bytes, None
        )
        if sink:
            sink.add_evidence(prof_ev)
        data = CompanyData(
            profile=profile,
            profile_evidence_id=prof_ev.evidence_id,
            reference_date=date.fromisoformat(manifest["reference_date"]),
        )
        for kind_name, meta in manifest["datasets"].items():
            kind = DatasetKind(kind_name)
            path = d / meta["file"]
            raw = path.read_bytes()
            as_of = datetime.fromisoformat(meta["as_of"])
            uri = f"fixture://{company_id}/{meta['file']}"
            ev = make_evidence(company_id, uri, f"dataset:{kind.value}", raw, as_of, {"dataset": kind.value})
            if sink:
                sink.add_evidence(ev)
            records, errors = parse_csv(RECORD_TYPES[kind], raw.decode("utf-8"), meta["file"])
            records = [r for r in records if r.company_id == company_id]
            data.datasets[kind] = Dataset(
                kind=kind, records=records, evidence_id=ev.evidence_id, as_of=as_of, source_uri=uri, row_errors=errors
            )
        return data
