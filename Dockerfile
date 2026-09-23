# syntax=docker/dockerfile:1.7
# PE Value Creation OS container image (PVC-130).
#
# One image runs every process; the command selects the role:
#   MCP server     uvicorn pe_value_os.mcp_server:app --host 0.0.0.0 --port 8000   (default CMD)
#   approval API   uvicorn pe_value_os.api.app:app --host 0.0.0.0 --port 8080
#   worker         pvc worker
#   migrations     pvc db upgrade            (one-off task, PVC_MIGRATION_DATABASE_URL)
#   role bootstrap python /app/ops/bootstrap_db.py   (one-off task, PVC_ADMIN_DATABASE_URL)
#
# Build: docker build -t pvc .

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.12.18

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---- build stage: resolve and install runtime dependencies from uv.lock ----------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie AS build

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /src

# Dependencies first (cached until pyproject.toml or uv.lock changes). Runtime extras only; no dev tools.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --extra server --no-dev --no-install-project

# Then the project itself, installed non-editable so the runtime image needs no source tree.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra server --no-dev --no-editable

# ---- runtime stage ----------------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

LABEL org.opencontainers.image.title="pe-value-creation-os" \
      org.opencontainers.image.description="PE Value Creation OS: MCP server, approval API, worker" \
      org.opencontainers.image.licenses="Proprietary"

# Pick up OS security fixes published after the base image was built; no extra packages are installed.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 pvc \
    && useradd --system --uid 10001 --gid pvc --home-dir /app --no-create-home --shell /usr/sbin/nologin pvc

WORKDIR /app

# Application code and dependencies are owned by root and read-only for the service user.
COPY --from=build /app/.venv /app/.venv
COPY infra/docker/healthcheck.py infra/docker/bootstrap_db.py /app/ops/
# Synthetic fixture companies for PVC_SOURCE_ADAPTER=fixtures (dev, demo, staging smoke runs). No real data.
COPY tests/fixtures/companies /app/fixtures/companies

# Amazon RDS CA bundle so libpq can use sslmode=verify-full (server certificate and hostname checked).
# Pinned by checksum; when AWS rotates the bundle, update RDS_CA_SHA256 (docs/deployment.md).
ARG RDS_CA_SHA256=sha256:e5bb2084ccf45087bda1c9bffdea0eb15ee67f0b91646106e466714f9de3c7e3
ADD --checksum=${RDS_CA_SHA256} --chmod=0444 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    /app/certs/rds-global-bundle.pem

# Writable state (filesystem evidence store and notification outbox in dev; S3 is used when
# PVC_EVIDENCE_BUCKET is set). Named volumes mounted here inherit this ownership.
RUN mkdir -p /app/var/evidence /app/var/outbox && chown -R pvc:pvc /app/var

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PVC_FIXTURE_ROOT=/app/fixtures/companies \
    PVC_EVIDENCE_DIR=/app/var/evidence \
    PVC_OUTBOX_DIR=/app/var/outbox

USER 10001:10001

EXPOSE 8000 8080

# Detects the role from the container command: API -> GET /healthz == 200; MCP -> HTTP answers below 500
# (401 when auth is on); worker and one-off tasks -> no HTTP check. Override with PVC_HEALTHCHECK_URL.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/app/ops/healthcheck.py"]

CMD ["uvicorn", "pe_value_os.mcp_server:app", "--host", "0.0.0.0", "--port", "8000"]
