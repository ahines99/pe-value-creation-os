# Compute (PVC-131, PVC-134): one image, five ECS Fargate workloads.
#   mcp       long-running service, MCP Streamable HTTP on :8000 behind the ALB
#   api       long-running service, approval API and review UI on :8080 behind the ALB
#   worker    long-running service, no ingress; runs workflows and scheduled jobs (PVC-134)
#   migrate   one-off task: `pvc db upgrade` as pvc_migrator (run by CD before every deploy)
#   bootstrap one-off task: creates roles and sets their passwords as the RDS master user (first install,
#             and after a role password rotation)
#
# Plain settings are task-definition environment variables; credentials come from Secrets Manager as ECS
# secrets. CD registers new task-definition revisions with the new image (infra/scripts/deploy.sh), so the
# services ignore task_definition drift; Terraform-side config changes ride along on the next deploy.

locals {
  app_environment = merge(
    {
      PVC_ENV                     = local.pvc_env
      PVC_LOG_LEVEL               = var.log_level
      DATABASE_URL                = local.db_urls.app
      PVC_EVIDENCE_BUCKET         = aws_s3_bucket.evidence.bucket
      PVC_EVIDENCE_KMS_KEY_ID     = aws_kms_key.data.arn
      PVC_AUTH_ISSUER             = var.auth_issuer
      PVC_AUTH_AUDIENCE           = coalesce(var.auth_audience, local.mcp_resource_url)
      PVC_AUTH_JWKS_URL           = var.auth_jwks_url
      PVC_MCP_RESOURCE_URL        = local.mcp_resource_url
      PVC_AUTH_REQUIRED_SCOPES    = var.auth_required_scopes
      PVC_EGRESS_ALLOWLIST        = join(",", local.app_egress_hosts)
      PVC_PROPOSER                = var.proposer
      PVC_MODEL                   = var.model
      PVC_SOURCE_ADAPTER          = var.source_adapter
      PVC_WORKER_COMPANIES        = join(",", var.worker_companies)
      PVC_PUBLIC_URL              = local.public_api_url
      OTEL_EXPORTER_OTLP_ENDPOINT = var.otel_exporter_otlp_endpoint
      PVC_POLICY_PATH             = var.policy_path
    },
    var.source_adapter_env,
  )

  app_secrets = merge(
    { PGPASSWORD = aws_secretsmanager_secret.db_role["app"].arn },
    var.proposer == "model" ? { ANTHROPIC_API_KEY = aws_secretsmanager_secret.app["anthropic-api-key"].arn } : {},
  )

  uvicorn_flags = ["--host", "0.0.0.0", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]

  workloads = {
    mcp = {
      port        = 8000
      command     = tolist(concat(["uvicorn", "pe_value_os.mcp_server:app", "--port", "8000"], local.uvicorn_flags))
      environment = tomap(local.app_environment)
      secrets     = tomap(local.app_secrets)
      evidence    = true
    }
    api = {
      port        = 8080
      command     = tolist(concat(["uvicorn", "pe_value_os.api.app:app", "--port", "8080"], local.uvicorn_flags))
      environment = tomap(local.app_environment)
      secrets     = tomap(local.app_secrets)
      evidence    = true
    }
    worker = {
      port        = null
      command     = tolist(["pvc", "worker"])
      environment = tomap(local.app_environment)
      secrets = tomap(merge(
        local.app_secrets,
        var.notify_webhook_enabled ? { PVC_NOTIFY_WEBHOOK_URL = aws_secretsmanager_secret.app["notify-webhook-url"].arn } : {},
      ))
      evidence = true
    }
    migrate = {
      port    = null
      command = tolist(["pvc", "db", "upgrade"])
      environment = tomap({
        PVC_ENV                    = local.pvc_env
        PVC_LOG_LEVEL              = var.log_level
        PVC_MIGRATION_DATABASE_URL = local.db_urls.migrator
      })
      secrets  = tomap({ PGPASSWORD = aws_secretsmanager_secret.db_role["migrator"].arn })
      evidence = false
    }
    bootstrap = {
      port    = null
      command = tolist(["python", "/app/ops/bootstrap_db.py"])
      environment = tomap({
        PVC_ENV                = local.pvc_env
        PVC_LOG_LEVEL          = var.log_level
        PVC_ADMIN_DATABASE_URL = local.db_urls.admin
      })
      secrets = tomap({
        PGPASSWORD               = "${aws_db_instance.this.master_user_secret[0].secret_arn}:password::"
        PVC_APP_DB_PASSWORD      = aws_secretsmanager_secret.db_role["app"].arn
        PVC_RO_DB_PASSWORD       = aws_secretsmanager_secret.db_role["readonly"].arn
        PVC_MIGRATOR_DB_PASSWORD = aws_secretsmanager_secret.db_role["migrator"].arn
      })
      evidence = false
    }
  }

  services           = toset(["mcp", "api", "worker"])
  services_with_port = { for k, v in local.workloads : k => v if v.port != null }
}

# ---- Application secrets (values are set out of band; see docs/deployment.md) -------------------------------
resource "aws_secretsmanager_secret" "app" {
  for_each                = toset(["anthropic-api-key", "notify-webhook-url"])
  name                    = "${local.prefix}/app/${each.key}"
  description             = "Set with: aws secretsmanager put-secret-value --secret-id ${local.prefix}/app/${each.key} --secret-string ..."
  kms_key_id              = aws_kms_key.data.arn
  recovery_window_in_days = var.deletion_protection ? 30 : 7
  tags                    = local.tags
}

# ---- Container registry -----------------------------------------------------------------------------------
resource "aws_ecr_repository" "this" {
  name                 = local.prefix
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = local.tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the 100 most recent images (rollback window)"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 100
        }
        action = { type = "expire" }
      },
    ]
  })
}

# ---- ECS --------------------------------------------------------------------------------------------------
resource "aws_ecs_cluster" "this" {
  name = local.prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.tags
}

resource "aws_ecs_task_definition" "this" {
  for_each                 = local.workloads
  family                   = "${local.prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_sizes[each.key].cpu
  memory                   = var.task_sizes[each.key].memory
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = try(aws_iam_role.task[each.key].arn, null)

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = "${aws_ecr_repository.this.repository_url}:${var.image_tag}"
      essential = true
      command   = each.value.command
      user      = "10001:10001"

      portMappings = each.value.port == null ? [] : [
        { containerPort = each.value.port, protocol = "tcp" }
      ]

      environment = [
        for k, v in each.value.environment : { name = k, value = v } if v != null && v != ""
      ]
      secrets = [
        for k, v in each.value.secrets : { name = k, valueFrom = v }
      ]

      linuxParameters = {
        initProcessEnabled = true
        capabilities       = { drop = ["ALL"] }
      }

      # Same script as the image HEALTHCHECK (ECS ignores Dockerfile health checks).
      healthCheck = {
        command     = ["CMD", "python", "/app/ops/healthcheck.py"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      # Give the worker time to checkpoint an in-flight step on deploys and scale-in.
      stopTimeout = each.key == "worker" ? 120 : 30

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.workload[each.key].name
          awslogs-region        = local.region
          awslogs-stream-prefix = each.key
        }
      }
    }
  ])

  tags = local.tags
}

resource "aws_ecs_service" "this" {
  for_each                           = local.services
  name                               = each.key
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.this[each.key].arn
  desired_count                      = var.desired_counts[each.key]
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  propagate_tags                     = "SERVICE"
  enable_execute_command             = false
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = contains(keys(local.services_with_port), each.key) ? 60 : null

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.app[*].id
    security_groups  = [aws_security_group.workload[each.key].id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = contains(keys(local.services_with_port), each.key) ? [local.services_with_port[each.key].port] : []
    content {
      target_group_arn = aws_lb_target_group.this[each.key].arn
      container_name   = "app"
      container_port   = load_balancer.value
    }
  }

  tags = local.tags

  lifecycle {
    # CD owns the running revision (infra/scripts/deploy.sh).
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.https]
}
