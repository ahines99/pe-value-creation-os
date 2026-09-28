"""Public fact lineage, financial bridges and export isolation; no vendor data or credentials."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pe_value_os.diligence.filing_pdf import FilingMap, Table, extract_filing, table_values
from pe_value_os.diligence.financials import analyze_facts
from pe_value_os.diligence.models import FactBundle, FiscalPeriod
from pe_value_os.diligence.render import build_public_report, render_baseline

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data/public/progress/annual-facts.json"
MAP = ROOT / "data/public/progress/fy2025-map.json"


def bundle() -> FactBundle:
    return FactBundle.model_validate_json(FACTS.read_bytes())


def tiny_mapping(raw: bytes) -> FilingMap:
    return FilingMap(
        company="Fictional Co",
        entity_id="test",
        ticker="TEST",
        title="Fictional filing",
        url="https://example.com/filing.pdf",
        accession="0000000001-26-000001",
        form="10-K",
        filed_on=date(2026, 1, 20),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        currency="USD",
        unit_scale=1000,
        entity_heading="FICTIONAL CO",
        tables=(
            Table(
                pdf_page=1,
                printed_page="1",
                heading="Income statement",
                unit_heading="(in thousands)",
                columns=({"label": "2025", "period": {"start": "2025-01-01", "end": "2025-12-31", "basis": "annual"}},),
                rows=(
                    {"metric": "revenue", "label": "Revenue"},
                    {"metric": "interest_expense", "label": "Interest expense"},
                ),
            ),
        ),
    )


def write_tiny_pdf(path: Path) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 12 Tf 20 TL 40 740 Td (FICTIONAL CO) Tj T* (Income statement) Tj T* (\\(in thousands\\)) Tj T* (2025) Tj T* (Revenue 1,000) Tj T* (Interest expense \\(25\\)) Tj T* (1) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)
    return path.read_bytes()


def test_pdf_extraction_preserves_units_signs_and_lineage(tmp_path):
    pdf = tmp_path / "fictional.pdf"
    mapping = tiny_mapping(write_tiny_pdf(pdf))
    result = extract_filing(pdf, mapping, datetime(2026, 2, 1, tzinfo=UTC), date(2026, 2, 1))
    assert [f.amount for f in result.facts] == [Decimal("1000000"), Decimal("-25000")]
    assert result.facts[0].reported_amount == 1000
    assert result.facts[0].source_row == "Revenue 1,000"
    assert result.documents[0].sha256 == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert len(result.documents[0].mapping_sha256) == 64
    pdf.write_bytes(pdf.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash"):
        extract_filing(pdf, mapping, datetime(2026, 2, 1, tzinfo=UTC), date(2026, 2, 1))


@pytest.mark.parametrize(
    "bad_row", ["Revenue —", "Revenue 1,000 2,000", "Revenue unknown", "Revenue 1e6", "Revenue 1,20"]
)
def test_unparseable_or_shifted_column_never_becomes_zero(bad_row):
    table = tiny_mapping(b"x").tables[0]
    text = f"Income statement\n(in thousands) 2025\n{bad_row}\nInterest expense (25)"
    with pytest.raises(ValueError):
        table_values(text, table)


def test_column_reordering_is_rejected():
    table = FilingMap.model_validate_json(MAP.read_bytes()).tables[0]
    with pytest.raises(ValueError, match="columns"):
        table_values(
            "Consolidated Statements of Operations\n(in thousands, except per share data)\nNovember 30, 2023 November 30, 2024 November 30, 2025",
            table,
        )


def test_scale_must_match_source_unit_heading():
    raw = tiny_mapping(b"x").model_dump(mode="json")
    raw["unit_scale"] = 1
    with pytest.raises(ValueError, match="scale of 1000"):
        FilingMap.model_validate(raw)


def test_independently_verified_filing_baseline_and_accounting_distinctions():
    result = analyze_facts(bundle())
    latest = result["periods"][-1]
    assert len(bundle().facts) == 81
    assert all(c["status"] == "matched" for c in latest["reconciliations"])
    assert latest["reported"]["revenue"]["value"] == Decimal("977831000")
    # Net income 73.133 + tax 8.495 + interest 70.850 + operating D&A 151.724.
    assert latest["derived"]["ebitda"]["value"] == Decimal("304202000")
    assert latest["derived"]["operating_income_before_da"]["value"] == Decimal("305014000")
    # CFO 235.187 - PP&E outlay 5.702. Neither figure is initiative savings.
    assert latest["derived"]["cfo_less_ppe"]["value"] == Decimal("229485000")
    assert latest["derived"]["ebitda"]["value"] - latest["derived"]["operating_income_before_da"]["value"] == Decimal(
        "-812000"
    )
    assert analyze_facts(bundle()) == result


def test_cross_statement_other_amortization_is_not_forced_to_match():
    periods = analyze_facts(bundle())["periods"]
    for period, difference in zip(periods[:2], (203000, 2106000), strict=True):
        check = next(c for c in period["reconciliations"] if c["target"] == "intangible_amortization")
        assert check["status"] == "mismatch" and check["difference"] == difference
        assert period["derived"]["ebitda"]["value"] is None
        assert period["reported"]["net_income"]["value"] is not None


def test_missing_component_withholds_earnings_instead_of_using_zero():
    raw = bundle().model_dump(mode="json")
    raw["facts"] = [f for f in raw["facts"] if f["metric"] != "ppe_depreciation"]
    result = analyze_facts(FactBundle.model_validate(raw))
    assert result["periods"][-1]["derived"]["ebitda"]["value"] is None
    assert result["periods"][-1]["derived"]["ebitda"]["missing"] == ["ppe_depreciation"]


@pytest.mark.parametrize("classification", ["licensed_private", "permissioned_private", "constructed"])
def test_public_export_rejects_other_source_classes_before_writing(tmp_path, classification):
    raw = bundle().model_dump(mode="json")
    raw["documents"][0]["classification"] = classification
    source = tmp_path / "input.json"
    source.write_text(FactBundle.model_validate(raw).model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="export rejects"):
        build_public_report(source, tmp_path / "public" / "memo")
    assert not (tmp_path / "public").exists()


def test_inconsistent_currency_blocks_bridge():
    raw = bundle().model_dump(mode="json")
    raw["facts"][0]["currency"] = "EUR"
    with pytest.raises(ValueError, match="currencies"):
        analyze_facts(FactBundle.model_validate(raw))


@pytest.mark.parametrize("metric", ["interest_expense", "ppe_purchases"])
def test_positive_outflow_requires_review_instead_of_reversing_cash_or_earnings(metric):
    raw = bundle().model_dump(mode="json")
    for fact in raw["facts"]:
        if fact["metric"] == metric:
            fact["reported_amount"] = str(abs(Decimal(fact["reported_amount"])))
    with pytest.raises(ValueError, match="signed nonpositive outflow"):
        analyze_facts(FactBundle.model_validate(raw))


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_document", "foreign_entity", "future_filing", "nan"])
def test_fact_registry_rejects_ambiguous_or_invalid_records(mutation):
    raw = bundle().model_dump(mode="json")
    if mutation == "duplicate":
        raw["facts"].append(raw["facts"][0])
    elif mutation == "unknown_document":
        raw["facts"][0]["document_id"] = "unregistered"
    elif mutation == "foreign_entity":
        raw["facts"][0]["entity_id"] = "other-company"
    elif mutation == "future_filing":
        raw["information_cutoff"] = "2026-01-19"
    else:
        raw["facts"][0]["reported_amount"] = "NaN"
    with pytest.raises(ValidationError):
        FactBundle.model_validate(raw)


def test_ytd_is_not_a_discrete_quarter_and_naive_retrieval_is_rejected():
    with pytest.raises(ValidationError, match="duration"):
        FiscalPeriod(start=date(2026, 1, 1), end=date(2026, 6, 30), basis="discrete_quarter")
    raw = bundle().model_dump(mode="json")
    raw["documents"][0]["retrieved_at"] = "2026-09-28T10:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        FactBundle.model_validate(raw)


def test_public_report_escapes_source_text_and_preserves_input(tmp_path):
    raw = bundle().model_dump(mode="json")
    raw["company"] = "<script>alert('company')</script>"
    raw["facts"][0]["source_row"] = "<script>alert('row')</script>"
    data = FactBundle.model_validate(raw)
    html = render_baseline(data, analyze_facts(data))
    assert "<script>" not in html and "&lt;script&gt;" in html
    source = tmp_path / "input.json"
    source.write_text(data.model_dump_json(), encoding="utf-8")
    before = source.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        build_public_report(source, source)
    assert source.read_bytes() == before
    output = build_public_report(source, tmp_path / "memo")
    assert output.exists() and output.with_suffix(".json").exists()
