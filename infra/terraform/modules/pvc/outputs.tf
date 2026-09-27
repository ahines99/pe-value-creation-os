output "mcp_url" {
  description = "Public MCP endpoint (Streamable HTTP)."
  value       = local.mcp_resource_url
}

output "api_url" {
  description = "Public approval API and review UI."
  value       = local.public_api_url
}

output "alb_dns_name" {
  description = "Point mcp_hostname and api_hostname at this name (alias or CNAME)."
  value       = aws_lb.this.dns_name
}

output "alb_zone_id" {
  description = "Hosted zone id of the ALB, for Route 53 alias records."
  value       = aws_lb.this.zone_id
}

output "nat_public_ips" {
  description = "Egress IPs, for data sources that allow-list callers by IP."
  value       = aws_eip.nat[*].public_ip
}

output "egress_allowed_domains" {
  description = "Domains the Network Firewall lets the application reach."
  value       = local.egress_domains
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "app_subnet_ids" {
  value = aws_subnet.app[*].id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecs_services" {
  value = { for k, s in aws_ecs_service.this : k => s.name }
}

output "task_definition_families" {
  value = { for k, td in aws_ecs_task_definition.this : k => td.family }
}

output "workload_security_group_ids" {
  value = { for k, sg in aws_security_group.workload : k => sg.id }
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.bucket
}

output "db_endpoint" {
  value = local.db_endpoint
}

output "db_master_secret_arn" {
  description = "RDS-managed master credentials (bootstrap task only)."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "secret_arns" {
  description = "Secrets whose values operators set or rotate."
  value = merge(
    { for k, s in aws_secretsmanager_secret.db_role : "db-pvc_${k}" => s.arn },
    { for k, s in aws_secretsmanager_secret.app : k => s.arn },
  )
}

output "github_deploy_role_arn" {
  value = aws_iam_role.deploy.arn
}

output "github_environment_variables" {
  description = "Variables to set on the matching GitHub environment for .github/workflows/cd.yml."
  value = {
    AWS_REGION         = local.region
    AWS_DEPLOY_ROLE    = aws_iam_role.deploy.arn
    ECR_REPOSITORY_URL = aws_ecr_repository.this.repository_url
    ECS_CLUSTER        = aws_ecs_cluster.this.name
    TASK_FAMILY_PREFIX = "${local.prefix}-"
    MCP_URL            = local.mcp_resource_url
    API_URL            = local.public_api_url
  }
}
