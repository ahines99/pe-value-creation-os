"""Reproduce reviewed peer facts and locate disclosure anchors in exact issuer PDFs."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from pypdf import PdfReader

from pe_value_os.diligence.filing_pdf import FilingMap, extract_filing
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.peers import PeerContext, analyze_peers


def verify(directory: Path, mappings: Path, context: PeerContext, focal_pdf: Path) -> int:
    focal = context.focal_cash_reconciliation
    mapping = FilingMap.model_validate_json((mappings / "progress-2025-cash-net-income-map.json").read_bytes())
    extracted = extract_filing(focal_pdf, mapping, focal.documents[0].retrieved_at, focal.information_cutoff)
    standalone = FactBundle.model_validate_json((mappings / "progress-2025-cash-net-income-facts.json").read_bytes())
    if extracted != focal or extracted != standalone:
        raise ValueError("focal cash reconciliation differs from reviewed source bundle")
    count = len(extracted.facts)
    for candidate in context.candidates:
        if candidate.facts is None:
            continue
        bundle = candidate.facts
        pdf = directory / f"{candidate.candidate_id}.pdf"
        mapping = FilingMap.model_validate_json((mappings / f"{candidate.candidate_id}-map.json").read_bytes())
        extracted = extract_filing(pdf, mapping, bundle.documents[0].retrieved_at, bundle.information_cutoff)
        standalone = FactBundle.model_validate_json((mappings / f"{candidate.candidate_id}-facts.json").read_bytes())
        if extracted != bundle or extracted != standalone:
            raise ValueError("re-extracted peer facts differ from reviewed source bundle")
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != bundle.documents[0].sha256:
            raise ValueError("peer PDF differs from reviewed source bytes")
        reader = PdfReader(pdf)
        for note in candidate.disclosures:
            if note.pdf_page > len(reader.pages) or " ".join(note.source_anchor.split()) not in " ".join(
                reader.pages[note.pdf_page - 1].extract_text().split()
            ):
                raise ValueError(f"disclosure source anchor missing: {note.evidence_id}")
        count += len(extracted.facts)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-directory", type=Path, required=True)
    parser.add_argument("--focal-pdf", type=Path, required=True)
    parser.add_argument("--mappings", type=Path, default=Path("data/public/peers"))
    parser.add_argument("--context", type=Path, default=Path("data/public/progress/peer-context.json"))
    parser.add_argument("--facts", type=Path, default=Path("data/public/progress/financial-facts.json"))
    args = parser.parse_args()
    context = PeerContext.model_validate_json(args.context.read_bytes())
    count = verify(args.pdf_directory, args.mappings, context, args.focal_pdf)
    analyze_peers(FactBundle.model_validate_json(args.facts.read_bytes()), context)
    print(
        f"Verified {count} peer/context facts and reviewed disclosure anchors; source review judgments remain explicit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
