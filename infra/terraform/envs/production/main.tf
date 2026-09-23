# Production (PVC-136). Same module as staging, separate AWS account, state and credentials.
# Deployed by CD only after a reviewer approves the GitHub `production` environment.
#
#   terraform init -backend-config=backend.hcl      # copy backend.hcl.example
#   terraform apply                                 # copy terraform.tfvars.example to terraform.tfvars

terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.7, < 4.0"
    }
  }

  # Partial configuration: bucket, key, region (and optionally kms_key_id) come from backend.hcl.
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  # Refuse to run against any other account: staging and production credentials never mix.
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      System      = "pvc"
      Environment = "production"
      ManagedBy   = "terraform"
      Repository  = var.github_repository
    }
  }
}

module "pvc" {
  source = "../../modules/pvc"

  environment = "production"
  vpc_cidr    = var.vpc_cidr
  az_count    = 3

  # Egress allow-list (PVC-094)
  data_source_hosts    = var.data_source_hosts
  notify_webhook_host  = var.notify_webhook_host
  extra_egress_domains = var.extra_egress_domains

  # Identity provider
  auth_issuer          = var.auth_issuer
  auth_jwks_url        = var.auth_jwks_url
  auth_audience        = var.auth_audience
  auth_required_scopes = var.auth_required_scopes
  api_audience         = var.api_audience
  api_client_ids       = var.api_client_ids
  api_browser_oidc     = var.api_browser_oidc

  # Ingress
  mcp_hostname             = var.mcp_hostname
  api_hostname             = var.api_hostname
  acm_certificate_arn      = var.acm_certificate_arn
  ingress_cidrs            = var.ingress_cidrs
  waf_rate_limit           = var.waf_rate_limit
  max_request_body_bytes   = var.max_request_body_bytes
  model_provider_host      = var.model_provider_host
  db_role_password_version = var.db_role_password_version

  # Database: Multi-AZ standby, maximum PITR window, deletion protection on the database, ALB, firewall
  # and secrets.
  db_instance_class        = var.db_instance_class
  db_allocated_storage     = 100
  db_max_allocated_storage = 1000
  db_multi_az              = true
  db_backup_retention_days = 35
  deletion_protection      = true

  # Evidence
  evidence_retention_days = var.evidence_retention_days

  # Compute and application
  image_tag                   = var.image_tag
  desired_counts              = var.desired_counts
  proposer                    = var.proposer
  model                       = var.model
  source_adapter              = var.source_adapter
  source_adapter_env          = var.source_adapter_env
  worker_companies            = var.worker_companies
  notify_webhook_enabled      = var.notify_webhook_enabled
  otel_exporter_otlp_endpoint = var.otel_exporter_otlp_endpoint

  # Observability
  log_retention_days = 365
  alarm_topic_arn    = var.alarm_topic_arn

  # CD
  github_repository           = var.github_repository
  github_environment          = "production"
  create_github_oidc_provider = var.create_github_oidc_provider
  github_oidc_provider_arn    = var.github_oidc_provider_arn
}
