# Offline tests for the pvc module: a mocked AWS provider, so no credentials or account are needed.
#   cd infra/terraform/modules/pvc && terraform init -backend=false && terraform test
# They evaluate every expression (egress allow-list, task definitions, IAM, WAF) and assert the security
# properties the tickets require. They do not prove AWS accepts the configuration; only an apply does.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "111111111111" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_kms_key" {
    defaults = { arn = "arn:aws:kms:us-east-1:111111111111:key/00000000-0000-0000-0000-000000000000" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:111111111111:secret:pvc-test-AbCdEf" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::111111111111:role/pvc-test" }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::111111111111:oidc-provider/token.actions.githubusercontent.com" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:us-east-1:111111111111:repository/pvc-staging"
      repository_url = "111111111111.dkr.ecr.us-east-1.amazonaws.com/pvc-staging"
    }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:111111111111:log-group:pvc-test" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:us-east-1:111111111111:cluster/pvc-staging" }
  }
  mock_resource "aws_lb" {
    defaults = {
      arn        = "arn:aws:elasticloadbalancing:us-east-1:111111111111:loadbalancer/app/pvc-staging/0123456789abcdef"
      arn_suffix = "app/pvc-staging/0123456789abcdef"
    }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:111111111111:listener/app/pvc-staging/0123456789abcdef/0123456789abcdef" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = {
      arn        = "arn:aws:elasticloadbalancing:us-east-1:111111111111:targetgroup/pvc-staging/0123456789abcdef"
      arn_suffix = "targetgroup/pvc-staging/0123456789abcdef"
    }
  }
  mock_resource "aws_wafv2_web_acl" {
    defaults = { arn = "arn:aws:wafv2:us-east-1:111111111111:regional/webacl/pvc-staging/00000000-0000-0000-0000-000000000000" }
  }
  mock_resource "aws_networkfirewall_rule_group" {
    defaults = { arn = "arn:aws:network-firewall:us-east-1:111111111111:stateful-rulegroup/pvc-staging-egress-allowlist" }
  }
  mock_resource "aws_networkfirewall_firewall_policy" {
    defaults = { arn = "arn:aws:network-firewall:us-east-1:111111111111:firewall-policy/pvc-staging-egress" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::pvc-staging-evidence-111111111111" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address = "pvc-staging.abc.us-east-1.rds.amazonaws.com"
      port    = 5432
      master_user_secret = [{
        secret_arn    = "arn:aws:secretsmanager:us-east-1:111111111111:secret:rds!db-1234-AbCdEf"
        kms_key_id    = "arn:aws:kms:us-east-1:111111111111:key/00000000-0000-0000-0000-000000000000"
        secret_status = "active"
      }]
    }
  }
  mock_resource "aws_networkfirewall_firewall" {
    defaults = {
      arn = "arn:aws:network-firewall:us-east-1:111111111111:firewall/pvc-staging-egress"
      firewall_status = [{
        sync_states = [
          { availability_zone = "us-east-1a", attachment = [{ endpoint_id = "vpce-0a", subnet_id = "subnet-0a" }] },
          { availability_zone = "us-east-1b", attachment = [{ endpoint_id = "vpce-0b", subnet_id = "subnet-0b" }] },
          { availability_zone = "us-east-1c", attachment = [{ endpoint_id = "vpce-0c", subnet_id = "subnet-0c" }] },
        ]
        transit_gateway_attachment_sync_states = []
      }]
    }
  }
}

variables {
  environment                 = "staging"
  auth_issuer                 = "https://login.example.com/oauth2/default"
  auth_jwks_url               = "https://keys.example.com/v1/keys"
  mcp_hostname                = "mcp.staging.example.com"
  api_hostname                = "approvals.staging.example.com"
  acm_certificate_arn         = "arn:aws:acm:us-east-1:111111111111:certificate/00000000-0000-0000-0000-000000000000"
  github_repository           = "example-org/pe-value-creation-os"
  github_environment          = "staging"
  data_source_hosts           = ["warehouse.example.com", ".snowflakecomputing.com"]
  otel_exporter_otlp_endpoint = "https://otlp.example.net:443/v1"
}

run "staging_defaults" {
  command = apply

  # PVC-094: one allow-list drives the firewall and the in-process check.
  assert {
    condition = toset(output.egress_allowed_domains) == toset([
      "api.anthropic.com", "login.example.com", "keys.example.com", "otlp.example.net",
      "warehouse.example.com", ".snowflakecomputing.com",
    ])
    error_message = "Unexpected egress allow-list: ${jsonencode(output.egress_allowed_domains)}"
  }

  assert {
    condition     = aws_networkfirewall_rule_group.egress_allowlist.rule_group[0].rules_source[0].rules_source_list[0].generated_rules_type == "ALLOWLIST"
    error_message = "The firewall rule group must be an allow-list."
  }

  assert {
    condition     = contains(aws_networkfirewall_firewall_policy.egress.firewall_policy[0].stateful_default_actions, "aws:drop_established")
    error_message = "Traffic not on the allow-list must be dropped."
  }

  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.this["mcp"].container_definitions)[0].environment : "${e.name}=${e.value}"],
      "PVC_EGRESS_ALLOWLIST=api.anthropic.com,login.example.com,keys.example.com,otlp.example.net,warehouse.example.com,*.snowflakecomputing.com",
    )
    error_message = "The MCP task must receive the same egress allow-list, in application syntax."
  }

  # Auth is on outside dev; database URL carries no password.
  assert {
    condition = alltrue([
      for s in ["mcp", "api", "worker"] : contains(
        [for e in jsondecode(aws_ecs_task_definition.this[s].container_definitions)[0].environment : "${e.name}=${e.value}"],
        "PVC_ENV=staging",
      )
    ])
    error_message = "Services must run with PVC_ENV=staging (authentication required)."
  }

  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.this["api"].container_definitions)[0].environment : "${e.name}=${e.value}"],
      "DATABASE_URL=postgresql://pvc_app@pvc-staging.abc.us-east-1.rds.amazonaws.com:5432/pvc?sslmode=verify-full&sslrootcert=/app/certs/rds-global-bundle.pem",
    )
    error_message = "The API must connect as pvc_app over TLS without a password in the URL."
  }

  # Secrets arrive as ECS secrets; the bootstrap task reads the master password JSON key.
  assert {
    condition = contains(
      [for s in jsondecode(aws_ecs_task_definition.this["bootstrap"].container_definitions)[0].secrets : s.valueFrom],
      "arn:aws:secretsmanager:us-east-1:111111111111:secret:rds!db-1234-AbCdEf:password::",
    )
    error_message = "The bootstrap task must read the RDS-managed master password."
  }

  assert {
    condition     = length(jsondecode(aws_ecs_task_definition.this["mcp"].container_definitions)[0].secrets) == 1
    error_message = "With PVC_PROPOSER=rules the MCP task needs only its database password."
  }

  # PVC-132
  assert {
    condition = (
      aws_db_instance.this.storage_encrypted && !aws_db_instance.this.publicly_accessible
      && aws_db_instance.this.backup_retention_period >= 1 && aws_db_instance.this.engine == "postgres"
    )
    error_message = "The database must be encrypted, private and backed up."
  }

  assert {
    condition     = contains([for p in aws_db_parameter_group.this.parameter : "${p.name}=${p.value}"], "rds.force_ssl=1")
    error_message = "The parameter group must force TLS."
  }

  # Evidence bucket
  assert {
    condition     = aws_s3_bucket_object_lock_configuration.evidence.rule[0].default_retention[0].mode == "GOVERNANCE"
    error_message = "Evidence needs Object Lock in governance mode."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.evidence.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "aws:kms"
    error_message = "Evidence must be encrypted with SSE-KMS."
  }

  # PVC-135
  assert {
    condition     = aws_lb_listener.http.default_action[0].redirect[0].protocol == "HTTPS"
    error_message = "HTTP must redirect to HTTPS."
  }

  assert {
    condition     = one([for r in aws_wafv2_web_acl.this.rule : r.statement[0].rate_based_statement[0].limit if r.name == "rate-limit-per-ip"]) == 1000
    error_message = "WAF must rate-limit per IP."
  }

  assert {
    condition     = one([for r in aws_wafv2_web_acl.this.rule : r.statement[0].regex_match_statement[0].regex_string if r.name == "request-size-limit"]) == "^[0-9]{7,}$"
    error_message = "WAF must block Content-Length of 1,000,000 bytes or more by default."
  }

  assert {
    condition     = aws_lb_target_group.this["mcp"].health_check[0].path == "/.well-known/oauth-protected-resource/mcp"
    error_message = "MCP health check must use the protected-resource metadata path."
  }

  # Staging is deletable; worker has no load balancer.
  assert {
    condition     = !aws_db_instance.this.deletion_protection && !aws_lb.this.enable_deletion_protection
    error_message = "Staging should not enable deletion protection."
  }

  assert {
    condition     = length(aws_ecs_service.this["worker"].load_balancer) == 0 && length(aws_ecs_service.this["mcp"].load_balancer) == 1
    error_message = "Only mcp and api sit behind the load balancer."
  }
}

run "production_settings" {
  command = apply

  variables {
    environment            = "production"
    github_environment     = "production"
    az_count               = 3
    deletion_protection    = true
    db_multi_az            = true
    proposer               = "model"
    notify_webhook_enabled = true
    notify_webhook_host    = "hooks.slack.com"
    max_request_body_bytes = 10000000
  }

  assert {
    condition     = aws_db_instance.this.deletion_protection && aws_db_instance.this.multi_az && aws_lb.this.enable_deletion_protection
    error_message = "Production must be Multi-AZ with deletion protection."
  }

  assert {
    condition = contains(
      [for e in jsondecode(aws_ecs_task_definition.this["worker"].container_definitions)[0].environment : "${e.name}=${e.value}"],
      "PVC_ENV=prod",
    )
    error_message = "Production containers must run with PVC_ENV=prod."
  }

  assert {
    condition = toset([for s in jsondecode(aws_ecs_task_definition.this["worker"].container_definitions)[0].secrets : s.name]) == toset([
      "PGPASSWORD", "ANTHROPIC_API_KEY", "PVC_NOTIFY_WEBHOOK_URL",
    ])
    error_message = "The worker needs the model key and webhook secrets when enabled."
  }

  assert {
    condition     = !contains([for s in jsondecode(aws_ecs_task_definition.this["mcp"].container_definitions)[0].secrets : s.name], "PVC_NOTIFY_WEBHOOK_URL")
    error_message = "Only the worker sends notifications."
  }

  assert {
    condition     = contains(output.egress_allowed_domains, "hooks.slack.com")
    error_message = "The webhook host must be on the egress allow-list."
  }

  assert {
    condition     = length(aws_nat_gateway.this) == 3 && length(aws_route.app_default) == 3
    error_message = "Production uses one NAT gateway and firewall route per availability zone."
  }

  assert {
    condition     = one([for r in aws_wafv2_web_acl.this.rule : r.statement[0].regex_match_statement[0].regex_string if r.name == "request-size-limit"]) == "^[0-9]{8,}$"
    error_message = "A 10 MB limit must block Content-Length values of eight or more digits."
  }
}

run "rejects_non_power_of_ten_body_limit" {
  command = plan

  variables {
    max_request_body_bytes = 5000000
  }

  expect_failures = [var.max_request_body_bytes]
}
