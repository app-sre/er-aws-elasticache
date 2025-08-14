# Tests for ElastiCache Replication Group resource
variables {
  region                        = "us-east-1"
  identifier                    = "test-elasticache"
  output_resource_name          = "test-elasticache"
  output_prefix                 = "test-elasticache"
  replication_group_id          = "test-redis-cluster"
  replication_group_description = "Test Redis cluster"
  engine                        = "redis"
  engine_version                = "7.0"
  node_type                     = "cache.t3.micro"
  number_cache_clusters         = 2
  security_group_ids            = ["sg-123456789"]
  subnet_group_name             = "test-subnet-group"
  tags = {
    Environment = "test"
    Component   = "elasticache"
  }
  transit_encryption_enabled = true

}

run "replication_group_basic_configuration" {
  command = plan

  assert {
    condition     = aws_elasticache_replication_group.this.replication_group_id == "test-redis-cluster"
    error_message = "Replication group ID should match input variable"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.engine == "redis"
    error_message = "Engine should be redis"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.engine_version == "7.0"
    error_message = "Engine version should match input"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.node_type == "cache.t3.micro"
    error_message = "Node type should match input"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.num_cache_clusters == 2
    error_message = "Number of cache clusters should match input"
  }
}

run "replication_group_security_settings" {
  command = plan

  variables {
    at_rest_encryption_enabled = true
    transit_encryption_enabled = true
  }

  assert {
    condition     = aws_elasticache_replication_group.this.at_rest_encryption_enabled == "true"
    error_message = "At-rest encryption should be enabled"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled == true
    error_message = "Transit encryption should be enabled"
  }
}

run "replication_group_without_encryption" {
  command = plan

  variables {
    at_rest_encryption_enabled = false
    transit_encryption_enabled = false
  }

  assert {
    condition     = aws_elasticache_replication_group.this.at_rest_encryption_enabled == "false"
    error_message = "At-rest encryption should be disabled"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled == false
    error_message = "Transit encryption should be disabled"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token == null
    error_message = "Auth token should be null when transit encryption is disabled"
  }
}

run "replication_group_backup_settings" {
  command = plan

  variables {
    snapshot_retention_limit = 5
    snapshot_window          = "03:00-05:00"
    maintenance_window       = "sun:02:00-sun:03:00"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.snapshot_retention_limit == 5
    error_message = "Snapshot retention limit should match input"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.snapshot_window == "03:00-05:00"
    error_message = "Snapshot window should match input"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.maintenance_window == "sun:02:00-sun:03:00"
    error_message = "Maintenance window should match input"
  }
}

run "replication_group_high_availability" {
  command = plan

  variables {
    automatic_failover_enabled = true
    multi_az_enabled           = true
    availability_zones         = ["us-east-1a", "us-east-1b"]
  }

  assert {
    condition     = aws_elasticache_replication_group.this.automatic_failover_enabled == true
    error_message = "Automatic failover should be enabled"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.multi_az_enabled == true
    error_message = "Multi-AZ should be enabled"
  }

  assert {
    condition     = length(aws_elasticache_replication_group.this.preferred_cache_cluster_azs) == 2
    error_message = "Should have 2 availability zones configured"
  }
}

run "replication_group_cluster_mode" {
  command = plan

  variables {
    num_node_groups         = 2
    replicas_per_node_group = 1
    number_cache_clusters   = null
  }

  assert {
    condition     = aws_elasticache_replication_group.this.num_node_groups == 2
    error_message = "Number of node groups should match input"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.replicas_per_node_group == 1
    error_message = "Replicas per node group should match input"
  }
}

run "replication_group_networking" {
  command = plan

  variables {
    port               = 6379
    security_group_ids = ["sg-123456789", "sg-987654321"]
    subnet_group_name  = "custom-subnet-group"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.port == 6379
    error_message = "Port should match input"
  }

  assert {
    condition     = length(aws_elasticache_replication_group.this.security_group_ids) == 2
    error_message = "Should have 2 security groups configured"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.subnet_group_name == "custom-subnet-group"
    error_message = "Subnet group name should match input"
  }
}

run "replication_group_logging" {
  command = plan

  variables {
    log_delivery_configuration = [
      {
        destination      = "cloudwatch-logs"
        destination_type = "cloudwatch-logs"
        log_format       = "json"
        log_type         = "slow-log"
      }
    ]
  }

  assert {
    condition     = length(aws_elasticache_replication_group.this.log_delivery_configuration) == 1
    error_message = "Should have one log delivery configuration"
  }
}

run "replication_group_tags" {
  command = plan

  variables {
    tags = {
      Environment = "test"
      Component   = "elasticache"
      Team        = "platform"
    }
  }

  assert {
    condition     = aws_elasticache_replication_group.this.tags["Environment"] == "test"
    error_message = "Environment tag should be set correctly"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.tags["Component"] == "elasticache"
    error_message = "Component tag should be set correctly"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.tags["Team"] == "platform"
    error_message = "Team tag should be set correctly"
  }
}
