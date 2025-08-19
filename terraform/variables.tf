variable "apply_immediately" {
  type    = bool
  default = false
}

variable "at_rest_encryption_enabled" {
  type    = bool
  default = null
}

variable "auto_minor_version_upgrade" {
  type    = bool
  default = true
}

variable "automatic_failover_enabled" {
  type    = bool
  default = true
}

variable "availability_zones" {
  type    = list(string)
  default = []
}

variable "default_tags" {
  type    = list(map(any))
  default = []
}

variable "default_tags_tf" {
  type    = map(any)
  default = null
}

variable "engine" {
  type = string
}

variable "engine_version" {
  type = string
}

variable "environment" {
  type    = string
  default = "production"
}

variable "identifier" {
  type = string
}

variable "log_delivery_configuration" {
  type    = list(object({ destination = string, destination_type = string, log_type = string, log_format = string }))
  default = []
}

variable "maintenance_window" {
  type    = string
  default = null
}

variable "multi_az_enabled" {
  type    = bool
  default = null
}

variable "node_type" {
  type = string
}

variable "notification_topic_arn" {
  type    = string
  default = null
}

variable "num_node_groups" {
  type    = number
  default = null
}

variable "number_cache_clusters" {
  type    = number
  default = null
}

variable "output_prefix" {
  type = string
}

variable "output_resource_name" {
  type    = string
  default = null
}

variable "parameter_group" {
  type    = object({ family = string, name = string, description = string, parameters = list(object({ name = string, value = any })) })
  default = null
}

variable "parameter_group_name" {
  type    = string
  default = null
}

variable "port" {
  type    = number
  default = null
}

variable "region" {
  type = string
}

variable "replicas_per_node_group" {
  type    = number
  default = null
}

variable "replication_group_description" {
  type    = string
  default = "elasticache replication group"
}

variable "replication_group_id" {
  type = string
}

variable "reset_password" {
  type    = string
  default = null
}

variable "security_group_ids" {
  type    = list(string)
  default = []
}

variable "service_updates_cooldown_days" {
  type    = number
  default = null
}

variable "service_updates_enabled" {
  type    = bool
  default = true
}

variable "service_updates_severities" {
  type    = list(string)
  default = ["critical", "important"]
}

variable "service_updates_types" {
  type    = list(string)
  default = ["engine-update", "security-update"]
}

variable "snapshot_retention_limit" {
  type    = number
  default = null
}

variable "snapshot_window" {
  type    = string
  default = null
}

variable "subnet_group_name" {
  type    = string
  default = "default"
}

variable "tags" {
  type    = map(any)
  default = null
}

variable "transit_encryption_enabled" {
  type    = bool
  default = null
}

variable "transit_encryption_mode" {
  type    = string
  default = null
}
