#!/usr/bin/env python

import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check(outputs: Mapping) -> bool:
    """Check function."""
    for key in outputs:
        if key.endswith("__db_port"):
            # port output found
            return True
    logger.error("Port output not found.")
    return False


def main() -> None:
    """Main function."""
    logger.info("Running post checks ...")
    if len(sys.argv) != 2:  # noqa: PLR2004
        logger.error("Usage: post_checks.py <output_json>")
        sys.exit(1)

    output_json = Path(sys.argv[1])
    if not check(json.loads(output_json.read_text())):
        sys.exit(1)
    logger.info("Post checks completed.")


if __name__ == "__main__":
    main()
