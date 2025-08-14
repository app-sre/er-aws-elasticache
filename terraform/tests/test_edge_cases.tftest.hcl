# Tests for edge cases and boundary conditions
variables {
  region                     = "us-east-1"
  identifier                 = "test-elasticache"
  output_resource_name       = "test-elasticache"
  output_prefix              = "test-elasticache"
  replication_group_id       = "test-redis-cluster"
  engine                     = "redis"
  engine_version             = "7.0"
  node_type                  = "cache.t3.micro"
  number_cache_clusters      = 2
  security_group_ids         = ["sg-123456789"]
  subnet_group_name          = "test-subnet-group"
  transit_encryption_enabled = true
}

run "minimum_viable_configuration" {
  command = plan
  assert {
    condition     = aws_elasticache_replication_group.this.replication_group_id == var.replication_group_id
    error_message = "Module should work with minimal configuration"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.engine == var.engine
    error_message = "Engine should be set correctly in minimal config"
  }
}

run "maximum_configuration" {
  command = plan

  variables {
    # Test with all possible variables set
    apply_immediately          = true
    at_rest_encryption_enabled = true
    auto_minor_version_upgrade = false
    automatic_failover_enabled = true
    availability_zones         = ["us-east-1a", "us-east-1b", "us-east-1c"]
    maintenance_window         = "sun:02:00-sun:03:00"
    multi_az_enabled           = true
    notification_topic_arn     = "arn:aws:sns:us-east-1:123456789012:test-topic"
    num_node_groups            = null
    port                       = 6379
    replicas_per_node_group    = null
    snapshot_retention_limit   = 10
    snapshot_window            = "03:00-05:00"
    transit_encryption_enabled = true
    transit_encryption_mode    = "preferred"
    parameter_group = {
      name        = "max-config-pg"
      family      = "redis7.x"
      description = "Maximum configuration parameter group"
      parameters = [
        { name = "maxmemory-policy", value = "allkeys-lru" },
        { name = "timeout", value = "300" },
        { name = "tcp-keepalive", value = "60" }
      ]
    }
    log_delivery_configuration = [
      {
        destination      = "cloudwatch-logs"
        destination_type = "cloudwatch-logs"
        log_format       = "json"
        log_type         = "slow-log"
      },
      {
        destination      = "kinesis-firehose"
        destination_type = "kinesis-firehose"
        log_format       = "text"
        log_type         = "engine-log"
      }
    ]
    tags = {
      Environment = "test"
      Component   = "elasticache"
      Team        = "platform"
      CostCenter  = "engineering"
    }
  }

  assert {
    condition     = aws_elasticache_replication_group.this.apply_immediately == true
    error_message = "All configuration options should be applied correctly"
  }

  assert {
    condition     = length(aws_elasticache_replication_group.this.log_delivery_configuration) == 2
    error_message = "Multiple log delivery configurations should be supported"
  }

  assert {
    condition     = length(aws_elasticache_parameter_group.this[0].parameter) == 3
    error_message = "Multiple parameters should be configured"
  }
}

run "cluster_mode_disabled_explicitly" {
  command = plan

  variables {
    # Traditional replication group (cluster mode disabled)
    num_node_groups            = null
    replicas_per_node_group    = null
    number_cache_clusters      = 3
    automatic_failover_enabled = true
  }

  assert {
    condition     = aws_elasticache_replication_group.this.num_cache_clusters == 3
    error_message = "Should support traditional replication group mode"
  }
}

run "cluster_mode_enabled_explicitly" {
  command = plan

  variables {
    # Cluster mode enabled
    num_node_groups            = 2
    replicas_per_node_group    = 1
    number_cache_clusters      = null
    automatic_failover_enabled = true
  }

  assert {
    condition     = aws_elasticache_replication_group.this.num_node_groups == 2
    error_message = "Should support cluster mode enabled"
  }
}

run "single_node_cluster" {
  command = plan

  variables {
    number_cache_clusters      = 1
    automatic_failover_enabled = false
    multi_az_enabled           = false
  }

  assert {
    condition     = aws_elasticache_replication_group.this.num_cache_clusters == 1
    error_message = "Should support single node configuration"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.automatic_failover_enabled == false
    error_message = "Automatic failover should be disabled for single node"
  }
}

run "valkey_engine_configuration" {
  command = plan

  variables {
    engine = "valkey"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.engine == "valkey"
    error_message = "Should support valkey engine"
  }
}

run "zero_snapshot_retention" {
  command = plan

  variables {
    snapshot_retention_limit = 0
  }

  assert {
    condition     = aws_elasticache_replication_group.this.snapshot_retention_limit == 0
    error_message = "Should support disabling snapshots with zero retention"
  }
}

run "null_optional_values" {
  command = plan

  variables {
    maintenance_window     = null
    snapshot_window        = null
    notification_topic_arn = null
    port                   = null
    subnet_group_name      = null
    availability_zones     = null
  }

  # This test just validates that the configuration is syntactically valid with null values
  # No assertion needed - if the plan succeeds, null values are handled correctly
}

run "special_characters_in_descriptions" {
  command = plan

  variables {
    replication_group_description = "Test cluster with special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"
    parameter_group = {
      name        = "test-special-chars-pg"
      family      = "redis7.x"
      description = "Parameter group with special characters: !@#$%^&*()"
      parameters  = []
    }
  }

  assert {
    condition     = aws_elasticache_replication_group.this.description != null
    error_message = "Should handle special characters in descriptions"
  }
}

run "reset_password_edge_cases" {
  command = plan

  variables {
    transit_encryption_enabled = true
    reset_password             = "" # Empty string
  }

  # This test validates that empty string reset_password doesn't cause errors
  # No assertion needed - if the plan succeeds, empty string is handled correctly
}
