"""CI check: upgrade to head, downgrade to base, upgrade again (PVC-030)."""

from __future__ import annotations

import os
import sys

from .migrate import current, downgrade, upgrade


def main() -> int:
    url = os.environ.get("PVC_TEST_DATABASE_URL") or os.environ.get("PVC_MIGRATION_DATABASE_URL")
    if not url:
        print("PVC_TEST_DATABASE_URL not set", file=sys.stderr)
        return 2
    upgrade(url)
    head = current(url)
    downgrade(url)
    assert current(url) is None, "downgrade to base left a revision behind"
    upgrade(url)
    assert current(url) == head
    print(f"migrations round-trip ok (head={head})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
