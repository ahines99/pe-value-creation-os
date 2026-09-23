# ---- Identity ---------------------------------------------------------------------------------------------
variable "name" {
  description = "Short system name used as a prefix for every resource."
  type        = string
  default     = "pvc"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,14}$", var.name))
    error_message = "name must be 2-15 characters: lowercase letters, digits and hyphens."
  }
}

variable "environment" {
  description = "Deployment environment. Each environment lives in its own AWS account."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "tags" {
  description = "Extra tags applied to taggable resources (the provider's default_tags cover the rest)."
  type        = map(string)
  default     = {}
}

# ---- Network ----------------------------------------------------------------------------------------------
variable "vpc_cidr" {
  description = "VPC CIDR block. Must be a /16 so the /24 subnet plan fits."
  type        = string
  default     = "10.40.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && endswith(var.vpc_cidr, "/16")
    error_message = "vpc_cidr must be a valid /16 CIDR block."
  }
}

variable "az_count" {
  description = "Number of availability zones (one NAT gateway and one firewall endpoint per zone)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3 (the ALB and RDS subnet group need at least two zones)."
  }
}

# ---- Egress allow-list (PVC-094) --------------------------------------------------------------------------
variable "model_provider_host" {
  description = "Model provider API host. Empty string disables model egress (PVC_PROPOSER=rules only)."
  type        = string
  default     = "api.anthropic.com"
}

variable "data_source_hosts" {
  description = "Hosts of configured data sources (warehouse, CSV drop, SaaS APIs). A leading dot allows subdomains, e.g. \".snowflakecomputing.com\"."
  type        = list(string)
  default     = []
}

variable "notify_webhook_host" {
  description = "Host of the notification webhook (PVC_NOTIFY_WEBHOOK_URL). Null when notifications stay in the outbox."
  type        = string
  default     = null
}

variable "extra_egress_domains" {
  description = "Additional allowed egress domains. Every entry needs a documented reason (docs/deployment.md)."
  type        = list(string)
  default     = []
}

# ---- Authentication ---------------------------------------------------------------------------------------
variable "auth_issuer" {
  description = "OAuth issuer URL of the fund's identity provider (PVC_AUTH_ISSUER)."
  type        = string

  validation {
    condition     = can(regex("^https://[^/]+", var.auth_issuer))
    error_message = "auth_issuer must be an https URL."
  }
}

variable "auth_jwks_url" {
  description = "JWKS endpoint of the identity provider (PVC_AUTH_JWKS_URL)."
  type        = string

  validation {
    condition     = can(regex("^https://[^/]+", var.auth_jwks_url))
    error_message = "auth_jwks_url must be an https URL."
  }
}

variable "auth_audience" {
  description = "Expected token audience (PVC_AUTH_AUDIENCE). Null uses the MCP resource URL."
  type        = string
  default     = null
}

variable "auth_required_scopes" {
  description = "Comma-separated scopes required for MCP access (PVC_AUTH_REQUIRED_SCOPES)."
  type        = string
  default     = "pvc.read"
}

variable "api_audience" {
  description = "Token audience for the approval API (PVC_API_AUDIENCE). Must differ from the MCP audience so MCP-client tokens cannot be replayed against it. Null uses the public API URL."
  type        = string
  default     = null
}

variable "api_client_ids" {
  description = "OAuth client ids (azp) allowed to record approval decisions, i.e. the approval UI's client (PVC_API_CLIENT_IDS)."
  type        = list(string)

  validation {
    condition     = length(var.api_client_ids) > 0
    error_message = "Set at least one approval UI client id; approval decisions are disabled without it."
  }
}

variable "api_browser_oidc" {
  description = <<-EOT
    ALB OIDC authentication for the browser review UI (/runs/*/review, forms, evidence, KPI pages). The ALB signs
    the user in and forwards the identity provider's access token in x-amzn-oidc-accesstoken, which the API verifies
    like a bearer token (audience api_audience, scope pvc.approve for decisions). Null leaves the pages reachable
    only with a bearer token. client_secret is stored in Terraform state; protect the state bucket accordingly.
  EOT
  type = object({
    issuer                 = string
    authorization_endpoint = string
    token_endpoint         = string
    user_info_endpoint     = string
    client_id              = string
    client_secret          = string
    scope                  = optional(string, "openid pvc.read pvc.approve")
  })
  default   = null
  sensitive = true
}

# ---- Ingress (PVC-135) ------------------------------------------------------------------------------------
variable "mcp_hostname" {
  description = "Public DNS name of the MCP endpoint, e.g. mcp.staging.example.com. Must be covered by the ACM certificate."
  type        = string
}

variable "api_hostname" {
  description = "Public DNS name of the approval API and review UI, e.g. approvals.staging.example.com."
  type        = string
}

variable "acm_certificate_arn" {
  description = "ARN of an issued ACM certificate (same region) covering mcp_hostname and api_hostname."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:acm:", var.acm_certificate_arn))
    error_message = "acm_certificate_arn must be an ACM certificate ARN."
  }
}

variable "ingress_cidrs" {
  description = "CIDR blocks allowed to reach the load balancer on 80/443."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "alb_ssl_policy" {
  description = "TLS policy for the HTTPS listener (TLS 1.2+ with forward secrecy, TLS 1.3 preferred)."
  type        = string
  default     = "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"
}

variable "alb_idle_timeout" {
  description = "ALB idle timeout in seconds. Streamable HTTP responses can stay open while tools run."
  type        = number
  default     = 120
}

variable "waf_rate_limit" {
  description = "Maximum requests per client IP in any 5-minute window before WAF blocks the IP."
  type        = number
  default     = 1000

  validation {
    condition     = var.waf_rate_limit >= 10
    error_message = "waf_rate_limit must be at least 10 (WAF minimum)."
  }
}

variable "max_request_body_bytes" {
  description = "Requests declaring a Content-Length of this many bytes or more are blocked at the WAF. Must be a power of ten (e.g. 1000000 = 1 MB)."
  type        = number
  default     = 1000000

  validation {
    condition     = can(regex("^10+$", tostring(var.max_request_body_bytes))) && var.max_request_body_bytes >= 10000
    error_message = "max_request_body_bytes must be a power of ten, at least 10000."
  }
}

# ---- Database (PVC-132) -----------------------------------------------------------------------------------
variable "db_engine_version" {
  description = "PostgreSQL major version (RDS picks the latest minor and applies minor upgrades)."
  type        = string
  default     = "18"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "Initial storage in GiB."
  type        = number
  default     = 50
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling in GiB."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  description = "Run a synchronous standby in a second availability zone."
  type        = bool
  default     = false
}

variable "db_backup_retention_days" {
  description = "Automated backup retention in days; point-in-time recovery covers the same window."
  type        = number
  default     = 7

  validation {
    condition     = var.db_backup_retention_days >= 1 && var.db_backup_retention_days <= 35
    error_message = "db_backup_retention_days must be between 1 and 35 (0 would disable PITR)."
  }
}

variable "db_backup_window" {
  description = "Daily backup window (UTC)."
  type        = string
  default     = "03:00-04:00"
}

variable "db_maintenance_window" {
  description = "Weekly maintenance window (UTC)."
  type        = string
  default     = "sun:04:30-sun:05:30"
}

variable "db_master_username" {
  description = "RDS master user. Used only by the bootstrap task; its password is generated and rotated by RDS in Secrets Manager."
  type        = string
  default     = "pvc_admin"
}

variable "db_role_password_version" {
  description = "Bump to generate and store new passwords for pvc_app / pvc_readonly / pvc_migrator, then re-run the bootstrap task."
  type        = number
  default     = 1
}

variable "db_ca_cert_identifier" {
  description = "RDS server certificate authority."
  type        = string
  default     = "rds-ca-rsa2048-g1"
}

variable "deletion_protection" {
  description = "Protect the database, load balancer and firewall from deletion, and keep secrets recoverable for 30 days."
  type        = bool
  default     = false
}

# ---- Evidence storage -------------------------------------------------------------------------------------
variable "evidence_bucket_name" {
  description = "Evidence bucket name. Null derives <name>-<environment>-evidence-<account id>."
  type        = string
  default     = null
}

variable "evidence_retention_days" {
  description = "Default Object Lock retention (governance mode) for evidence object versions."
  type        = number
  default     = 365

  validation {
    condition     = var.evidence_retention_days >= 1
    error_message = "evidence_retention_days must be at least 1."
  }
}

# ---- Compute ----------------------------------------------------------------------------------------------
variable "image_tag" {
  description = "Image tag written into the Terraform-managed task definitions. CD registers new revisions with the commit SHA; services ignore task-definition drift."
  type        = string
  default     = "initial"
}

variable "desired_counts" {
  description = "Running task count per service. Use 0 for the first apply, before any image exists."
  type = object({
    mcp    = number
    api    = number
    worker = number
  })
  default = {
    mcp    = 2
    api    = 2
    worker = 1
  }
}

variable "task_sizes" {
  description = "Fargate CPU units and memory (MiB) per workload."
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {
    mcp       = { cpu = 512, memory = 1024 }
    api       = { cpu = 512, memory = 1024 }
    worker    = { cpu = 1024, memory = 2048 }
    migrate   = { cpu = 256, memory = 512 }
    bootstrap = { cpu = 256, memory = 512 }
    offboard  = { cpu = 256, memory = 512 }
  }
}

# ---- Application settings ---------------------------------------------------------------------------------
variable "log_level" {
  description = "PVC_LOG_LEVEL."
  type        = string
  default     = "INFO"
}

variable "proposer" {
  description = "PVC_PROPOSER: rules (deterministic) or model (requires the anthropic-api-key secret)."
  type        = string
  default     = "rules"

  validation {
    condition     = contains(["rules", "model"], var.proposer)
    error_message = "proposer must be rules or model."
  }
}

variable "model" {
  description = "PVC_MODEL. Null uses the application default."
  type        = string
  default     = null
}

variable "source_adapter" {
  description = "PVC_SOURCE_ADAPTER: fixtures | csv | warehouse | composite."
  type        = string
  default     = "fixtures"

  validation {
    condition     = contains(["fixtures", "csv", "warehouse", "composite"], var.source_adapter)
    error_message = "source_adapter must be fixtures, csv, warehouse or composite."
  }
}

variable "source_adapter_env" {
  description = "Extra plain (non-secret) environment for the source adapter, e.g. PVC_CSV_ROOT or PVC_SOURCES_CONFIG."
  type        = map(string)
  default     = {}

  # These settings belong to the module; letting an adapter override them could, for example, set PVC_ENV=dev and
  # disable authentication. Core settings are also merged last, so they win regardless.
  validation {
    condition = length(setintersection(keys(var.source_adapter_env), [
      "PVC_ENV", "DATABASE_URL", "PVC_EVIDENCE_BUCKET", "PVC_EVIDENCE_KMS_KEY_ID", "PVC_AUTH_ISSUER",
      "PVC_AUTH_AUDIENCE", "PVC_AUTH_JWKS_URL", "PVC_AUTH_PUBLIC_KEY", "PVC_MCP_RESOURCE_URL", "PVC_MCP_ALLOWED_HOSTS",
      "PVC_AUTH_REQUIRED_SCOPES", "PVC_API_AUDIENCE", "PVC_API_CLIENT_IDS", "PVC_EGRESS_ALLOWLIST", "PVC_DEV_TOKENS",
      "PVC_ALLOWED_COMPANIES", "PVC_WORKER_COMPANIES", "PVC_PROPOSER", "PVC_MODEL", "PVC_POLICY_PATH",
      "OTEL_EXPORTER_OTLP_ENDPOINT", "PGPASSWORD", "ANTHROPIC_API_KEY",
    ])) == 0
    error_message = "source_adapter_env may not set core settings such as PVC_ENV, auth, database or egress variables."
  }
}

variable "worker_companies" {
  description = "Company ids the worker may act on (PVC_WORKER_COMPANIES). Empty means none outside dev."
  type        = list(string)
  default     = []
}

variable "notify_webhook_enabled" {
  description = "Inject the notify-webhook-url secret into the worker. Set the secret value before enabling."
  type        = bool
  default     = false
}

variable "otel_exporter_otlp_endpoint" {
  description = "OTLP/HTTP collector URL (OTEL_EXPORTER_OTLP_ENDPOINT). Empty disables export; its host joins the egress allow-list."
  type        = string
  default     = ""
}

variable "policy_path" {
  description = "PVC_POLICY_PATH inside the container. Null uses the packaged policy."
  type        = string
  default     = null
}

# ---- Observability ----------------------------------------------------------------------------------------
variable "log_retention_days" {
  description = "CloudWatch Logs retention for application, firewall, WAF and database logs."
  type        = number
  default     = 90
}

variable "alarm_topic_arn" {
  description = "SNS topic for CloudWatch alarm notifications. Null creates alarms without actions."
  type        = string
  default     = null
}

# ---- CI/CD (PVC-133) --------------------------------------------------------------------------------------
variable "github_repository" {
  description = "GitHub repository allowed to deploy, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "github_environment" {
  description = "GitHub Actions environment whose jobs may assume the deploy role (the OIDC subject is repo:<repo>:environment:<name>)."
  type        = string
}

variable "create_github_oidc_provider" {
  description = "Create the account's GitHub OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "github_oidc_provider_arn" {
  description = "Existing GitHub OIDC provider ARN, used when create_github_oidc_provider is false."
  type        = string
  default     = null
}
