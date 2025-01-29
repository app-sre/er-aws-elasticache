#!/usr/bin/env python


import logging
import os
import sys
from datetime import UTC, timedelta
from datetime import datetime as dt

from external_resources_io.input import (
    parse_model,
    read_input_from_file,
)
from external_resources_io.terraform import (
    Action,
    TerraformJsonPlanParser,
)

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks_lib import ServiceUpdatesManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logging.getLogger("botocore").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


def terraform_changes(plan: TerraformJsonPlanParser) -> bool:
    """Check if there are any terraform changes"""
    return any(
        c.change and c.change.actions != [Action.ActionNoop]
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


def main(
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


if __name__ == "__main__":
    app_interface_input = parse_model(AppInterfaceInput, read_input_from_file())
    plan = TerraformJsonPlanParser(plan_path=sys.argv[1])
    main(
        plan,
        app_interface_input,
        dry_run=os.environ.get("DRY_RUN", "true").lower() == "true",
    )
    logger.info("Post apply completed.")
