#!/usr/bin/env bash
# Repeatable offline infrastructure checks. Needs Docker; no cloud credentials.
set -euo pipefail
cd "$(dirname "$0")/../.."
terraform_image='hashicorp/terraform:1.16.4@sha256:985cdc6c1d9b0a65b83377f666efd2f740b47f02ac55be1ced3d18f7d3b0e829'
actionlint_image='rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667'
shellcheck_image='koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d'
docker run --rm -v "$PWD:/work" -w /work "$actionlint_image" -color
docker run --rm -v "$PWD:/work" -w /work "$shellcheck_image" infra/scripts/*.sh
docker compose config --quiet
docker compose --profile observability config --quiet
docker run --rm -v "$PWD:/work" -w /work "$terraform_image" fmt -check -recursive infra/terraform
for root in infra/terraform/envs/staging infra/terraform/envs/production infra/terraform/modules/pvc; do
  docker run --rm -v "$PWD:/work" -w /work "$terraform_image" -chdir="$root" init -backend=false -input=false
  docker run --rm -v "$PWD:/work" -w /work "$terraform_image" -chdir="$root" validate
done
docker run --rm -v "$PWD:/work" -w /work "$terraform_image" -chdir=infra/terraform/modules/pvc test
docker run --rm --entrypoint promtool -v "$PWD/ops/observability:/etc/prometheus:ro" \
  prom/prometheus:v3.15.0 check rules /etc/prometheus/prometheus-alerts.yaml
