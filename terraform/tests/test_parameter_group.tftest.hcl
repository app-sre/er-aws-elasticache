# Tests for ElastiCache Parameter Group resource
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

run "parameter_group_not_created_when_null" {
  command = plan

  variables {
    parameter_group = null
  }

  assert {
    condition     = length(aws_elasticache_parameter_group.this) == 0
    error_message = "Parameter group should not be created when variable is null"
  }
}

run "parameter_group_created_with_basic_config" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-parameter-group"
      family      = "redis7.x"
      description = "Test parameter group for Redis 7.x"
      parameters  = []
    }
  }

  assert {
    condition     = length(aws_elasticache_parameter_group.this) == 1
    error_message = "Parameter group should be created when configured"
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].name == "test-parameter-group"
    error_message = "Parameter group name should match input"
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].family == "redis7.x"
    error_message = "Parameter group family should match input"
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].description == "Test parameter group for Redis 7.x"
    error_message = "Parameter group description should match input"
  }
}

run "parameter_group_with_parameters" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-parameter-group-with-params"
      family      = "redis7.x"
      description = "Test parameter group with custom parameters"
      parameters = [
        {
          name  = "maxmemory-policy"
          value = "allkeys-lru"
        },
        {
          name  = "timeout"
          value = "300"
        },
        {
          name  = "tcp-keepalive"
          value = "60"
        }
      ]
    }
  }

  assert {
    condition     = length(aws_elasticache_parameter_group.this[0].parameter) == 3
    error_message = "Parameter group should have 3 parameters configured"
  }

}

run "parameter_group_tags_applied" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-parameter-group-tags"
      family      = "redis7.x"
      description = "Test parameter group with tags"
      parameters  = []
    }
    tags = {
      Environment = "test"
      Component   = "elasticache"
      Team        = "platform"
    }
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].tags["Environment"] == "test"
    error_message = "Parameter group should inherit tags from variable"
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].tags["Component"] == "elasticache"
    error_message = "Parameter group should have Component tag"
  }
}

run "replication_group_uses_custom_parameter_group" {
  command = plan

  variables {
    parameter_group = {
      name        = "custom-parameter-group"
      family      = "redis7.x"
      description = "Custom parameter group"
      parameters  = []
    }
  }

  assert {
    condition     = aws_elasticache_replication_group.this.parameter_group_name == "custom-parameter-group"
    error_message = "Replication group should use custom parameter group when created"
  }
}

run "replication_group_uses_external_parameter_group" {
  command = plan

  variables {
    parameter_group      = null
    parameter_group_name = "external-parameter-group"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.parameter_group_name == "external-parameter-group"
    error_message = "Replication group should use external parameter group when specified"
  }

  assert {
    condition     = length(aws_elasticache_parameter_group.this) == 0
    error_message = "No parameter group should be created when using external group"
  }
}

run "parameter_group_different_families" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-redis6-parameter-group"
      family      = "redis6.x"
      description = "Test parameter group for Redis 6.x"
      parameters = [
        {
          name  = "maxmemory-policy"
          value = "volatile-lru"
        }
      ]
    }
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].family == "redis6.x"
    error_message = "Parameter group should support different Redis families"
  }
}
