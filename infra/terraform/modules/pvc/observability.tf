# Logs and alarms. Every log group is KMS-encrypted and has a retention period. Application logs are
# structlog JSON (PVC-100); traces and metrics go to OTEL_EXPORTER_OTLP_ENDPOINT when configured.

resource "aws_cloudwatch_log_group" "workload" {
  for_each          = local.workloads
  name              = "/ecs/${local.prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "firewall" {
  for_each          = toset(["alert", "flow"])
  name              = "/network-firewall/${local.prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.tags
}

# RDS creates these on first export; creating them here sets retention and encryption.
resource "aws_cloudwatch_log_group" "rds" {
  for_each          = toset(["postgresql", "upgrade"])
  name              = "/aws/rds/instance/${local.prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.tags
}

# WAF requires the "aws-waf-logs-" prefix. Bearer tokens and cookies are redacted.
resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${local.prefix}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
  tags              = local.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}

# ---- Alarms -----------------------------------------------------------------------------------------------
locals {
  alarm_actions = var.alarm_topic_arn == null ? [] : [var.alarm_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "target_5xx" {
  for_each            = local.services_with_port
  alarm_name          = "${local.prefix}-${each.key}-5xx"
  alarm_description   = "${each.key}: more than 10 target 5xx responses in 5 minutes"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.this[each.key].arn_suffix
  }
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "unhealthy_targets" {
  for_each            = local.services_with_port
  alarm_name          = "${local.prefix}-${each.key}-unhealthy"
  alarm_description   = "${each.key}: at least one unhealthy target for 5 minutes"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.this[each.key].arn_suffix
  }
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "db_cpu" {
  alarm_name          = "${local.prefix}-db-cpu"
  alarm_description   = "Database CPU above 80% for 15 minutes"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.identifier }
  tags                = local.tags
}

resource "aws_cloudwatch_metric_alarm" "db_free_storage" {
  alarm_name          = "${local.prefix}-db-free-storage"
  alarm_description   = "Database free storage below 10 GiB"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10737418240
  comparison_operator = "LessThanThreshold"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.identifier }
  tags                = local.tags
}

resource "aws_cloudwatch_metric_alarm" "waf_blocked" {
  alarm_name          = "${local.prefix}-waf-blocked-spike"
  alarm_description   = "More than 500 WAF-blocked requests in 5 minutes (attack or a legitimate client being throttled)"
  namespace           = "AWS/WAFV2"
  metric_name         = "BlockedRequests"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 500
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  dimensions = {
    WebACL = aws_wafv2_web_acl.this.name
    Region = local.region
    Rule   = "ALL"
  }
  tags = local.tags
}

# Dropped egress means a process tried to reach a host that is not on the allow-list.
resource "aws_cloudwatch_log_metric_filter" "egress_denied" {
  name           = "${local.prefix}-egress-denied"
  log_group_name = aws_cloudwatch_log_group.firewall["alert"].name
  pattern        = "{ $.event.alert.action = \"blocked\" }"

  metric_transformation {
    name          = "EgressDenied"
    namespace     = "PVC/${local.prefix}"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "egress_denied" {
  alarm_name          = "${local.prefix}-egress-denied"
  alarm_description   = "Network Firewall dropped outbound traffic to a host outside the egress allow-list"
  namespace           = "PVC/${local.prefix}"
  metric_name         = "EgressDenied"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  tags                = local.tags
}
