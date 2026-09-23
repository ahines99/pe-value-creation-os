variable "aws_account_id" {
  description = "Staging AWS account id. The provider refuses any other account."
  type        = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_repository" {
  description = "owner/name of the repository whose staging environment may deploy."
  type        = string
}

variable "create_github_oidc_provider" {
  type    = bool
  default = true
}

variable "github_oidc_provider_arn" {
  type    = string
  default = null
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "data_source_hosts" {
  description = "Data-source hosts the application may reach (warehouse, SaaS APIs)."
  type        = list(string)
  default     = []
}

variable "notify_webhook_host" {
  type    = string
  default = null
}

variable "extra_egress_domains" {
  type    = list(string)
  default = []
}

variable "auth_issuer" {
  type = string
}

variable "auth_jwks_url" {
  type = string
}

variable "auth_audience" {
  type    = string
  default = null
}

variable "auth_required_scopes" {
  type    = string
  default = "pvc.read"
}

variable "api_audience" {
  description = "Token audience for the approval API; must differ from the MCP audience. Null uses https://<api_hostname>."
  type        = string
  default     = null
}

variable "api_client_ids" {
  description = "OAuth client ids of the approval UI, allowed to record approval decisions."
  type        = list(string)
}

variable "api_browser_oidc" {
  description = "ALB OIDC sign-in for the review UI pages (see the module variable). Null disables browser sign-in."
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

variable "mcp_hostname" {
  type = string
}

variable "api_hostname" {
  type = string
}

variable "acm_certificate_arn" {
  type = string
}

variable "ingress_cidrs" {
  description = "Staging can be restricted to the fund's VPN egress ranges."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "waf_rate_limit" {
  type    = number
  default = 1000
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "evidence_retention_days" {
  type    = number
  default = 30
}

variable "image_tag" {
  type    = string
  default = "initial"
}

variable "desired_counts" {
  type = object({
    mcp    = number
    api    = number
    worker = number
  })
  default = {
    mcp    = 1
    api    = 1
    worker = 1
  }
}

variable "proposer" {
  type    = string
  default = "rules"
}

variable "model" {
  type    = string
  default = null
}

variable "source_adapter" {
  type    = string
  default = "fixtures"
}

variable "source_adapter_env" {
  type    = map(string)
  default = {}
}

variable "worker_companies" {
  type    = list(string)
  default = []
}

variable "notify_webhook_enabled" {
  type    = bool
  default = false
}

variable "otel_exporter_otlp_endpoint" {
  type    = string
  default = ""
}

variable "alarm_topic_arn" {
  type    = string
  default = null
}

variable "model_provider_host" {
  description = "Model provider API host on the egress allow-list. Empty disables model egress (rules proposer only)."
  type        = string
  default     = "api.anthropic.com"
}

variable "max_request_body_bytes" {
  description = "WAF blocks requests declaring a Content-Length of this many bytes or more (a power of ten)."
  type        = number
  default     = 1000000
}

variable "db_role_password_version" {
  description = "Bump to rotate the pvc_app / pvc_readonly / pvc_migrator passwords, then re-run the bootstrap task."
  type        = number
  default     = 1
}
