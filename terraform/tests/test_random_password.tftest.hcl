
# Basic test for random password generation
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

run "password_exists" {
  command = plan

  variables {
    transit_encryption_enabled = true
  }

  assert {
    condition     = length(random_password.this) == 1
    error_message = "Random password should be generated when transit encryption is enabled"
  }

  assert {
    condition     = random_password.this[0].length == 20
    error_message = "Random password should be 20 characters long"
  }
}
