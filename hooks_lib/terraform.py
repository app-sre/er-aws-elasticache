import logging
import subprocess  # noqa: S404
import sys
from collections.abc import Sequence

from .env import DRY_RUN, TERRAFORM_CMD

logger = logging.getLogger(__name__)


def tf_run(args: Sequence[str], *, dry_run: bool = DRY_RUN) -> str:
    """Run a terraform command."""
    args = [*TERRAFORM_CMD.split(), *args]
    if dry_run:
        logger.debug(f"cmd: {' '.join(args)}")
        return ""

    cmd = subprocess.run(args, capture_output=True, text=True, check=False)
    if cmd.returncode != 0:
        logger.error(cmd.stdout)
        logger.error(cmd.stderr)
        sys.exit(1)
    return cmd.stdout
