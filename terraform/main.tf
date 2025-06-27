
provider "aws" {
  region = var.region
  default_tags {
    tags = var.default_tags_tf
  }
}

provider "random" {}

resource "aws_elasticache_parameter_group" "this" {
  count       = var.parameter_group != null ? 1 : 0
  name        = var.parameter_group.name
  family      = var.parameter_group.family
  description = var.parameter_group.description
  tags        = var.tags

  dynamic "parameter" {
    for_each = var.parameter_group.parameters
    content {
      name  = parameter.value.name
      value = parameter.value.value
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "random_password" "this" {
  count   = var.transit_encryption_enabled ? 1 : 0
  length  = 20
  special = true
  keepers = coalesce(var.reset_password, false) ? {
    reset_password = var.reset_password
  } : null
  override_special = "!&#$^<>-"
}

resource "aws_elasticache_replication_group" "this" {
  apply_immediately           = var.apply_immediately
  at_rest_encryption_enabled  = var.at_rest_encryption_enabled
  auth_token                  = var.transit_encryption_enabled ? random_password.this[0].result : null
  auth_token_update_strategy  = "SET"
  automatic_failover_enabled  = var.automatic_failover_enabled
  description                 = var.replication_group_description
  engine                      = var.engine
  engine_version              = var.engine_version
  maintenance_window          = var.maintenance_window
  multi_az_enabled            = var.multi_az_enabled
  node_type                   = var.node_type
  notification_topic_arn      = var.notification_topic_arn
  num_cache_clusters          = var.number_cache_clusters
  num_node_groups             = var.num_node_groups
  parameter_group_name        = length(aws_elasticache_parameter_group.this) > 0 ? aws_elasticache_parameter_group.this[0].name : var.parameter_group_name
  port                        = var.port
  preferred_cache_cluster_azs = var.availability_zones
  replicas_per_node_group     = var.replicas_per_node_group
  replication_group_id        = var.replication_group_id
  security_group_ids          = var.security_group_ids
  snapshot_retention_limit    = var.snapshot_retention_limit
  snapshot_window             = var.snapshot_window
  subnet_group_name           = var.subnet_group_name
  tags                        = var.tags
  transit_encryption_enabled  = var.transit_encryption_enabled
  transit_encryption_mode     = var.transit_encryption_mode

  dynamic "log_delivery_configuration" {
    for_each = var.log_delivery_configuration
    content {
      destination      = log_delivery_configuration.value.destination
      destination_type = log_delivery_configuration.value.destination_type
      log_format       = log_delivery_configuration.value.log_format
      log_type         = log_delivery_configuration.value.log_type
    }
  }

  depends_on = [aws_elasticache_parameter_group.this]
}
