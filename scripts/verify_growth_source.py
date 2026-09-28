"""Verify the public growth exhibit against its exact local issuer PDF and reviewed map."""

from __future__ import annotations

import argparse
from pathlib import Path

from pe_value_os.diligence.filing_pdf import FilingMap, extract_filing
from pe_value_os.diligence.growth import GrowthContext, analyze_growth, verify_disclosure_source
from pe_value_os.diligence.models import FactBundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--facts", type=Path, default=Path("data/public/progress/financial-facts.json"))
    parser.add_argument("--context", type=Path, default=Path("data/public/progress/growth-context.json"))
    parser.add_argument("--mapping", type=Path, default=Path("data/public/progress/revenue-mix-map.json"))
    args = parser.parse_args()
    context = GrowthContext.model_validate_json(args.context.read_bytes())
    mapping = FilingMap.model_validate_json(args.mapping.read_bytes())
    original = context.revenue_mix
    extracted = extract_filing(args.pdf, mapping, original.documents[0].retrieved_at, original.information_cutoff)
    if extracted != original:
        raise ValueError("re-extracted revenue mix differs from the reviewed context")
    verify_disclosure_source(args.pdf, context)
    analyze_growth(FactBundle.model_validate_json(args.facts.read_bytes()), context)
    print(f"Verified {len(extracted.facts)} mix facts and {len(context.disclosures)} reviewed disclosure anchors.")
    print("Anchors locate reviewed prose; they do not replace review of numeric interpretation or research judgments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
