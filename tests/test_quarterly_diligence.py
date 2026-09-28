"""Fiscal basis, cross-filing arithmetic, dependency gates and dated acquisition context."""

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from scripts.build_public_case import assemble

from pe_value_os.diligence.filing_pdf import FilingMap, Table, extract_filing, table_values
from pe_value_os.diligence.financials import analyze_facts
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.quarterly import derive_quarters
from pe_value_os.diligence.render import build_public_report

DATA = Path(__file__).resolve().parents[1] / "data/public/progress"


def bundle():
    return FactBundle.model_validate_json((DATA / "financial-facts.json").read_bytes())


def quarter_table():
    raw = FilingMap.model_validate_json((DATA / "fy2026-q2-map.json").read_bytes()).tables[0].model_dump(mode="json")
    raw["rows"] = [{"metric": "revenue", "label": "Revenue"}]
    return Table.model_validate(raw)


HEADER = "Condensed Consolidated Statements of Operations\nThree Months Ended Six Months Ended\n(in thousands, except per share data) May 31, 2026 May 31, 2025 May 31, 2026 May 31, 2025\n"


def test_pdf_cover_identity_and_full_period_ids_with_shared_quarter_ytd_end(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for lines in (["FICTIONAL CO", "1"], [*HEADER.strip().splitlines(), "Revenue 100 90 200 180", "2"]):
        page = writer.add_blank_page(width=900, height=800)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
        stream = DecodedStreamObject()
        stream.set_data(
            ("BT /F1 10 Tf 20 TL 40 740 Td " + " T* ".join(f"({line}) Tj" for line in escaped) + " ET").encode()
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    pdf = tmp_path / "quarter.pdf"
    writer.write(pdf)
    mapping_raw = FilingMap.model_validate_json((DATA / "fy2026-q2-map.json").read_bytes()).model_dump(mode="json")
    table = quarter_table().model_dump(mode="json")
    table.update(pdf_page=2, printed_page="2")
    mapping_raw.update(
        company="Fictional Co",
        entity_heading="FICTIONAL CO",
        source_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        tables=[table],
    )
    mapping = FilingMap.model_validate(mapping_raw)
    result = extract_filing(pdf, mapping, datetime(2026, 9, 28, tzinfo=UTC), date(2026, 9, 28))
    assert len(result.facts) == len({f.fact_id for f in result.facts}) == 4
    assert [f.amount for f in result.facts] == [100000, 90000, 200000, 180000]
    with pytest.raises(ValueError):
        FilingMap.model_validate({**mapping_raw, "entity_heading": " "})
    with pytest.raises(ValueError, match="entity identity"):
        extract_filing(
            pdf,
            mapping.model_copy(update={"entity_heading": "WRONG ENTITY"}),
            datetime(2026, 9, 28, tzinfo=UTC),
            date(2026, 9, 28),
        )


def test_repeated_dates_select_reviewed_occurrences_not_the_first_match():
    assert table_values(HEADER + "Revenue 100 90 200 180", quarter_table())["revenue"] == (100, 90, 200, 180)
    raw = quarter_table().model_dump(mode="json")
    raw["columns"][2]["occurrence"] = 0
    with pytest.raises(ValueError, match="columns"):
        table_values(HEADER + "Revenue 100 90 200 180", Table.model_validate(raw))


def test_missing_group_heading_and_dates_only_in_a_footnote_are_rejected():
    with pytest.raises(ValueError, match="group heading"):
        table_values(
            HEADER.replace("Six Months Ended", "Nine Months Ended") + "Revenue 100 90 200 180", quarter_table()
        )
    with pytest.raises(ValueError, match="columns"):
        table_values(
            "Condensed Consolidated Statements of Operations\nThree Months Ended Six Months Ended\n(in thousands, except per share data)\nRevenue 100 90 200 180\nMay 31, 2026 May 31, 2025 May 31, 2026 May 31, 2025",
            quarter_table(),
        )


def test_assembly_preserves_original_annual_records_and_reproduces_reviewed_quarters():
    current = bundle()
    assert assemble(DATA) == current
    assert len(current.facts) == 241
    annual = FactBundle.model_validate_json((DATA / "annual-facts.json").read_bytes())
    assert current.facts[:81] == annual.facts
    assert current.documents[0] == annual.documents[0]
    for index in (1, 2):
        source = FactBundle.model_validate_json((DATA / f"fy2026-q{index}-facts.json").read_bytes())
        mapping = FilingMap.model_validate_json((DATA / f"fy2026-q{index}-map.json").read_bytes())
        assert source.documents[0].mapping_sha256 == hashlib.sha256(mapping.model_dump_json().encode()).hexdigest()
        assert all(f":{f.period.start}:{f.period.end}:{f.period.basis}:" in f.fact_id for f in source.facts)
    same_end_revenue = [f for f in current.facts if f.metric == "revenue" and f.period.end == date(2026, 5, 31)]
    assert len({f.fact_id for f in same_end_revenue}) == 2
    assert {f.period.basis: f.amount for f in same_end_revenue} == {
        "discrete_quarter": Decimal("253465000"),
        "year_to_date": Decimal("501264000"),
    }


def test_hand_worked_q2_bridge_keeps_calculation_lineage_separate_from_reported_rows():
    data = bundle()
    quarter = derive_quarters(data)["quarters"][-1]
    assert quarter["status"] == "matched"
    assert all(c["status"] == "matched" for c in quarter["checks"])
    assert quarter["components"]["operating_cash_flow"]["value"] == Decimal("78837000")  # 177.463m - 98.626m
    assert quarter["components"]["ppe_purchases"]["value"] == Decimal("-1864000")  # -4.569m - (-2.705m)
    assert quarter["components"]["ppe_depreciation"]["value"] == Decimal("1762000")
    assert quarter["components"]["intangible_amortization"]["value"] == Decimal("35105000")
    assert quarter["measures"]["ebitda"]["value"] == Decimal("81618000")
    assert quarter["measures"]["operating_income_before_da"]["value"] == Decimal("82069000")
    assert quarter["measures"]["cfo_less_ppe"]["value"] == Decimal("76973000")
    assert len(quarter["components"]["operating_cash_flow"]["evidence_ids"]) == 2
    assert not any(
        f.metric == "operating_cash_flow" and f.period.basis == "discrete_quarter" and f.period.end == date(2026, 5, 31)
        for f in data.facts
    )


def test_amortization_definition_difference_blocks_earnings_not_independent_cash():
    previous = derive_quarters(bundle())["quarters"][0]
    assert previous["amortization_difference"] == 351000
    assert previous["measures"]["ebitda"]["value"] is None
    assert previous["measures"]["cfo_less_ppe"]["value"] == Decimal("29501000")
    annual = analyze_facts(bundle())["periods"][0]
    assert annual["derived"]["ebitda"]["value"] is None
    assert annual["derived"]["cfo_less_ppe"]["value"] is not None


@pytest.mark.parametrize(
    "mutation",
    ["income_revision", "missing_prior", "missing_cash", "currency", "cash_direction", "source_income_error"],
)
def test_incompatible_or_missing_inputs_do_not_become_an_unqualified_quarter(mutation):
    raw = bundle().model_dump(mode="json")
    if mutation == "missing_prior":
        raw["facts"] = [f for f in raw["facts"] if f["period"]["end"] != "2026-02-28"]
    elif mutation == "missing_cash":
        raw["facts"] = [
            f for f in raw["facts"] if not (f["metric"] == "operating_cash_flow" and f["period"]["end"] == "2026-02-28")
        ]
    else:
        for fact in raw["facts"]:
            if fact["period"]["end"] == "2026-05-31" and fact["period"]["basis"] == "year_to_date":
                if mutation == "income_revision" and fact["metric"] == "revenue":
                    fact["reported_amount"] = str(Decimal(fact["reported_amount"]) + 100)
                elif mutation == "currency":
                    fact["currency"] = "EUR"
                elif mutation == "cash_direction" and fact["metric"] == "ppe_purchases":
                    fact["reported_amount"] = "-1000"  # Still a reported outflow, but smaller than Q1: review required.
                elif mutation == "source_income_error" and fact["metric"] == "cash_flow_net_income":
                    fact["reported_amount"] = str(Decimal(fact["reported_amount"]) + 100)
    if mutation == "currency":
        with pytest.raises(ValueError, match="currencies"):
            derive_quarters(FactBundle.model_validate(raw))
    else:
        quarter = derive_quarters(FactBundle.model_validate(raw))["quarters"][-1]
        assert quarter.get("measures", {}).get("cfo_less_ppe", {}).get("value") is None


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_source", "future_event", "future_filing"])
def test_context_respects_registered_sources_and_cutoff(mutation):
    raw = bundle().model_dump(mode="json")
    if mutation == "duplicate":
        raw["events"].append(raw["events"][0])
    elif mutation == "unknown_source":
        raw["events"][0]["document_id"] = "unregistered"
    elif mutation == "future_event":
        raw["events"][0]["occurred_on"] = "2026-09-30"
    else:
        raw["information_cutoff"] = "2026-09-21"
    with pytest.raises(ValueError):
        FactBundle.model_validate(raw)


def test_public_export_includes_context_period_basis_and_calculated_quarter(tmp_path):
    output = build_public_report(DATA / "financial-facts.json", tmp_path / "baseline")
    html = output.read_text(encoding="utf-8")
    assert "Domo business acquisition completed" in html
    assert "discrete quarter" in html and "year to date" in html
    assert "81.618" in html and "76.973" in html
    assert "not the current consolidated business" in html
    assert "Quarter derivation and comparability" in html
