"""CSV export-drop adapter (PVC-111, PVC-114): portfolio companies export datasets as CSV files.

Layout: <root>/<company_id>/company.json, manifest.json ({"reference_date": "...", "datasets": {"pnl":
{"file": "pnl.csv", "as_of": "..."}}}) and one CSV per dataset with the columns in docs/data_contracts.md. This
is the same layout the fixture generator writes, so fixtures double as a conformance sample. `reference_date`
may be "today".
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

from ..domain.dataset import CompanyData
from ..domain.source_models import RECORD_TYPES, CompanyProfile, Dataset, DatasetKind, parse_csv
from ..security import validate_company_id
from .base import EvidenceSink, SourceError, StagedEvidence, make_evidence


class CsvExportAdapter:
    name = "csv_export"
    uri_scheme = "file"

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def list_companies(self) -> list[str]:
        return (
            sorted(p.name for p in self.root.iterdir() if (p / "manifest.json").exists()) if self.root.exists() else []
        )

    def _manifest(self, company_id: str) -> dict:  # type: ignore[type-arg]
        path = self._path(company_id, "manifest.json")
        if not path.exists():
            raise SourceError(f"No export found for {company_id!r} under {self.root}")
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def _path(self, company_id: str, name: str) -> Path:
        validate_company_id(company_id)
        root = self.root.resolve()
        company = root / company_id
        # Company links must not redirect an import to a sibling tenant.
        if company.resolve() != company:
            raise SourceError("Company export directory must not be a symlink")
        path = (company / name).resolve()
        if not path.is_relative_to(company) or path == company:
            raise SourceError("Export path escapes the company directory")
        return path

    def reference_date(self, company_id: str) -> date:
        ref = self._manifest(company_id).get("reference_date", "today")
        return datetime.now(UTC).date() if ref == "today" else date.fromisoformat(ref)

    def load(self, company_id: str, sink: EvidenceSink | None = None) -> CompanyData:
        manifest = self._manifest(company_id)
        staged = StagedEvidence()
        prof_bytes = self._path(company_id, "company.json").read_bytes()
        profile = CompanyProfile.model_validate_json(prof_bytes)
        if profile.company_id != company_id:
            raise SourceError(f"company.json declares {profile.company_id!r}, expected {company_id!r}")
        pev = make_evidence(
            company_id, f"{self.uri_scheme}://{company_id}/company.json", "company_profile", prof_bytes, None
        )
        staged.add_evidence(pev)
        data = CompanyData(
            profile=profile, profile_evidence_id=pev.evidence_id, reference_date=self.reference_date(company_id)
        )
        for name, meta in manifest.get("datasets", {}).items():
            kind = DatasetKind(name)
            path = self._path(company_id, meta["file"])
            if not path.exists():
                continue  # declared but not delivered: sufficiency reports it as missing
            raw = path.read_bytes()
            as_of = (
                datetime.fromisoformat(meta["as_of"])
                if meta.get("as_of")
                else datetime.fromtimestamp(path.stat().st_mtime, UTC)
            )
            uri = f"{self.uri_scheme}://{company_id}/{meta['file']}"
            ev = make_evidence(company_id, uri, f"dataset:{kind.value}", raw, as_of, {"dataset": kind.value})
            text = raw.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or reader.fieldnames.count("company_id") != 1:
                raise SourceError("Export must declare exactly one company_id column")
            # Inspect every raw row before parsing: malformed foreign rows must never
            # disappear into the validation-error list while their bytes are published.
            if any(row.get("company_id") != company_id or None in row for row in reader):
                raise SourceError(f"{meta['file']} contains rows for other companies or malformed columns")
            records, errors = parse_csv(RECORD_TYPES[kind], text, meta["file"])
            staged.add_evidence(ev)
            data.datasets[kind] = Dataset(
                kind=kind, records=records, evidence_id=ev.evidence_id, as_of=as_of, source_uri=uri, row_errors=errors
            )
        staged.publish(sink)
        return data
