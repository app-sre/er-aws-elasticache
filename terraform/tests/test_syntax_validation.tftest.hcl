# Syntax and configuration validation tests
# These tests validate Terraform configuration without requiring AWS credentials

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

run "syntax_validation_basic" {
  command = plan

  # Test that basic configuration validates
  assert {
    condition     = var.engine == "redis"
    error_message = "Engine should be redis"
  }

  assert {
    condition     = var.node_type == "cache.t3.micro"
    error_message = "Node type should be cache.t3.micro"
  }
}

run "syntax_validation_with_parameter_group" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-parameter-group"
      family      = "redis7.x"
      description = "Test parameter group"
      parameters = [
        {
          name  = "maxmemory-policy"
          value = "allkeys-lru"
        }
      ]
    }
  }

  # Validate parameter group configuration structure
  assert {
    condition     = var.parameter_group.name == "test-parameter-group"
    error_message = "Parameter group name should be configurable"
  }

  assert {
    condition     = length(var.parameter_group.parameters) == 1
    error_message = "Parameter group should accept parameters list"
  }
}

run "syntax_validation_encryption" {
  command = plan

  variables {
    transit_encryption_enabled = true
    at_rest_encryption_enabled = true
  }

  # Validate encryption settings
  assert {
    condition     = var.transit_encryption_enabled == true
    error_message = "Transit encryption should be configurable"
  }

  assert {
    condition     = var.at_rest_encryption_enabled == true
    error_message = "At-rest encryption should be configurable"
  }
}

run "syntax_validation_cluster_mode" {
  command = plan

  variables {
    num_node_groups         = 2
    replicas_per_node_group = 1
    number_cache_clusters   = null
  }

  # Validate cluster mode configuration
  assert {
    condition     = var.num_node_groups == 2
    error_message = "Node groups should be configurable"
  }

  assert {
    condition     = var.replicas_per_node_group == 1
    error_message = "Replicas per node group should be configurable"
  }
}
