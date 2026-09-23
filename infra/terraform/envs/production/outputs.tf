output "mcp_url" {
  value = module.pvc.mcp_url
}

output "api_url" {
  value = module.pvc.api_url
}

output "alb_dns_name" {
  value = module.pvc.alb_dns_name
}

output "alb_zone_id" {
  value = module.pvc.alb_zone_id
}

output "nat_public_ips" {
  value = module.pvc.nat_public_ips
}

output "egress_allowed_domains" {
  value = module.pvc.egress_allowed_domains
}

output "ecr_repository_url" {
  value = module.pvc.ecr_repository_url
}

output "ecs_cluster_name" {
  value = module.pvc.ecs_cluster_name
}

output "evidence_bucket" {
  value = module.pvc.evidence_bucket
}

output "db_endpoint" {
  value = module.pvc.db_endpoint
}

output "secret_arns" {
  value = module.pvc.secret_arns
}

output "github_environment_variables" {
  value = module.pvc.github_environment_variables
}
