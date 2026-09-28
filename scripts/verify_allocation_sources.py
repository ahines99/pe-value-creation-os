"""Verify both registered allocation snapshots against downloaded issuer PDFs, offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

from pe_value_os.diligence.vintages import AllocationHistory, AllocationVintage


def mapping(vintage: AllocationVintage) -> dict:
    return {
        "pdf_page": vintage.pdf_page,
        "printed_page": vintage.printed_page,
        "table_heading": vintage.table_heading,
        "unit_scale": vintage.unit_scale,
        "rows": [{"metric": r.metric, "label": r.label} for r in vintage.rows],
    }


def verify(vintage: AllocationVintage, pdf: Path) -> None:
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != vintage.document.sha256:
        raise ValueError("PDF bytes differ from the registered source")
    mapping_sha256 = hashlib.sha256(
        json.dumps(mapping(vintage), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if mapping_sha256 != vintage.document.mapping_sha256:
        raise ValueError("allocation mapping fingerprint mismatch")
    reader = PdfReader(pdf)
    cover = reader.pages[0].extract_text()
    if "PROGRESS SOFTWARE CORPORATION" not in cover:
        raise ValueError("issuer identity missing from cover")
    text = reader.pages[vintage.pdf_page - 1].extract_text(extraction_mode="layout")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    normalized = "\n".join(lines)
    if vintage.table_heading not in normalized or "(in thousands)" not in normalized:
        raise ValueError("allocation heading or units differ from mapping")
    for row in vintage.rows:
        matches = [line for line in lines if line.startswith(row.label + " ")]
        if len(matches) != 1 or matches[0] != row.source_row:
            raise ValueError("allocation source row differs from the registered extraction")
        raw = matches[0][len(row.label) :].replace("$", "").strip()
        if row.metric in ("technology", "trade_name", "customer_relationships"):
            if not raw.endswith("7 years"):
                raise ValueError("intangible useful-life column changed")
            raw = raw.removesuffix("7 years").strip()
        if not re.fullmatch(r"\(?[0-9,]+\)?", raw):
            raise ValueError("unexpected allocation numeric cell")
        amount = Decimal(raw.replace(",", "").replace("(", "-").replace(")", ""))
        if amount != row.reported_amount:
            raise ValueError("allocation amount differs from the PDF")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/public/progress/sharefile-allocation-history.json"))
    parser.add_argument("--original-pdf", type=Path, required=True)
    parser.add_argument("--revised-pdf", type=Path, required=True)
    args = parser.parse_args()
    history = AllocationHistory.model_validate_json(args.input.read_bytes())
    for vintage, path in zip(history.vintages, (args.original_pdf, args.revised_pdf), strict=True):
        verify(vintage, path)
    print("Verified 18 allocation facts against two SHA-256-bound issuer PDFs.")
