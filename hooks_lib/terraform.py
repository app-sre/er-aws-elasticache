import logging
import subprocess  # noqa: S404
from collections.abc import Sequence

from .env import Env

logger = logging.getLogger(__name__)


def tf_run(args: Sequence[str], *, dry_run: bool | None = None) -> str:
    """Run a terraform command."""
    args = [*Env.TERRAFORM_CMD.split(), *args]
    dry_run = dry_run if dry_run is not None else Env.DRY_RUN
    if dry_run:
        logger.debug(f"cmd: {' '.join(args)}")
        return ""

    try:
        cmd = subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.exception(e.stdout)
        logger.exception(e.stderr)
        raise
    return cmd.stdout
