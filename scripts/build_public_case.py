"""Assemble reviewed public filing bundles and context without replacing source facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pe_value_os.diligence.models import ContextEvent, FactBundle, SourceDocument


def assemble(directory: Path) -> FactBundle:
    bundles = [
        FactBundle.model_validate_json((directory / name).read_bytes())
        for name in ("annual-facts.json", "fy2026-q1-facts.json", "fy2026-q2-facts.json")
    ]
    context = json.loads((directory / "context-events.json").read_bytes())
    first = bundles[0]
    if any(
        (b.company, b.entity_id, b.ticker, b.information_cutoff)
        != (first.company, first.entity_id, first.ticker, first.information_cutoff)
        for b in bundles
    ):
        raise ValueError("public case assembly requires the same entity and information cutoff")
    result = FactBundle(
        company=first.company,
        entity_id=first.entity_id,
        ticker=first.ticker,
        information_cutoff=first.information_cutoff,
        documents=(*(d for b in bundles for d in b.documents), SourceDocument.model_validate(context["document"])),
        facts=tuple(f for b in bundles for f in b.facts),
        events=(ContextEvent.model_validate(context["event"]),),
    )
    result.require_public()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/public/progress"))
    parser.add_argument("--output", type=Path, default=Path("data/public/progress/financial-facts.json"))
    args = parser.parse_args()
    if args.output.resolve() in {
        (args.directory / name).resolve()
        for name in ("annual-facts.json", "fy2026-q1-facts.json", "fy2026-q2-facts.json", "context-events.json")
    }:
        parser.error("output must not overwrite a source bundle")
    result = assemble(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Assembled {len(result.facts)} public facts and {len(result.events)} context events.")
