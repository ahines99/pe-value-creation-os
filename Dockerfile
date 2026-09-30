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

# Base images are pinned by digest (multi-arch index) so a rebuild cannot silently pick up a different image.
# Dependabot (.github/dependabot.yml) proposes digest updates; the runtime stage also applies OS security updates.
FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv

# ---- build stage: resolve and install runtime dependencies from uv.lock ----------------------------------
FROM python:3.12-alpine3.24@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111 AS build

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
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src
COPY tests/fixtures/companies ./tests/fixtures/companies
COPY evals ./evals
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra server --no-dev --no-editable

# ---- runtime stage ----------------------------------------------------------------------------------------
FROM python:3.12-alpine3.24@sha256:4c47124a8391cb7a9f571164147d154777cf012a4ece5f86097130d7a4478111 AS runtime

LABEL org.opencontainers.image.title="pe-value-creation-os" \
      org.opencontainers.image.description="PE Value Creation OS: MCP server, approval API, worker" \
      org.opencontainers.image.licenses="Apache-2.0"

# Pick up OS security fixes published after the base image was built; no extra packages are installed.
RUN apk upgrade --no-cache \
    && addgroup -S -g 10001 pvc \
    && adduser -S -D -H -u 10001 -G pvc -h /app -s /sbin/nologin pvc

WORKDIR /app

# Application code and dependencies are owned by root and read-only for the service user.
COPY --from=build /app/.venv /app/.venv
COPY infra/docker/healthcheck.py infra/docker/bootstrap_db.py /app/ops/
# Synthetic fixtures and eval cases are installed with the package; no source checkout is needed.

# Amazon RDS CA bundle so libpq can use sslmode=verify-full (server certificate and hostname checked).
# Pinned by checksum; when AWS rotates the bundle, update RDS_CA_SHA256 (docs/deployment.md).
# Refreshed from the AWS endpoint after verifying 111 CA roots and their self-signatures/validity.
ARG RDS_CA_SHA256=sha256:fe45bbebf92ad3e27a583bbb2ddd1553c521ed4d49af5514dc0a40372ea5395c
ADD --checksum=${RDS_CA_SHA256} --chmod=0444 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    /app/certs/rds-global-bundle.pem

# Writable state (filesystem evidence store and notification outbox in dev; S3 is used when
# PVC_EVIDENCE_BUCKET is set). Named volumes mounted here inherit this ownership.
RUN mkdir -p /app/var/evidence /app/var/outbox && chown -R pvc:pvc /app/var

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PVC_EVIDENCE_DIR=/app/var/evidence \
    PVC_OUTBOX_DIR=/app/var/outbox

USER 10001:10001

EXPOSE 8000 8080

# API/MCP dependency readiness and worker heartbeat checks; unknown processes fail closed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/app/ops/healthcheck.py"]

CMD ["uvicorn", "pe_value_os.mcp_server:app", "--host", "0.0.0.0", "--port", "8000"]
