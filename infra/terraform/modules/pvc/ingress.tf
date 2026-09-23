# Ingress and TLS (PVC-135): one internet-facing ALB, host-based routing.
#   https://<mcp_hostname>/mcp  -> mcp service (:8000)
#   https://<api_hostname>/     -> approval API and review UI (:8080)
# HTTP redirects to HTTPS; TLS 1.2+ only; WAFv2 applies per-IP rate limiting, a request-size limit and the
# AWS managed common and known-bad-inputs rule sets. Unknown hosts get 404.

locals {
  target_health = {
    # Protected-resource metadata (RFC 9728) is served without a token once auth is configured, so a 200
    # here proves the MCP app is up and wired to the identity provider.
    mcp = { path = "/.well-known/oauth-protected-resource/mcp", matcher = "200", hostname = var.mcp_hostname, priority = 10 }
    api = { path = "/healthz", matcher = "200", hostname = var.api_hostname, priority = 20 }
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
