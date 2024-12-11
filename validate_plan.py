import logging
import os
import sys
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from boto3 import Session
from botocore.config import Config
from external_resources_io.input import parse_model, read_input_from_file
from external_resources_io.terraform import (
    Action,
    ResourceChange,
    TerraformJsonPlanParser,
)

if TYPE_CHECKING:
    from mypy_boto3_ec2.client import EC2Client
    from mypy_boto3_ec2.type_defs import SecurityGroupTypeDef
    from mypy_boto3_ec2.type_defs import SubnetTypeDef as EC2SubnetTypeDef
    from mypy_boto3_elasticache.client import ElastiCacheClient
    from mypy_boto3_elasticache.type_defs import (
        SubnetTypeDef as ElasticacheSubnetTypeDef,
    )
else:
    ElastiCacheClient = EC2Client = ElasticacheSubnetTypeDef = EC2SubnetTypeDef = (
        SecurityGroupTypeDef
    ) = object

from er_aws_elasticache.app_interface_input import AppInterfaceInput

logging.basicConfig(level=logging.INFO)
logging.getLogger("botocore").setLevel(logging.ERROR)
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


class ElasticachePlanValidator:
    """The plan validator class"""

    def __init__(
        self, plan: TerraformJsonPlanParser, app_interface_input: AppInterfaceInput
    ) -> None:
        self.plan = plan
        self.input = app_interface_input
        self.aws_api = AWSApi(config_options={"region_name": self.input.data.region})
        self.errors: list[str] = []

    @property
    def elasticache_replication_group_updates(self) -> list[ResourceChange]:
        """Get the elasticache replication group updates"""
        return [
            c
            for c in self.plan.plan.resource_changes
            if c.type == "aws_elasticache_replication_group"
            and c.change
            and c.change.after
            and Action.ActionCreate in c.change.actions
        ]

    @property
    def elasticache_parameter_group_updates(self) -> list[ResourceChange]:
        """Get the elasticache parameter group updates"""
        return [
            c
            for c in self.plan.plan.resource_changes
            if c.type == "aws_elasticache_parameter_group"
            and c.change
            and Action.ActionCreate in c.change.actions
        ]

    def _validate_replication_group_id(self, replication_group_id: str) -> None:
        logger.info(f"Validating Elasticache replication group {replication_group_id}")
        try:
            self.aws_api.client.describe_replication_groups(
                ReplicationGroupId=replication_group_id
            )
            self.errors.append(
                f"Replication group ID {replication_group_id} already exists!"
            )
        except self.aws_api.client.exceptions.ReplicationGroupNotFoundFault:
            pass

    def _validate_subnets(self, cache_subnet_group_name: str) -> str | None:
        logger.info(f"Validating Elasticache subnet group {cache_subnet_group_name}")

        vpc_ids: set[str] = set()
        cache_group_subnets = self.aws_api.get_cache_group_subnets(
            cache_subnet_group_name
        )
        subnets = self.aws_api.get_subnets(
            subnets=[s["SubnetIdentifier"] for s in cache_group_subnets]
        )

        for subnet in subnets:
            if "VpcId" not in subnet:
                self.errors.append(
                    f"VpcId not found for subnet {subnet.get('SubnetId')}"
                )
                continue
            vpc_ids.add(subnet["VpcId"])
        if len(vpc_ids) > 1:
            self.errors.append("All subnets must belong to the same VPC")
        return vpc_ids.pop()

    def _validate_security_groups(
        self, security_groups: Sequence[str], vpc_id: str
    ) -> None:
        logger.info(f"Validating security group {security_groups}")
        data = self.aws_api.get_security_groups(security_groups)
        if missing := set(security_groups).difference({s.get("GroupId") for s in data}):
            self.errors.append(f"Security group(s) {missing} not found")
            return

        for sg in data:
            if sg.get("VpcId") != vpc_id:
                self.errors.append(
                    f"Security group {sg.get('GroupId')} does not belong to the same VPC as the subnets"
                )

    def _validate_parameter_group(self, name: str) -> None:
        logger.info(f"Validating Elasticache parameter group {name}")
        try:
            self.aws_api.client.describe_cache_parameters(CacheParameterGroupName=name)
            self.errors.append(f"Parameter group {name} already exists!")
        except self.aws_api.client.exceptions.CacheParameterGroupNotFoundFault:
            pass

    def validate(self) -> bool:
        """Validate method"""
        for u in self.elasticache_replication_group_updates:
            assert u.change  # mypy
            assert u.change.after  # mypy

            self._validate_replication_group_id(u.change.after["replication_group_id"])

            if vpc_id := self._validate_subnets(
                cache_subnet_group_name=u.change.after["subnet_group_name"]
            ):
                self._validate_security_groups(
                    security_groups=u.change.after["security_group_ids"],
                    vpc_id=vpc_id,
                )
        for u in self.elasticache_parameter_group_updates:
            self._validate_parameter_group(u.name)
        return not self.errors


if __name__ == "__main__":
    app_interface_input = parse_model(
        AppInterfaceInput,
        read_input_from_file(
            file_path=os.environ.get("ER_INPUT_FILE", "/inputs/input.json"),
        ),
    )
    logger.info("Running Elasticache terraform plan validation")
    plan = TerraformJsonPlanParser(plan_path=sys.argv[1])
    validator = ElasticachePlanValidator(plan, app_interface_input)
    if not validator.validate():
        logger.error(validator.errors)
        sys.exit(1)

    logger.info("Validation ended succesfully")
