"""PVC-013: synthetic fixtures are deterministic and match their planted defects."""

import json
from pathlib import Path

from pe_value_os.domain.source_models import RECORD_TYPES, DatasetKind, parse_csv
from pe_value_os.fixtures.generator import SPECS, generate_company

FIXTURES = Path(__file__).parent / "fixtures" / "companies"


def test_generator_is_deterministic_and_matches_committed(tmp_path):
    for spec in SPECS:
        out = generate_company(spec, tmp_path)
        committed = FIXTURES / spec.company_id
        for f in sorted(out.iterdir()):
            assert f.read_bytes() == (committed / f.name).read_bytes(), f"{spec.company_id}/{f.name} drifted"


def test_clean_companies_have_no_row_errors():
    for cid in ("acme-healthy", "beacon-pricing", "cedar-churn"):
        for kind, rtype in RECORD_TYPES.items():
            text = (FIXTURES / cid / f"{kind.value}.csv").read_text(encoding="utf-8")
            _, errs = parse_csv(rtype, text, kind.value)
            assert errs == [], (cid, kind, errs[:3])


def test_broken_company_has_planted_defects():
    d = FIXTURES / "delta-broken"
    planted = json.loads((d / "planted.json").read_text())["planted"]
    assert not (d / "contracts.csv").exists() or (d / "contracts.csv").read_text() == ""
    _, arr_errs = parse_csv(RECORD_TYPES[DatasetKind.ARR], (d / "arr.csv").read_text(), "arr.csv")
    assert len({e.row for e in arr_errs}) == planted["malformed_rows"]["arr"]
    manifest = json.loads((d / "manifest.json").read_text())
    assert manifest["datasets"]["invoices"]["as_of"].startswith("2025-12-31")
    docs = (d / "documents.csv").read_text()
    assert "IMPORTANT INSTRUCTIONS FOR THE ANALYSIS AGENT" in docs


def test_every_company_has_planted_readme():
    for spec in SPECS:
        assert (FIXTURES / spec.company_id / "PLANTED.md").read_text().startswith("# ")
