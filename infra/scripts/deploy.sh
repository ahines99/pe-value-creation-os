#!/usr/bin/env bash
# Release helper for ECS (PVC-133). Used by .github/workflows/cd.yml and for manual operations.
#
#   deploy.sh push <local-image>          push a locally loaded image to ECR (idempotent) and print its
#                                         digest-pinned URI
#   deploy.sh run-task <workload> <image> run a one-off task (migrate | bootstrap) with <image>, wait for it,
#                                         print its log and fail unless it exits 0
#   deploy.sh deploy <image>              run migrations, then roll mcp, api and worker to <image> and wait
#                                         until every service is stable on the new revision
#   deploy.sh rollback <service> <task-definition-arn>
#                                         point one service back at an earlier revision and wait
#
# Environment (the GitHub environment variables printed by `terraform output github_environment_variables`):
#   AWS_REGION, ECS_CLUSTER, TASK_FAMILY_PREFIX (e.g. "pvc-staging-"), ECR_REPOSITORY_URL (push only)
# Requires: aws CLI v2, jq, docker (push only).
set -euo pipefail

SERVICES=(mcp api worker)

die() { echo "error: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }

require_env() {
  local v
  for v in "$@"; do
    [[ -n "${!v:-}" ]] || die "environment variable $v is not set"
  done
}

# Register a new revision of <family> identical to the latest one except for the app container image.
# Terraform owns everything else in the task definition, so config changes applied there ride along.
register_revision() {
  local family="$1" image="$2" tmp
  tmp="$(mktemp)"
  aws ecs describe-task-definition --task-definition "$family" --query taskDefinition --output json \
    | jq --arg img "$image" '
        .containerDefinitions |= map(if .name == "app" then .image = $img else . end)
        | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities,
              .registeredAt, .registeredBy, .deregisteredAt)' >"$tmp"
  aws ecs register-task-definition --cli-input-json "file://$tmp" \
    --query taskDefinition.taskDefinitionArn --output text
  rm -f "$tmp"
}

cmd_push() {
  local local_image="${1:?usage: deploy.sh push <local-image>}" tag digest
  require_env ECR_REPOSITORY_URL
  tag="${GITHUB_SHA:-$(docker image inspect --format '{{.Id}}' "$local_image" | cut -c8-19)}"
  if digest="$(aws ecr describe-images --repository-name "${ECR_REPOSITORY_URL#*/}" \
      --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text 2>/dev/null)"; then
    log "image tag $tag already in ECR ($digest); not pushing again (tags are immutable)"
  else
    docker tag "$local_image" "$ECR_REPOSITORY_URL:$tag"
    docker push "$ECR_REPOSITORY_URL:$tag" >&2
    digest="$(aws ecr describe-images --repository-name "${ECR_REPOSITORY_URL#*/}" \
      --image-ids "imageTag=$tag" --query 'imageDetails[0].imageDigest' --output text)"
  fi
  echo "$ECR_REPOSITORY_URL@$digest"
}

cmd_run_task() {
  local workload="${1:?usage: deploy.sh run-task <workload> <image>}" image="${2:?image required}"
  local td subnets sg task_arn task_id exit_code reason prefix started_by
  require_env ECS_CLUSTER TASK_FAMILY_PREFIX
  prefix="${TASK_FAMILY_PREFIX%-}"

  td="$(register_revision "${TASK_FAMILY_PREFIX}${workload}" "$image")"
  log "running $workload ($td)"

  # Same private subnets as the services; the workload's own security group.
  subnets="$(aws ecs describe-services --cluster "$ECS_CLUSTER" --services api \
    --query 'services[0].networkConfiguration.awsvpcConfiguration.subnets' --output text | tr -s '[:space:]' ',')"
  subnets="${subnets%,}"
  sg="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${TASK_FAMILY_PREFIX}${workload}" \
    --query 'SecurityGroups[0].GroupId' --output text)"
  [[ -n "$subnets" && "$sg" == sg-* ]] || die "could not resolve network configuration for $workload"

  started_by="$(printf 'cd-%.12s' "${GITHUB_SHA:-manual}")"
  task_arn="$(aws ecs run-task --cluster "$ECS_CLUSTER" --launch-type FARGATE --task-definition "$td" \
    --started-by "$started_by" \
    --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$sg],assignPublicIp=DISABLED}" \
    --query 'tasks[0].taskArn' --output text)"
  [[ "$task_arn" == arn:* ]] || die "run-task did not start a task"
  task_id="${task_arn##*/}"

  aws ecs wait tasks-stopped --cluster "$ECS_CLUSTER" --tasks "$task_arn"

  aws logs get-log-events --log-group-name "/ecs/${prefix}/${workload}" \
    --log-stream-name "${workload}/app/${task_id}" --start-from-head \
    --query 'events[].message' --output text 2>/dev/null | tr '\t' '\n' >&2 || true

  # shellcheck disable=SC2016 # backticks are JMESPath literals, not shell expansions
  exit_code="$(aws ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks "$task_arn" \
    --query 'tasks[0].containers[?name==`app`].exitCode | [0]' --output text)"
  reason="$(aws ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks "$task_arn" \
    --query 'tasks[0].stoppedReason' --output text)"
  [[ "$exit_code" == "0" ]] || die "$workload task $task_id failed (exit code $exit_code, $reason)"
  log "$workload succeeded"
}

wait_for_services() {
  local -n expected_ref="$1"
  local s state td
  log "waiting for ${SERVICES[*]} to become stable"
  aws ecs wait services-stable --cluster "$ECS_CLUSTER" --services "${SERVICES[@]}"
  # A circuit-breaker rollback also ends "stable", so confirm the new revision actually won.
  for s in "${!expected_ref[@]}"; do
    # shellcheck disable=SC2016 # backticks are JMESPath literals, not shell expansions
    read -r td state < <(aws ecs describe-services --cluster "$ECS_CLUSTER" --services "$s" \
      --query 'services[0].deployments[?status==`PRIMARY`] | [0].[taskDefinition, rolloutState]' --output text)
    [[ "$td" == "${expected_ref[$s]}" && "$state" == "COMPLETED" ]] \
      || die "service $s is on $td ($state), expected ${expected_ref[$s]}; the deployment was rolled back"
  done
}

cmd_deploy() {
  local image="${1:?usage: deploy.sh deploy <image>}" s
  declare -A new_td=()
  require_env ECS_CLUSTER TASK_FAMILY_PREFIX

  # Migrations first: they must be backward compatible with the running release (expand, then contract).
  cmd_run_task migrate "$image"

  for s in "${SERVICES[@]}"; do
    new_td[$s]="$(register_revision "${TASK_FAMILY_PREFIX}${s}" "$image")"
    log "updating $s -> ${new_td[$s]}"
    aws ecs update-service --cluster "$ECS_CLUSTER" --service "$s" --task-definition "${new_td[$s]}" \
      --query 'service.serviceName' --output text >/dev/null
  done
  wait_for_services new_td
  log "deployed $image"
}

cmd_rollback() {
  local service="${1:?usage: deploy.sh rollback <service> <task-definition-arn>}" td="${2:?task definition required}"
  declare -A target=()
  require_env ECS_CLUSTER
  # shellcheck disable=SC2034 # read through the nameref in wait_for_services
  target[$service]="$td"
  aws ecs update-service --cluster "$ECS_CLUSTER" --service "$service" --task-definition "$td" \
    --query 'service.serviceName' --output text >/dev/null
  SERVICES=("$service")
  wait_for_services target
  log "$service rolled back to $td"
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    push) cmd_push "$@" ;;
    run-task) cmd_run_task "$@" ;;
    deploy) cmd_deploy "$@" ;;
    rollback) cmd_rollback "$@" ;;
    *) die "usage: deploy.sh push|run-task|deploy|rollback ... (see header)" ;;
  esac
}

main "$@"
