#!/usr/bin/env python

import logging
import sys
from datetime import UTC, timedelta
from datetime import datetime as dt

from external_resources_io.config import Action, Config
from external_resources_io.input import parse_model, read_input_from_file
from external_resources_io.log import setup_logging
from external_resources_io.terraform import Action as PlanAction
from external_resources_io.terraform import TerraformJsonPlanParser

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks.pre_plan import (
    AUTH_TOKEN_ROTATION_MARKER_ADDRESS,
    RANDOM_PASSWORD_ADDRESS,
    REPLICATION_GROUP_ADDRESS,
)
from hooks_lib import ServiceUpdatesManager
from hooks_lib.terraform_state import TerraformState, get_current_state

logger = logging.getLogger(__name__)


def staging_complete(
    app_interface_input: AppInterfaceInput, state: TerraformState
) -> bool:
    """Check whether transit encryption / auth token staging has fully reached the tenant's desired state.

    Without this, the default reconcile cadence (~24h) would make a multi-step
    staged transition (see hooks/pre_plan.py) take days instead of a handful of
    quick retries.
    """
    data = app_interface_input.data
    if not data.transit_encryption_enabled:
        return True

    replication_group = state.get_resource(REPLICATION_GROUP_ADDRESS) or {}
    # A missing/unknown mode on an already-encrypted resource is treated as
    # "required" (see compute_transit_encryption_mode/compute_auth_token_update_strategy
    # in hooks/pre_plan.py) - must match that assumption here too, or a legacy
    # resource with no recorded mode would be stuck retrying forever.
    current_mode = replication_group.get("transit_encryption_mode") or "required"
    if data.transit_encryption_mode and current_mode != data.transit_encryption_mode:
        return False

    marker = state.get_resource(AUTH_TOKEN_ROTATION_MARKER_ADDRESS)
    random_password = state.get_resource(RANDOM_PASSWORD_ADDRESS)
    if marker is None and random_password is None:
        # Mode is ready but the auth token has never been introduced at all -
        # still incomplete. A legacy resource that predates this marker would
        # already have random_password.this present (the old code created it
        # unconditionally), so this only matches a genuine first-time case,
        # not an already-stable resource adopting this fix.
        return False

    return not (marker and marker.get("input") != "SET")


def terraform_changes(plan: TerraformJsonPlanParser) -> bool:
    """Check if there are any terraform changes"""
    return any(
        c.change and c.change.actions != [PlanAction.ActionNoop]
        for c in plan.plan.resource_changes
    )


def default_cooldown(environment: str) -> int:
    """Calculate the cooldown period based on the environment name."""
    name = environment.lower().strip()
    match name:
        case _ if "production" in name:
            default = 14
        case _ if "staging" in name or "stage" in name:
            default = 7
        case _:
            default = 5

    return default


def request_retry_if_staging_incomplete(
    app_interface_input: AppInterfaceInput, *, dry_run: bool, action: Action
) -> None:
    """Exit 1 to force a fast reconcile retry while transit encryption / auth token staging is incomplete."""
    if dry_run or action != Action.APPLY:
        return

    if staging_complete(app_interface_input, get_current_state()):
        return

    logger.info(
        "Transit encryption / auth token staging still in progress; "
        "requesting a faster retry."
    )
    sys.exit(1)


def apply_pending_service_update(
    plan: TerraformJsonPlanParser,
    app_interface_input: AppInterfaceInput,
    *,
    dry_run: bool,
) -> None:
    """Ensure that no service updates are in progress."""
    if not app_interface_input.data.service_updates_enabled:
        logger.info("Automatic service updates are disabled.")
        return

    if terraform_changes(plan):
        # do not do anything if there are resource changes
        logger.info("Resource changes detected. Skipping any pending service updates.")
        return

    sumgr = ServiceUpdatesManager(
        app_interface_input.data.replication_group_id, app_interface_input.data.region
    )

    service_updates = sumgr.service_updates(
        service_updates_types=app_interface_input.data.service_updates_types,
        severities=app_interface_input.data.service_updates_severities,
        released_before=dt.now(tz=UTC)
        - timedelta(
            days=app_interface_input.data.service_updates_cooldown_days
            if app_interface_input.data.service_updates_cooldown_days is not None
            else default_cooldown(app_interface_input.data.environment)
        ),
    )

    if not service_updates:
        # No service updates available
        return

    if dry_run:
        logger.info("Service updates available:")
        for su in service_updates:
            logger.info(
                f"Name={su.name} Release Date={su.release_date:%Y-%m-%d} Severity={su.severity}"
            )
        return

    # Apply the most recent service update
    logger.info(f"Applying service update {service_updates[0].name}")
    sumgr.apply_service_update(service_updates[0], wait_for_completion=True)


def main(
    plan: TerraformJsonPlanParser,
    app_interface_input: AppInterfaceInput,
    *,
    dry_run: bool,
    action: Action,
) -> None:
    """Post-apply checks: request a fast retry while staging is incomplete, then handle service updates."""
    request_retry_if_staging_incomplete(
        app_interface_input, dry_run=dry_run, action=action
    )
    apply_pending_service_update(plan, app_interface_input, dry_run=dry_run)


if __name__ == "__main__":
    setup_logging()
    config = Config()
    app_interface_input = parse_model(AppInterfaceInput, read_input_from_file())
    plan = TerraformJsonPlanParser(plan_path=config.plan_file_json)
    main(plan, app_interface_input, dry_run=config.dry_run, action=config.action)
    logger.info("Post apply completed.")
