"""Fixture-backed source adapter using the same validated import path as CSV exports."""

from __future__ import annotations

from pathlib import Path

from .csv_export import CsvExportAdapter

# Wheels include the same committed synthetic data used by source-tree tests.
# Prefer installed package data; the fallback supports editable development.
_PACKAGED_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "companies"
DEFAULT_ROOT = (
    _PACKAGED_ROOT
    if _PACKAGED_ROOT.is_dir()
    else Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "companies"
)


class FixtureAdapter(CsvExportAdapter):
    name = "fixtures"
    uri_scheme = "fixture"

    def __init__(self, root: Path | str | None = None):
        super().__init__(root if root is not None else DEFAULT_ROOT)
