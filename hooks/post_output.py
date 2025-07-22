#!/usr/bin/env python

import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

from external_resources_io.config import Config
from external_resources_io.log import setup_logging

logger = logging.getLogger(__name__)


def check(outputs: Mapping) -> bool:
    """Check function."""
    for key in outputs:
        if key == "db_port":
            # port output found
            return True
    logger.error("db_port output not found.")
    return False


def main() -> None:
    """Main function."""
    logger.info("Running post checks ...")
    output_json = Path(Config().outputs_file)
    if not check(json.loads(output_json.read_text(encoding="utf-8"))):
        sys.exit(1)
    logger.info("Post checks completed.")


if __name__ == "__main__":
    setup_logging()
    main()
