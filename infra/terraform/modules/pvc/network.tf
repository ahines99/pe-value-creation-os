# Network (PVC-131) and egress controls (PVC-094).
#
# Per availability zone (/24 each, from the /16 VPC):
#   ingress  10.x.0-2.0    public; the load balancer only. Default route -> internet gateway.
#   nat      10.x.10-12.0  public; NAT gateway. Return traffic to the app tier -> firewall endpoint.
#   firewall 10.x.20-22.0  AWS Network Firewall endpoint. Default route -> NAT gateway.
#   app      10.x.100-102.0 private; ECS tasks. Default route -> firewall endpoint (domain allow-list).
#   db       10.x.200-202.0 private; RDS. No route outside the VPC.
#
# Outbound path: app -> firewall -> NAT -> internet. Only TLS (SNI) and HTTP (Host) connections to
# local.egress_domains pass; everything else is dropped. AWS APIs the platform needs (ECR, S3, CloudWatch
# Logs, Secrets Manager) are reached through VPC endpoints and never cross the firewall.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  subnet_cidrs = {
    ingress  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
    nat      = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 10 + i)]
    firewall = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 20 + i)]
    app      = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 100 + i)]
    db       = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 200 + i)]
  }

  # AZ name -> firewall endpoint id.
  firewall_endpoints = {
    for s in aws_networkfirewall_firewall.egress.firewall_status[0].sync_states :
    s.availability_zone => s.attachment[0].endpoint_id
  }

  interface_endpoints = toset(["ecr.api", "ecr.dkr", "logs", "secretsmanager"])
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = local.prefix })
}

# Remove all rules from the default security group so nothing can use it by accident.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.prefix}-default-unused" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = local.prefix })
}

# ---- Subnets ----------------------------------------------------------------------------------------------
resource "aws_subnet" "ingress" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = local.subnet_cidrs.ingress[count.index]
  tags              = merge(local.tags, { Name = "${local.prefix}-ingress-${local.azs[count.index]}", Tier = "ingress" })
}

resource "aws_subnet" "nat" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = local.subnet_cidrs.nat[count.index]
  tags              = merge(local.tags, { Name = "${local.prefix}-nat-${local.azs[count.index]}", Tier = "nat" })
}

resource "aws_subnet" "firewall" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = local.subnet_cidrs.firewall[count.index]
  tags              = merge(local.tags, { Name = "${local.prefix}-firewall-${local.azs[count.index]}", Tier = "firewall" })
}

resource "aws_subnet" "app" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = local.subnet_cidrs.app[count.index]
  tags              = merge(local.tags, { Name = "${local.prefix}-app-${local.azs[count.index]}", Tier = "app" })
}

resource "aws_subnet" "db" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = local.subnet_cidrs.db[count.index]
  tags              = merge(local.tags, { Name = "${local.prefix}-db-${local.azs[count.index]}", Tier = "db" })
}

# ---- NAT --------------------------------------------------------------------------------------------------
resource "aws_eip" "nat" {
  count  = var.az_count
  domain = "vpc"
  tags   = merge(local.tags, { Name = "${local.prefix}-nat-${local.azs[count.index]}" })
}

resource "aws_nat_gateway" "this" {
  count         = var.az_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.nat[count.index].id
  tags          = merge(local.tags, { Name = "${local.prefix}-${local.azs[count.index]}" })

  depends_on = [aws_internet_gateway.this]
}

# ---- Route tables -----------------------------------------------------------------------------------------
resource "aws_route_table" "ingress" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.prefix}-ingress" })
}

resource "aws_route" "ingress_default" {
  route_table_id         = aws_route_table.ingress.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "ingress" {
  count          = var.az_count
  subnet_id      = aws_subnet.ingress[count.index].id
  route_table_id = aws_route_table.ingress.id
}

resource "aws_route_table" "nat" {
  count  = var.az_count
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.prefix}-nat-${local.azs[count.index]}" })
}

resource "aws_route" "nat_default" {
  count                  = var.az_count
  route_table_id         = aws_route_table.nat[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

# Symmetric routing: replies for the app tier go back through the same firewall endpoint.
resource "aws_route" "nat_to_app_via_firewall" {
  count                  = var.az_count
  route_table_id         = aws_route_table.nat[count.index].id
  destination_cidr_block = local.subnet_cidrs.app[count.index]
  vpc_endpoint_id        = local.firewall_endpoints[local.azs[count.index]]
}

resource "aws_route_table_association" "nat" {
  count          = var.az_count
  subnet_id      = aws_subnet.nat[count.index].id
  route_table_id = aws_route_table.nat[count.index].id
}

resource "aws_route_table" "firewall" {
  count  = var.az_count
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.prefix}-firewall-${local.azs[count.index]}" })
}

resource "aws_route" "firewall_default" {
  count                  = var.az_count
  route_table_id         = aws_route_table.firewall[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[count.index].id
}

resource "aws_route_table_association" "firewall" {
  count          = var.az_count
  subnet_id      = aws_subnet.firewall[count.index].id
  route_table_id = aws_route_table.firewall[count.index].id
}

resource "aws_route_table" "app" {
  count  = var.az_count
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.prefix}-app-${local.azs[count.index]}" })
}

resource "aws_route" "app_default" {
  count                  = var.az_count
  route_table_id         = aws_route_table.app[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  vpc_endpoint_id        = local.firewall_endpoints[local.azs[count.index]]
}

resource "aws_route_table_association" "app" {
  count          = var.az_count
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.app[count.index].id
}

# Database subnets: local routes only.
resource "aws_route_table" "db" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.prefix}-db" })
}

resource "aws_route_table_association" "db" {
  count          = var.az_count
  subnet_id      = aws_subnet.db[count.index].id
  route_table_id = aws_route_table.db.id
}

# ---- VPC endpoints (AWS APIs without internet egress) -----------------------------------------------------
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.app[*].id
  tags              = merge(local.tags, { Name = "${local.prefix}-s3" })
}

resource "aws_security_group" "endpoints" {
  name        = "${local.prefix}-vpc-endpoints"
  description = "HTTPS from the VPC to interface endpoints"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.tags, { Name = "${local.prefix}-vpc-endpoints" })
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  security_group_id = aws_security_group.endpoints.id
  description       = "HTTPS from inside the VPC"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = var.vpc_cidr
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = local.interface_endpoints
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${local.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = aws_subnet.app[*].id
  security_group_ids  = [aws_security_group.endpoints.id]
  tags                = merge(local.tags, { Name = "${local.prefix}-${each.key}" })
}

# ---- AWS Network Firewall: domain allow-list for egress ---------------------------------------------------
resource "aws_networkfirewall_rule_group" "egress_allowlist" {
  name        = "${local.prefix}-egress-allowlist"
  description = "Allowed outbound domains (model provider, identity provider, telemetry, data sources)"
  type        = "STATEFUL"
  capacity    = 200

  rule_group {
    rule_variables {
      ip_sets {
        key = "HOME_NET"
        ip_set {
          definition = [var.vpc_cidr]
        }
      }
    }

    rules_source {
      rules_source_list {
        generated_rules_type = "ALLOWLIST"
        target_types         = ["TLS_SNI", "HTTP_HOST"]
        targets              = local.egress_domains
      }
    }

    stateful_rule_options {
      rule_order = "STRICT_ORDER"
    }
  }

  tags = local.tags

  lifecycle {
    precondition {
      condition     = length(local.egress_domains) > 0
      error_message = "The egress allow-list is empty."
    }
  }
}

resource "aws_networkfirewall_firewall_policy" "egress" {
  name = "${local.prefix}-egress"

  firewall_policy {
    stateless_default_actions          = ["aws:forward_to_sfe"]
    stateless_fragment_default_actions = ["aws:forward_to_sfe"]

    # Anything not explicitly passed by the allow-list is dropped once the flow is established, and logged.
    stateful_default_actions = ["aws:drop_established", "aws:alert_established"]

    stateful_engine_options {
      rule_order = "STRICT_ORDER"
    }

    stateful_rule_group_reference {
      priority     = 100
      resource_arn = aws_networkfirewall_rule_group.egress_allowlist.arn
    }
  }

  tags = local.tags
}

resource "aws_networkfirewall_firewall" "egress" {
  name                              = "${local.prefix}-egress"
  vpc_id                            = aws_vpc.this.id
  firewall_policy_arn               = aws_networkfirewall_firewall_policy.egress.arn
  delete_protection                 = var.deletion_protection
  subnet_change_protection          = var.deletion_protection
  firewall_policy_change_protection = false

  dynamic "subnet_mapping" {
    for_each = aws_subnet.firewall[*].id
    content {
      subnet_id = subnet_mapping.value
    }
  }

  tags = local.tags
}

resource "aws_networkfirewall_logging_configuration" "egress" {
  firewall_arn = aws_networkfirewall_firewall.egress.arn

  logging_configuration {
    log_destination_config {
      log_type             = "ALERT"
      log_destination_type = "CloudWatchLogs"
      log_destination = {
        logGroup = aws_cloudwatch_log_group.firewall["alert"].name
      }
    }

    log_destination_config {
      log_type             = "FLOW"
      log_destination_type = "CloudWatchLogs"
      log_destination = {
        logGroup = aws_cloudwatch_log_group.firewall["flow"].name
      }
    }
  }
}

# ---- Security groups for workloads ------------------------------------------------------------------------
resource "aws_security_group" "workload" {
  for_each    = local.workloads
  name        = "${local.prefix}-${each.key}"
  description = "${each.key} tasks"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.tags, { Name = "${local.prefix}-${each.key}" })
}

resource "aws_vpc_security_group_ingress_rule" "workload_from_alb" {
  for_each                     = local.services_with_port
  security_group_id            = aws_security_group.workload[each.key].id
  description                  = "Load balancer to ${each.key}"
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
  referenced_security_group_id = aws_security_group.alb.id
}

# HTTPS out: VPC endpoints inside the VPC, allow-listed domains through the firewall.
resource "aws_vpc_security_group_egress_rule" "workload_https" {
  for_each          = local.workloads
  security_group_id = aws_security_group.workload[each.key].id
  description       = "HTTPS egress (filtered by Network Firewall)"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "workload_postgres" {
  for_each                     = local.workloads
  security_group_id            = aws_security_group.workload[each.key].id
  description                  = "PostgreSQL"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.db.id
}
