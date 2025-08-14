# Comprehensive tests for random password generation
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

run "password_not_created_when_encryption_disabled" {
  command = plan

  variables {
    transit_encryption_enabled = false
  }

  assert {
    condition     = length(random_password.this) == 0
    error_message = "Random password should not be created when transit encryption is disabled"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token == null
    error_message = "Auth token should be null when transit encryption is disabled"
  }
}

run "password_created_when_encryption_enabled" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  assert {
    condition     = length(random_password.this) == 1
    error_message = "Random password should be created when transit encryption is enabled"
  }

  assert {
    condition     = random_password.this[0].length == 20
    error_message = "Random password should be 20 characters long"
  }

  assert {
    condition     = random_password.this[0].special == true
    error_message = "Random password should include special characters"
  }

  assert {
    condition     = random_password.this[0].override_special == "!&#$^<>-"
    error_message = "Random password should use correct special character set"
  }
}

run "password_auth_token_integration" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token_update_strategy == "SET"
    error_message = "Auth token update strategy should be SET when transit encryption is enabled"
  }
}

run "password_reset_functionality" {
  command = plan

  variables {
    transit_encryption_enabled = true
    reset_password             = "reset-trigger-123"
  }

  assert {
    condition     = random_password.this[0].keepers["reset_password"] == "reset-trigger-123"
    error_message = "Password should include reset trigger in keepers when reset_password is provided"
  }
}

run "password_no_reset_when_empty_string" {
  command = plan

  variables {
    transit_encryption_enabled = true
    reset_password             = ""
  }

  assert {
    condition     = random_password.this[0].keepers == null
    error_message = "Password keepers should be null when reset_password is empty string"
  }
}

run "password_no_reset_when_null" {
  command = plan

  variables {
    transit_encryption_enabled = true
    reset_password             = null
  }

  assert {
    condition     = random_password.this[0].keepers == null
    error_message = "Password keepers should be null when reset_password is null"
  }
}

run "password_characteristics_validation" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  # Verify password configuration meets security requirements
  assert {
    condition     = random_password.this[0].length >= 16
    error_message = "Password should be at least 16 characters for security"
  }

  assert {
    condition     = random_password.this[0].special == true
    error_message = "Password should include special characters for complexity"
  }

  # Verify override_special excludes problematic characters
  assert {
    condition     = !contains(split("", random_password.this[0].override_special), "\"")
    error_message = "Password special characters should not include quotes to avoid parsing issues"
  }

  assert {
    condition     = !contains(split("", random_password.this[0].override_special), "'")
    error_message = "Password special characters should not include single quotes"
  }
}

run "password_integration_with_auth_strategy" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  # When transit encryption is enabled, verify the complete auth setup
  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled == true
    error_message = "Transit encryption should be enabled when password is generated"
  }

  assert {
    condition     = aws_elasticache_replication_group.this.auth_token_update_strategy == "SET"
    error_message = "Auth token update strategy should be properly configured"
  }
}

