#!/usr/bin/env python

import json
import logging
import os
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
    output_json_path = os.environ.get("OUTPUTS_FILE")
    if not output_json_path:
        logger.error("PLAN_FILE_JSON environment variable not set")
        sys.exit(1)

    output_json = Path(output_json_path)
    if not check(json.loads(output_json.read_text())):
        sys.exit(1)
    logger.info("Post checks completed.")


if __name__ == "__main__":
    main()
