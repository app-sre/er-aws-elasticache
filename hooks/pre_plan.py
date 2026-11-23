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

# terraform_data.auth_token_rotation marker input values, set by main.tf:
# "SET" - steady state, token required
# "ROTATE" - first-ever token introduction applied, auth still optional
# "ROTATE_EXISTING" - a replacement of an already-required token applied
ROTATION_MARKER_HOLDABLE = "ROTATE_EXISTING"


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

    prev_reset_password = ((random_password or {}).get("keepers") or {}).get(
        "reset_password"
    )
    if prev_reset_password != (app_interface_input.data.reset_password or None):
        # tenant requested a new password - restart the rotate/set cycle even
        # if a previous rotation is still pending (marker == "ROTATE"):
        # finalizing that marker with SET now would ask AWS to SET a token it
        # never actually ROTATEd in, since random_password is about to be
        # replaced with a new value in this same apply.
        if marker is not None and marker.get("input") in {
            "ROTATE",
            ROTATION_MARKER_HOLDABLE,
        }:
            logger.warning(
                "reset_password changed while a rotation is still pending"
                " (marker input %r): AWS drops the OLDEST token when a cluster"
                " already carries two - consumers still authenticating with it"
                " will be locked out by this apply, with no SET involved.",
                marker.get("input"),
            )
        return "ROTATE"

    # password unchanged: either finalizing an already-pending rotation (a
    # marker showing ROTATE/ROTATE_EXISTING) or steady-state (marker showing
    # SET or absent) - both cases finalize/stay at SET.
    if (
        marker is not None
        and marker.get("input") == ROTATION_MARKER_HOLDABLE
        and app_interface_input.data.finalize_auth_token_rotation is False
    ):
        # Tenant is holding the rotation open (APPSRE-15766): return "ROTATE"
        # so the config stays identical to the last successful apply. The
        # replication group plans as a no-op (auth_token and
        # auth_token_update_strategy both unchanged), no ModifyReplicationGroup
        # call is made, and BOTH the old and new tokens remain valid while
        # slow-rolling consumers pick up the new one from the output secret.
        # Only a replacement of an already-required token (ROTATE_EXISTING)
        # can be held: a first-time introduction (ROTATE) must finalize, so a
        # stale hold left in the config can never leave the cluster accepting
        # unauthenticated connections indefinitely. In steady state (SET)
        # this branch is also unreachable, so a hold can never introduce a
        # stray ROTATE.
        return "ROTATE"
    return "SET"


def _rotation_replaces_required_token(
    strategy: str | None,
    *,
    marker: dict[str, Any] | None,
    random_password: dict[str, Any] | None,
) -> bool:
    """Whether a ROTATE in this apply replaces an already-required token.

    Written to the auto.tfvars override so terraform_data.auth_token_rotation
    records the scope of the rotation (ROTATE_EXISTING vs ROTATE) alongside
    the strategy - see terraform/transit_encryption_staging.tf.
    """
    if strategy == "SET":
        # A SET (including the create apply, where the strategy variable is
        # SET) means the token in place is required - irrelevant for the
        # marker (it just records SET), but keeps the value truthful.
        return True
    if marker is None:
        # Legacy resource predating the marker: a random_password already in
        # state means a required token was in place (the pre-marker code
        # always applied SET); no random_password means a first-time
        # introduction.
        return random_password is not None
    # The marker reflects the last successful apply: SET (steady state) and
    # ROTATE_EXISTING (pending replacement of a required token) both prove a
    # required token was already in place, while ROTATE means the token
    # currently live is still the first, optional one.
    return marker.get("input") in {"SET", ROTATION_MARKER_HOLDABLE}


def compute_auth_token_rotation_replaces_required_token(
    strategy: str | None, state: TerraformState
) -> bool:
    """Compute auth_token_rotation_replaces_required_token for this run."""
    return _rotation_replaces_required_token(
        strategy,
        marker=state.get_resource(AUTH_TOKEN_ROTATION_MARKER_ADDRESS),
        random_password=state.get_resource(RANDOM_PASSWORD_ADDRESS),
    )


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
            "auth_token_rotation_replaces_required_token": (
                compute_auth_token_rotation_replaces_required_token(
                    auth_token_update_strategy, state
                )
            ),
            "transit_encryption_mode_override": transit_encryption_mode_override,
        }),
        encoding="utf-8",
    )


if __name__ == "__main__":
    setup_logging()
    config = Config()
    if config.action == Action.APPLY:
        main(parse_model(AppInterfaceInput, read_input_from_file()))
