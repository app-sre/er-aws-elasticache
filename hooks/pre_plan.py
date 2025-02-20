#!/usr/bin/env python

import logging
import subprocess  # noqa: S404
import sys
from collections.abc import Sequence

from external_resources_io.config import Config
from external_resources_io.log import setup_logging
from external_resources_io.terraform import terraform_run

logger = logging.getLogger(__name__)


def migrate_resources(resources: Sequence[str]) -> bool:
    """Migrate terraform resources."""
    changes = False
    for resource in resources:
        resource_class, *_, resource_id = resource.split(".")
        if resource_id.startswith("this"):
            # Skip resources that are already migrated
            continue

        new_resource = (
            f"{resource_class}.this[0]"
            if resource_class in {"aws_elasticache_parameter_group", "random_password"}
            else f"{resource_class}.this"
        )
        logger.info(f"Migrate resource: {resource} -> {new_resource}")
        terraform_run(["state", "mv", resource, new_resource])
        changes = True
    return changes


def main() -> None:
    """Run terraform migrations."""
    if Config().action == "delete":
        # do nothing
        return

    logger.info("Running CDKTF -> Terraform HCL migration ...")
    try:
        resources = terraform_run(["state", "list"], dry_run=False).splitlines()
    except subprocess.CalledProcessError:
        # not state file found
        logger.info("No state file found. Skipping migration.")
        return

    changes = migrate_resources(resources=resources)
    if not changes:
        # nothing to migrate. good.
        logger.info("No resources to migrate.")
        return

    # The ERv2 run must exit here because further steps may produce incorrect outputs or results!
    logger.info("Migration complete. Triggering a restart of the job!")
    sys.exit(1)


if __name__ == "__main__":
    setup_logging()
    main()
