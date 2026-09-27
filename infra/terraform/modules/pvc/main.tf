# PE Value Creation OS - one environment (staging or production) in one AWS account.
# Files: network.tf (VPC, NAT, Network Firewall egress allow-list), database.tf (RDS PostgreSQL, role secrets),
# storage.tf (evidence bucket), compute.tf (ECR, ECS Fargate), ingress.tf (ALB, TLS, WAF), iam.tf (task and
# deploy roles), observability.tf (logs, alarms).

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  prefix     = "${var.name}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.region

  # Value of PVC_ENV inside the containers. Auth is mandatory for both.
  pvc_env = var.environment == "production" ? "prod" : "staging"

  mcp_resource_url = "https://${var.mcp_hostname}/mcp"
  public_api_url   = "https://${var.api_hostname}"
  api_audience     = coalesce(var.api_audience, local.public_api_url)

  # ---- Egress allow-list (PVC-094): single source for Network Firewall and the in-process check ----------
  idp_hosts = distinct([
    regex("^https://([^/:]+)", var.auth_issuer)[0],
    regex("^https://([^/:]+)", var.auth_jwks_url)[0],
  ])
  telemetry_hosts = compact([try(regex("^https?://([^/:]+)", var.otel_exporter_otlp_endpoint)[0], "")])
  egress_domains = distinct(compact(concat(
    [var.model_provider_host],
    local.idp_hosts,
    local.telemetry_hosts,
    var.data_source_hosts,
    var.notify_webhook_host == null ? [] : [var.notify_webhook_host],
    var.extra_egress_domains,
  )))
  # Network Firewall writes subdomain wildcards as ".example.com"; the application uses "*.example.com".
  app_egress_hosts = [for d in local.egress_domains : startswith(d, ".") ? "*${d}" : d]

  tags = merge(var.tags, {
    System      = var.name
    Environment = var.environment
  })
}

# ---- Encryption keys --------------------------------------------------------------------------------------
# data: RDS storage and Performance Insights, the evidence bucket, and Secrets Manager secrets.
resource "aws_kms_key" "data" {
  description             = "${local.prefix} data at rest (RDS, evidence bucket, secrets)"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms_data.json
  tags                    = local.tags
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}

data "aws_iam_policy_document" "kms_data" {
  statement {
    sid       = "AccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }
}

# logs: CloudWatch Logs groups (application, firewall, WAF, database).
resource "aws_kms_key" "logs" {
  description             = "${local.prefix} CloudWatch Logs"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms_logs.json
  tags                    = local.tags
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${local.prefix}-logs"
  target_key_id = aws_kms_key.logs.key_id
}

data "aws_iam_policy_document" "kms_logs" {
  statement {
    sid       = "AccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${local.partition}:iam::${local.account_id}:root"]
    }
  }

  statement {
    sid = "CloudWatchLogs"
    actions = [
      "kms:Encrypt*",
      "kms:Decrypt*",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:Describe*",
    ]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${local.region}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:*"]
    }
  }
}
