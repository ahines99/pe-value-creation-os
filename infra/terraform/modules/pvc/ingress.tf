# Ingress and TLS (PVC-135): one internet-facing ALB, host-based routing.
#   https://<mcp_hostname>/mcp  -> mcp service (:8000)
#   https://<api_hostname>/     -> approval API and review UI (:8080)
# HTTP redirects to HTTPS; TLS 1.2+ only; WAFv2 applies per-IP rate limiting, a request-size limit and the
# AWS managed common and known-bad-inputs rule sets. Unknown hosts get 404.

locals {
  target_health = {
    mcp = { path = "/readyz", matcher = "200", hostname = var.mcp_hostname, priority = 10 }
    api = { path = "/readyz", matcher = "200", hostname = var.api_hostname, priority = 20 }
  }
}

resource "aws_security_group" "alb" {
  name        = "${local.prefix}-alb"
  description = "Public HTTPS load balancer"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.tags, { Name = "${local.prefix}-alb" })
}

resource "aws_vpc_security_group_ingress_rule" "alb" {
  for_each          = { for pair in setproduct(var.ingress_cidrs, [80, 443]) : "${pair[0]}-${pair[1]}" => pair }
  security_group_id = aws_security_group.alb.id
  description       = each.value[1] == 443 ? "HTTPS" : "HTTP (redirected to HTTPS)"
  ip_protocol       = "tcp"
  from_port         = each.value[1]
  to_port           = each.value[1]
  cidr_ipv4         = each.value[0]
}

resource "aws_vpc_security_group_egress_rule" "alb_to_targets" {
  for_each                     = local.services_with_port
  security_group_id            = aws_security_group.alb.id
  description                  = "ALB to ${each.key} targets"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = aws_security_group.workload[each.key].id
}

# ALB authentication calls the IdP token and user-info endpoints itself. These
# calls originate in the public ALB subnets, not in the application firewall path.
# Security groups cannot filter DNS names; restrict to HTTPS, only when OIDC is on.
resource "aws_vpc_security_group_egress_rule" "alb_oidc_https" {
  count             = var.api_browser_oidc == null ? 0 : 1
  security_group_id = aws_security_group.alb.id
  description       = "ALB OIDC token and user-info HTTPS requests"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_lb" "this" {
  name                       = local.prefix
  internal                   = false
  load_balancer_type         = "application"
  subnets                    = aws_subnet.ingress[*].id
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
  idle_timeout               = var.alb_idle_timeout
  tags                       = local.tags

  # Request logs for incident response (docs/runbooks/data-exposure.md).
  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    prefix  = "alb"
    enabled = true
  }

  depends_on = [aws_s3_bucket_policy.alb_logs]
}

# ---- ALB access logs --------------------------------------------------------------------------------------
# ALB log delivery supports SSE-S3 only (not SSE-KMS). Logs hold request metadata (paths, client IPs), never
# bodies or tokens; they expire after var.log_retention_days.
data "aws_elb_service_account" "this" {}

resource "aws_s3_bucket" "alb_logs" {
  bucket        = "${local.prefix}-alb-logs-${local.account_id}"
  force_destroy = !var.deletion_protection
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  bucket                  = aws_s3_bucket.alb_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    id     = "expire"
    status = "Enabled"
    filter {}
    expiration {
      days = var.log_retention_days
    }
  }
}

data "aws_iam_policy_document" "alb_logs" {
  statement {
    sid       = "AlbLogDelivery"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/alb/AWSLogs/${local.account_id}/*"]
    principals {
      type        = "AWS"
      identifiers = [data.aws_elb_service_account.this.arn]
    }
  }
  statement {
    sid       = "AlbLogDeliveryService"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/alb/AWSLogs/${local.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["logdelivery.elasticloadbalancing.amazonaws.com"]
    }
  }
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.alb_logs.arn,
      "${aws_s3_bucket.alb_logs.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  bucket     = aws_s3_bucket.alb_logs.id
  policy     = data.aws_iam_policy_document.alb_logs.json
  depends_on = [aws_s3_bucket_public_access_block.alb_logs]
}

resource "aws_lb_target_group" "this" {
  for_each             = local.services_with_port
  name                 = "${local.prefix}-${each.key}"
  port                 = each.value.port
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.this.id
  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = local.target_health[each.key].path
    matcher             = local.target_health[each.key].matcher
    protocol            = "HTTP"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = local.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = var.alb_ssl_policy
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = "{\"error\":\"not_found\"}"
      status_code  = "404"
    }
  }

  tags = local.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }

  tags = local.tags
}

resource "aws_lb_listener_rule" "host" {
  for_each     = local.services_with_port
  listener_arn = aws_lb_listener.https.arn
  priority     = local.target_health[each.key].priority

  condition {
    host_header {
      values = [local.target_health[each.key].hostname]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[each.key].arn
  }

  tags = local.tags
}

# Browser pages of the approval UI: the ALB signs the user in with the identity provider (OIDC) and forwards
# the IdP access token in x-amzn-oidc-accesstoken, which the API verifies like a bearer token. JSON API calls
# with a bearer token use the plain host rule above. Higher priority (lower number) than the host rule.
# Explicit bearer clients still reach API authentication on browser-shaped URLs
# (notably evidence downloads); the application verifies the bearer token itself.
resource "aws_lb_listener_rule" "api_bearer" {
  count        = var.api_browser_oidc == null ? 0 : 1
  listener_arn = aws_lb_listener.https.arn
  priority     = 14
  condition {
    host_header { values = [var.api_hostname] }
  }
  condition {
    http_header {
      http_header_name = "Authorization"
      values           = ["Bearer *", "bearer *"]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this["api"].arn
  }
}

resource "aws_lb_listener_rule" "api_browser" {
  count        = var.api_browser_oidc == null ? 0 : 1
  listener_arn = aws_lb_listener.https.arn
  priority     = 15

  condition {
    host_header {
      values = [var.api_hostname]
    }
  }

  condition {
    path_pattern {
      values = ["/", "/runs/*/review", "/runs/*/approvals/form", "/evidence/*", "/companies/*"]
    }
  }

  action {
    type = "authenticate-oidc"
    authenticate_oidc {
      issuer                     = var.api_browser_oidc.issuer
      authorization_endpoint     = var.api_browser_oidc.authorization_endpoint
      token_endpoint             = var.api_browser_oidc.token_endpoint
      user_info_endpoint         = var.api_browser_oidc.user_info_endpoint
      client_id                  = var.api_browser_oidc.client_id
      client_secret              = var.api_browser_oidc.client_secret
      scope                      = var.api_browser_oidc.scope
      session_timeout            = 28800
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this["api"].arn
  }

  tags = local.tags
}

# ---- WAF --------------------------------------------------------------------------------------------------
resource "aws_wafv2_web_acl" "this" {
  name        = local.prefix
  description = "Rate limiting, request size limit and managed protections for ${local.prefix}"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "rate-limit-per-ip"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_rate_limit
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # ALB WAF inspects at most the first 8 KB of a body, so the size limit is enforced on the declared
  # Content-Length: a value with as many digits as max_request_body_bytes (a power of ten) or more is too big.
  rule {
    name     = "request-size-limit"
    priority = 2

    action {
      block {}
    }

    statement {
      regex_match_statement {
        regex_string = "^[0-9]{${length(tostring(var.max_request_body_bytes))},}$"

        field_to_match {
          single_header {
            name = "content-length"
          }
        }

        text_transformation {
          priority = 0
          type     = "NONE"
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-request-size"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-common"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        # The managed 8 KB body limit would block legitimate MCP tool calls; request-size-limit replaces it.
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-aws-common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "aws-known-bad-inputs"
    priority = 20

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.prefix}-aws-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = local.prefix
    sampled_requests_enabled   = true
  }

  tags = local.tags
}

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}
