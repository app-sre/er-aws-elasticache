
output "db_endpoint" {
  value = aws_elasticache_replication_group.this.cluster_enabled ? aws_elasticache_replication_group.this.configuration_endpoint_address : aws_elasticache_replication_group.this.primary_endpoint_address
}

output "db_port" {
  value = aws_elasticache_replication_group.this.port
}

output "db_auth_token" {
  value     = aws_elasticache_replication_group.this.auth_token
  sensitive = true
}
