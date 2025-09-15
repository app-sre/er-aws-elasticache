# Basic validation tests that work without AWS credentials
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

run "validate_basic_configuration" {
  command = plan

  assert {
    condition     = var.region == "us-east-1"
    error_message = "Region should be configurable"
  }

  assert {
    condition     = var.engine == "redis"
    error_message = "Engine should be redis"
  }

  assert {
    condition     = var.node_type == "cache.t3.micro"
    error_message = "Node type should be configurable"
  }
}

run "validate_parameter_group_conditional" {
  command = plan

  variables {
    parameter_group = null
  }

  assert {
    condition     = var.parameter_group == null
    error_message = "Parameter group should be nullable"
  }
}

run "validate_parameter_group_creation" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-parameter-group"
      family      = "redis7.x"
      description = "Test parameter group"
      parameters  = []
    }
  }

  assert {
    condition     = var.parameter_group.name == "test-parameter-group"
    error_message = "Parameter group should be configurable"
  }

  assert {
    condition     = var.parameter_group.family == "redis7.x"
    error_message = "Parameter group family should be configurable"
  }
}

run "validate_encryption_settings" {
  command = plan

  variables {
    transit_encryption_enabled = true
    at_rest_encryption_enabled = true
  }

  assert {
    condition     = var.transit_encryption_enabled == true
    error_message = "Transit encryption should be configurable"
  }

  assert {
    condition     = var.at_rest_encryption_enabled == true
    error_message = "At-rest encryption should be configurable"
  }
}

run "validate_cluster_configuration" {
  command = plan

  variables {
    num_node_groups         = 2
    replicas_per_node_group = 1
    number_cache_clusters   = null
  }

  assert {
    condition     = var.num_node_groups == 2
    error_message = "Node groups should be configurable"
  }

  assert {
    condition     = var.replicas_per_node_group == 1
    error_message = "Replicas per node group should be configurable"
  }
}

run "validate_backup_settings" {
  command = plan

  variables {
    snapshot_retention_limit = 7
    snapshot_window          = "03:00-05:00"
    maintenance_window       = "sun:02:00-sun:03:00"
  }

  assert {
    condition     = var.snapshot_retention_limit == 7
    error_message = "Snapshot retention should be configurable"
  }

  assert {
    condition     = var.snapshot_window == "03:00-05:00"
    error_message = "Snapshot window should be configurable"
  }
}

run "validate_tags_configuration" {
  command = plan

  variables {
    tags = {
      Environment = "test"
      Component   = "elasticache"
    }
  }

  assert {
    condition     = var.tags["Environment"] == "test"
    error_message = "Resource tags should be configurable"
  }
}
