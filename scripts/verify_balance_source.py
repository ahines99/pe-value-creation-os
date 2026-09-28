"""Reproduce all reviewed point-in-time facts from the exact public issuer PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from pe_value_os.diligence.balances import BalanceBundle, BalanceMap, extract_balances
from pe_value_os.diligence.models import FactBundle
from pe_value_os.diligence.valuation import ValuationSpec, analyze_valuation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args()
    root = Path("data/public/progress")
    mapping = BalanceMap.model_validate_json((root / "fy2025-balance-map.json").read_bytes())
    reviewed = BalanceBundle.model_validate_json((root / "balance-facts.json").read_bytes())
    extracted = extract_balances(args.pdf, mapping)
    if extracted != reviewed:
        raise ValueError("point-in-time facts differ from the reviewed source bundle")
    report = analyze_valuation(
        FactBundle.model_validate_json((root / "financial-facts.json").read_bytes()),
        reviewed,
        ValuationSpec.model_validate_json(Path("data/constructed/progress/historical-valuation.json").read_bytes()),
    )
    if report["blocked_by"]:
        raise ValueError("reviewed balance exhibit has unresolved source reconciliation")
    print(
        f"PASS: {len(extracted.facts)} dated source facts; {len(report['reconciliations'])} debt reconciliations matched."
    )


if __name__ == "__main__":
    main()
