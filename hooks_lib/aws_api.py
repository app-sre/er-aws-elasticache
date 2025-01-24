import logging
import operator
from collections.abc import Mapping, Sequence
from typing import Any

from boto3 import Session
from botocore.config import Config
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.type_defs import SecurityGroupTypeDef
from mypy_boto3_ec2.type_defs import SubnetTypeDef as EC2SubnetTypeDef
from mypy_boto3_elasticache.client import ElastiCacheClient
from mypy_boto3_elasticache.literals import UpdateActionStatusType
from mypy_boto3_elasticache.type_defs import (
    ProcessedUpdateActionTypeDef,
    UpdateActionTypeDef,
)
from mypy_boto3_elasticache.type_defs import (
    SubnetTypeDef as ElasticacheSubnetTypeDef,
)

logger = logging.getLogger(__name__)


class AWSApi:
    """AWS Api Class"""

    def __init__(self, config_options: Mapping[str, Any]) -> None:
        self.session = Session()
        self.config = Config(**config_options)

    @property
    def client(self) -> ElastiCacheClient:
        """Gets a boto client"""
        return self.session.client("elasticache", config=self.config)

    @property
    def ec2_client(self) -> EC2Client:
        """Gets a boto client"""
        return self.session.client("ec2", config=self.config)

    def get_cache_group_subnets(
        self, cache_subnet_group_name: str
    ) -> list[ElasticacheSubnetTypeDef]:
        """Get the Elasticache subnet group"""
        data = self.client.describe_cache_subnet_groups(
            CacheSubnetGroupName=cache_subnet_group_name,
        )["CacheSubnetGroups"]
        if not data:
            raise ValueError(f"Cache subnet group {cache_subnet_group_name} not found")
        return data[0]["Subnets"]

    def get_subnets(self, subnets: Sequence[str]) -> list[EC2SubnetTypeDef]:
        """Get the subnet"""
        data = self.ec2_client.describe_subnets(
            SubnetIds=subnets,
        )
        return data["Subnets"]

    def get_security_groups(
        self, security_groups: Sequence[str]
    ) -> list[SecurityGroupTypeDef]:
        """Get the subnet"""
        data = self.ec2_client.describe_security_groups(
            GroupIds=security_groups,
        )
        return data["SecurityGroups"]

    def get_service_updates(
        self,
        replication_group_id: str,
        status: Sequence[UpdateActionStatusType] | None = None,
    ) -> list[UpdateActionTypeDef]:
        """Return a list of service updates for a replication group ordered by release date (most recent first)."""
        data = self.client.describe_update_actions(
            ReplicationGroupIds=[replication_group_id],
            ServiceUpdateStatus=["available"],
        )
        return sorted(
            [
                i
                for i in data["UpdateActions"]
                # Filter out updates that are not in the desired status
                if not status or i["UpdateActionStatus"] in status
            ],
            key=operator.itemgetter("ServiceUpdateReleaseDate"),
            reverse=True,
        )

    def batch_apply_service_updates(
        self, replication_group_id: str, service_update_name: str
    ) -> ProcessedUpdateActionTypeDef:
        """Apply a service update to a replication group."""
        data = self.client.batch_apply_update_action(
            ReplicationGroupIds=[replication_group_id],
            ServiceUpdateName=service_update_name,
        )
        if data["UnprocessedUpdateActions"]:
            for uaction in data["UnprocessedUpdateActions"]:
                logger.error(uaction)
            raise ValueError("Failed to apply service update")

        if not data["ProcessedUpdateActions"]:
            raise ValueError("Failed to apply service update")

        if len(data["ProcessedUpdateActions"]) != 1:
            for action in data["ProcessedUpdateActions"]:
                logger.error(action)
            raise ValueError("Something went wrong: Multiple service updates applied")

        return data["ProcessedUpdateActions"][0]
