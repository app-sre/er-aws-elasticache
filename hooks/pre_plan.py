#!/usr/bin/env python

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from external_resources_io.config import Action, Config
from external_resources_io.input import parse_model, read_input_from_file
from external_resources_io.log import setup_logging

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks_lib.terraform_state import TerraformState, get_current_state

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)

REPLICATION_GROUP_ADDRESS = "aws_elasticache_replication_group.this"
AUTH_TOKEN_ROTATION_MARKER_ADDRESS = "terraform_data.auth_token_rotation[0]"
RANDOM_PASSWORD_ADDRESS = "random_password.this[0]"

AUTO_TFVARS_FILENAME = "transit_encryption_staging.auto.tfvars.json"


def compute_transit_encryption_mode(
    app_interface_input: AppInterfaceInput, state: TerraformState
) -> str | None:
    """Stage transit_encryption_mode toward the tenant's desired value.

    AWS only allows single-step transitions (None/disabled -> preferred ->
    required) and requires "preferred" in the same call that first enables
    transit_encryption_enabled. Unlike auth_token_update_strategy, this can be
    read directly from the replication group's own state - transit_encryption_mode
    isn't subject to the same provider state-migration unreliability, so no
    separate marker is needed.
    """
    desired_mode = app_interface_input.data.transit_encryption_mode
    if desired_mode is None:
        return None

    replication_group = state.get_resource(REPLICATION_GROUP_ADDRESS)
    if replication_group is None:
        return None  # brand-new resource: pass the desired value straight through

    if replication_group.get("transit_encryption_enabled"):
        # Already encrypted. A resource that predates transit_encryption_mode
        # tracking (or was created without it explicitly set) may have no
        # recorded value even though it's already running with a required auth
        # token - assume "required" rather than "preferred" for such a
        # resource, to avoid an unnecessary (and momentarily auth-weakening)
        # step backward to "preferred".
        prev_mode = replication_group.get("transit_encryption_mode") or "required"
    else:
        prev_mode = None  # genuinely never enabled; needs full staging from scratch

    if prev_mode == desired_mode:
        return None  # already there
    if desired_mode == "required" and prev_mode != "preferred":
        return "preferred"  # must land on preferred first
    return desired_mode


def compute_auth_token_update_strategy(
    app_interface_input: AppInterfaceInput, state: TerraformState
) -> str | None:
    """Compute the auth_token_update_strategy required for this reconcile run.

    AWS rejects SET unless a token was already ROTATEd in, but ROTATE alone
    leaves auth optional (both authenticated and passwordless connections work).
    So introducing/rotating an auth token always needs two consecutive applies:
    ROTATE, then SET. describe_replication_groups can't distinguish "optional
    token from ROTATE" from "required token from SET" once settled, so progress
    is tracked via a dedicated terraform_data marker instead of AWS's own API.
    Ref: https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/auth.html

    AWS also rejects any AUTH token operation while transit_encryption_mode is
    "preferred" (confirmed live) - "The AUTH token modification is only
    supported when encryption-in-transit is enabled" - so this is gated on the
    replication group's prior transit_encryption_mode too. A missing/unknown
    mode on an already-encrypted resource is treated as "required" (matches
    this module's pre-existing, unconditional SET-always behavior for
    resources that predate transit_encryption_mode tracking) rather than
    blocking - only a confirmed "preferred" blocks.
    """
    replication_group = state.get_resource(REPLICATION_GROUP_ADDRESS)
    if replication_group is None:
        # brand-new resource: auth_token_update_strategy is not used during
        # create, but must be non-null so auth_token is still sent at creation
        return "SET"
    if not replication_group.get("transit_encryption_enabled"):
        # encryption isn't live yet; auth token blocked until it is
        return None
    if replication_group.get("transit_encryption_mode") == "preferred":
        # AWS blocks any AUTH token operation while mode is merely "preferred"
        return None

    marker = state.get_resource(AUTH_TOKEN_ROTATION_MARKER_ADDRESS)
    random_password = state.get_resource(RANDOM_PASSWORD_ADDRESS)
    return _next_auth_token_update_strategy(
        app_interface_input, marker=marker, random_password=random_password
    )


def _next_auth_token_update_strategy(
    app_interface_input: AppInterfaceInput,
    *,
    marker: dict[str, Any] | None,
    random_password: dict[str, Any] | None,
) -> str:
    """Decide ROTATE vs SET once transit_encryption_mode is confirmed "required"."""
    if marker is None and random_password is None:
        # mode just became required for the first time: neither the marker nor
        # random_password.this has ever been created (both are gated on this
        # same strategy being non-null), so there's nothing to compare against
        # yet - this is unambiguously a first-time introduction
        return "ROTATE"

    if marker and marker.get("input") != "SET":
        # a previous run rotated a new token in; finalize it now
        return "SET"

    prev_reset_password = ((random_password or {}).get("keepers") or {}).get(
        "reset_password"
    )
    if prev_reset_password != (app_interface_input.data.reset_password or None):
        # tenant requested a new password; start a new rotate/set cycle
        return "ROTATE"

    return "SET"


def main(app_interface_input: AppInterfaceInput) -> None:
    """Override auth_token_update_strategy/transit_encryption_mode for this run, if needed."""
    if not app_interface_input.data.transit_encryption_enabled:
        # nothing to stage; main.tf already forces both to null when disabled
        logger.info("Transit encryption disabled, no staging needed.")
        return

    state = get_current_state()
    auth_token_update_strategy = compute_auth_token_update_strategy(
        app_interface_input, state
    )
    transit_encryption_mode_override = compute_transit_encryption_mode(
        app_interface_input, state
    )

    logger.info(
        f"auth_token_update_strategy={auth_token_update_strategy!r}, "
        f"transit_encryption_mode_override={transit_encryption_mode_override!r}"
    )
    output_file = Path(Config().variables_tf_file).parent / AUTO_TFVARS_FILENAME
    output_file.write_text(
        json.dumps({
            "auth_token_update_strategy": auth_token_update_strategy,
            "transit_encryption_mode_override": transit_encryption_mode_override,
        }),
        encoding="utf-8",
    )


if __name__ == "__main__":
    setup_logging()
    config = Config()
    if config.action == Action.APPLY:
        main(parse_model(AppInterfaceInput, read_input_from_file()))
