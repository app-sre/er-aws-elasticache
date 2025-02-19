#!/usr/bin/env python

import logging
import sys

from external_resources_io.input import parse_model, read_input_from_file

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks_lib import ServiceUpdatesManager
from hooks_lib.log import setup_logging

logger = logging.getLogger(__name__)


def main(app_interface_input: AppInterfaceInput) -> None:
    """Ensure that no service updates are in progress."""
    sumgr = ServiceUpdatesManager(
        app_interface_input.data.replication_group_id, app_interface_input.data.region
    )

    if sumgr.update_in_progress:
        logger.error(
            f"A service update is in progress for replication group {sumgr.replication_group_id}"
        )
        sys.exit(1)

    logger.info("Pre checks completed.")


if __name__ == "__main__":
    setup_logging()
    app_interface_input = parse_model(AppInterfaceInput, read_input_from_file())
    main(app_interface_input)
