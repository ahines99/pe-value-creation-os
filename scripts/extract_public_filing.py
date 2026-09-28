"""Create a public fact bundle from a reviewed local issuer PDF and table mapping.

No vendor credentials or network calls. Download the exact primary-source document
named in the mapping first. The extractor validates its bytes before reading rows.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from pe_value_os.diligence.filing_pdf import FilingMap, extract_filing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--retrieved-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.pdf.resolve(), args.mapping.resolve()}:
        parser.error("output must not overwrite a source")
    mapping = FilingMap.model_validate_json(args.mapping.read_bytes())
    bundle = extract_filing(args.pdf, mapping, args.retrieved_at, args.cutoff)
    bundle.require_public()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(bundle.facts)} public filing facts from {len(mapping.tables)} mapped tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
