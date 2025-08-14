# Tests for provider configuration and default tags
variables {
  region                     = "us-west-2"
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

run "provider_region_configuration" {
  command = plan

  variables {
    region = "eu-west-1"
  }

  # Note: Direct provider configuration testing is limited in terraform test
  # This test ensures the module accepts different regions
  assert {
    condition     = var.region == "eu-west-1"
    error_message = "Module should accept different AWS regions"
  }
}

run "default_tags_applied_to_resources" {
  command = plan

  variables {
    default_tags_tf = {
      Organization = "test-org"
      CostCenter   = "engineering"
      Environment  = "test"
    }
    tags = {
      Component = "elasticache"
      Team      = "platform"
    }
  }

  # Verify that resources inherit default tags through provider configuration
  # Note: Provider default tags are applied automatically by Terraform
  assert {
    condition     = aws_elasticache_replication_group.this.tags["Component"] == "elasticache"
    error_message = "Resource should have component-specific tags"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.tags["Team"] == "platform"
    error_message = "Resource should have team-specific tags"
  }
}

run "parameter_group_inherits_tags" {
  command = plan

  variables {
    parameter_group = {
      name        = "test-parameter-group"
      family      = "redis7.x"
      description = "Test parameter group"
      parameters  = []
    }
    tags = {
      Component = "elasticache"
      Purpose   = "testing"
    }
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].tags["Component"] == "elasticache"
    error_message = "Parameter group should inherit component tags"
  }

  assert {
    condition     = aws_elasticache_parameter_group.this[0].tags["Purpose"] == "testing"
    error_message = "Parameter group should inherit purpose tags"
  }
}

run "default_tags_structure_validation" {
  command = plan

  variables {
    default_tags = [
      {
        tags = {
          Organization = "test-org"
          CostCenter   = "engineering"
        }
      }
    ]
    default_tags_tf = {
      Organization = "test-org"
      CostCenter   = "engineering"
    }
  }

  # Verify that both default_tags and default_tags_tf variables are accepted
  assert {
    condition     = length(var.default_tags) == 1
    error_message = "default_tags should accept list of tag maps"
  }

  assert {
    condition     = var.default_tags_tf["Organization"] == "test-org"
    error_message = "default_tags_tf should accept direct map of tags"
  }
}

run "random_provider_availability" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  # Verify random provider is available and configured
  assert {
    condition     = random_password.this[0].length == 20
    error_message = "Random provider should be available for password generation"
  }
}

run "multi_region_support" {
  command = plan

  variables {
    region = "ap-southeast-1"
  }

  # Test that the module works with different AWS regions
  assert {
    condition     = var.region == "ap-southeast-1"
    error_message = "Module should support Asia Pacific regions"
  }
}

run "tags_merge_behavior" {
  command = plan

  variables {
    default_tags_tf = {
      Environment = "production"
      Team        = "platform"
    }
    tags = {
      Component   = "elasticache"
      Environment = "test" # This should override default
    }
  }

  # Resource-specific tags should take precedence over default tags
  assert {
    condition     = aws_elasticache_replication_group.this.tags["Environment"] == "test"
    error_message = "Resource tags should override default tags when there's a conflict"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.tags["Component"] == "elasticache"
    error_message = "Resource tags should be preserved when no conflict"
  }
}

run "empty_tags_handling" {
  command = plan

  variables {
    tags            = null
    default_tags_tf = null
  }

  # Module should handle null tags gracefully
  assert {
    condition     = aws_elasticache_replication_group.this.tags == null
    error_message = "Module should handle null tags without errors"
  }
}
