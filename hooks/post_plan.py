#!/usr/bin/env python

import logging
import sys
from collections.abc import Sequence

from external_resources_io.input import parse_model, read_input_from_file
from external_resources_io.terraform import (
    Action,
    ResourceChange,
    TerraformJsonPlanParser,
)

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks_lib.aws_api import AWSApi
from hooks_lib.env import PLAN_FILE_JSON
from hooks_lib.log import setup_logging

logger = logging.getLogger(__name__)


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
    setup_logging()
    app_interface_input = parse_model(AppInterfaceInput, read_input_from_file())
    logger.info("Running Elasticache terraform plan validation")
    plan = TerraformJsonPlanParser(plan_path=PLAN_FILE_JSON)
    validator = ElasticachePlanValidator(plan, app_interface_input)
    if not validator.validate():
        logger.error(validator.errors)
        sys.exit(1)

    logger.info("Validation ended succesfully")
