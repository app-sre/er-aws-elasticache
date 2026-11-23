# auth_token_update_strategy defaults to "SET", matching AWS's behavior for brand
# new replication groups (the attribute is ignored during create). Introducing or
# rotating a token on an EXISTING resource needs ROTATE before SET is accepted by
# AWS - hooks/pre_plan.py detects that case from live Terraform state and
# overrides this variable via an auto.tfvars.json file for that one run.
#
# transit_encryption_mode_override stages transit_encryption_mode toward the
# tenant's desired value (disabled -> preferred -> required) the same way - AWS
# requires "preferred" in the same call that first enables
# transit_encryption_enabled, and only accepts "required" as a follow-up once
# "preferred" is already live.
#
# Both variables are deliberately NOT part of ElasticacheData/variables.tf: any
# key present in terraform.tfvars.json (generated from ElasticacheData) would be
# passed via an explicit -var-file flag, which always wins over an
# auto.tfvars.json override in Terraform's precedence order.
variable "auth_token_update_strategy" {
  type    = string
  default = "SET"
}

variable "transit_encryption_mode_override" {
  type    = string
  default = null
}

# Whether a ROTATE in this apply replaces an already-required token (a genuine
# rotation) or introduces the first-ever token (AUTH enablement). Internal,
# set by hooks/pre_plan.py via the same auto.tfvars.json override.
variable "auth_token_rotation_replaces_required_token" {
  type    = bool
  default = false
}

# Tracks which auth_token_update_strategy was used on the last successful apply,
# so hooks/pre_plan.py can tell "just rotated, needs a follow-up SET" apart from
# "already required" without relying on AWS's read API, which doesn't expose that
# distinction once the operation settles. Only exists once staging has actually
# started (auth_token_update_strategy is non-null), so its presence/absence is
# unambiguous.
#
# The input records the scope of a pending rotation in addition to the strategy:
# "ROTATE" means the first-ever token introduction (auth still optional), while
# "ROTATE_EXISTING" means a replacement of an already-required token. Only the
# latter may be held open via finalize_auth_token_rotation - a first-time
# introduction must always fast-retry to SET, or a stale hold left in the config
# would leave the cluster accepting unauthenticated connections indefinitely.
#
# depends_on is required (this resource has no attribute reference to the
# replication group): without it, Terraform has no ordering constraint between
# the two, and this resource's apply always trivially succeeds (no AWS call).
# If the replication group's ModifyReplicationGroup call failed, this marker
# could still commit, and the next run would trust a false marker.
resource "terraform_data" "auth_token_rotation" {
  count = var.transit_encryption_enabled && var.auth_token_update_strategy != null ? 1 : 0
  input = var.auth_token_update_strategy == "ROTATE" && var.auth_token_rotation_replaces_required_token ? "ROTATE_EXISTING" : var.auth_token_update_strategy

  depends_on = [aws_elasticache_replication_group.this]
}
