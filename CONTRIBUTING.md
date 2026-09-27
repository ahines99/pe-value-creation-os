# Contributing

Use Python 3.12+ and uv. Install with `uv sync --frozen --extra dev`, set `PVC_ENV=dev`, then run:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
uv run pvc eval --suite all --gate
uv run python -m pe_value_os.skills_lint
```

Set `PVC_TEST_DATABASE_URL` to an isolated PostgreSQL 18 database whose test account can create databases to include database/RLS/migration tests. Never use a customer database. Infrastructure changes also require `bash infra/scripts/check-infrastructure.sh` with Docker available. See [the showcase guide](docs/portfolio/quickstart.md) for the end-to-end local setup.

Keep financial arithmetic in deterministic, versioned calculators. Cite immutable evidence for value claims. Preserve company isolation and the independent human approval boundary. Add behavioral regression coverage for correctness or security changes; keep schemas, snapshots and skills consistent when interfaces change.

Open a focused pull request describing the concrete behavior change and validation. Do not commit credentials, customer data, generated local state or paid-provider responses. Contributions are submitted under Apache-2.0, as described in LICENSE. This is a portfolio project maintained on a best-effort basis; no support response time or production SLA is offered.
