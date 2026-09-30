"""Capture only fictional private-review fixtures under var/, never public docs."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ["PVC_ENV"] = "dev"
    from pytest import MonkeyPatch
    from tests.test_private_attribution import complete, finance_review, save
    from tests.test_private_observations import clock as measurement_clock
    from tests.test_private_records import COMPANY, ENV, FINANCE, revoke

    from pe_value_os import security
    from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
    from pe_value_os.adapters.repositories import InMemoryRepository
    from pe_value_os.api import private_review_views as views
    from pe_value_os.diligence import private_attribution, private_execution, private_review

    output = Path(sys.argv[1]).resolve()
    if not output.is_relative_to(ROOT / "var"):
        raise ValueError("private fixture captures must remain under the ignored var directory")
    output.mkdir(parents=True, exist_ok=True)
    with MonkeyPatch.context() as monkeypatch:
        measured = measurement_clock.__wrapped__(monkeypatch)

        class Clock(datetime):
            @classmethod
            def now(cls, zone):
                return measured.value

        for module in (private_attribution, private_execution, private_review):
            monkeypatch.setattr(module, "datetime", Clock)
        repo = InMemoryRepository(FileSystemEvidenceStore(output / "fixture-evidence"))
        case = complete(repo, measured)
        proposal = save(repo, case)

        def capture(name: str) -> None:
            with security.principal_scope(FINANCE):
                packet = repo.private_attribution_review_packet(COMPANY, proposal.revision_id, ENV)
            assert packet["origin"] == "synthetic_test_fixture"
            html = views.review_page(packet, "fictional-csrf-not-a-credential", "fictional-review-key")
            (output / f"{name}.html").write_text(html, encoding="utf-8")

        capture("pending")
        finance_review(repo, proposal)
        capture("accepted")
        with security.principal_scope(FINANCE):
            cards = repo.private_review_index(COMPANY)
        (output / "index.html").write_text(views.index_page(cards), encoding="utf-8")
        revoke(repo, case.grant)
        capture("revoked")
    print("PASS: four fictional private-review captures; no company data or public export")


if __name__ == "__main__":
    main()
