import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from hooks_lib.aws_api import AWSApi

logger = logging.getLogger(__name__)


@dataclass
class ServiceUpdate:
    """Service Update Information"""

    name: str
    release_date: datetime
    severity: str
    status: str
    type: str


class ServiceUpdatesManager:
    """This class manages AWS ElastiCache service updates."""

    def __init__(
        self,
        replication_group_id: str,
        region: str,
        aws_api_class: type[AWSApi] = AWSApi,
    ) -> None:
        self.replication_group_id = replication_group_id
        self.aws_api = aws_api_class(config_options={"region_name": region})

    @property
    def update_in_progress(self) -> bool:
        """Check if an update is in progress."""
        return bool(
            self.aws_api.get_service_updates(
                replication_group_id=self.replication_group_id,
                status=["waiting-to-start", "in-progress", "scheduling", "stopping"],
            )
        )

    def service_updates(
        self, severities: Sequence[str], released_before: datetime
    ) -> list[ServiceUpdate]:
        """Get a list of all available service updates ordered by release date (most recent first)."""
        return [
            ServiceUpdate(
                name=u["ServiceUpdateName"],
                release_date=u["ServiceUpdateReleaseDate"],
                severity=u["ServiceUpdateSeverity"],
                status=u["UpdateActionStatus"],
                type=u["ServiceUpdateType"],
            )
            for u in self.aws_api.get_service_updates(
                replication_group_id=self.replication_group_id,
                status=["not-applied", "scheduled", "stopped"],
            )
            if u["ServiceUpdateSeverity"] in severities
            and u["ServiceUpdateReleaseDate"] < released_before
        ]

    def apply_service_update(
        self, service_update: ServiceUpdate, *, wait_for_completion: bool = False
    ) -> None:
        """Apply a service update."""
        if self.update_in_progress:
            raise RuntimeError("An update is already in progress.")

        self.aws_api.batch_apply_service_updates(
            replication_group_id=self.replication_group_id,
            service_update_name=service_update.name,
        )

        if wait_for_completion:
            logger.info("Waiting for service update to complete...")
            while self.update_in_progress:
                print(".", end="", flush=True)  # noqa: T201
                time.sleep(30)
