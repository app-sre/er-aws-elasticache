#!/usr/bin/env python

import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from external_resources_io.config import Config
from external_resources_io.input import parse_model, read_input_from_file
from external_resources_io.log import setup_logging
from external_resources_io.terraform import (
    Action,
    ResourceChange,
    TerraformJsonPlanParser,
)

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks_lib.aws_api import AWSApi

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EngineInfo:
    """Represents information about an ElastiCache engine.

    Attributes:
        name: The name of the engine (e.g., 'redis', 'memcached').
        family: The parameter group family for the engine version.
        version: The version of the engine.
    """

    name: str
    family: str
    version: str


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
            and (
                Action.ActionCreate in c.change.actions
                or Action.ActionUpdate in c.change.actions
            )
        ]

    @property
    def elasticache_parameter_group_updates(self) -> list[ResourceChange]:
        """Get the elasticache parameter group updates"""
        return [
            c
            for c in self.plan.plan.resource_changes
            if c.type == "aws_elasticache_parameter_group"
            and c.change
            and (
                Action.ActionCreate in c.change.actions
                or Action.ActionUpdate in c.change.actions
            )
        ]

    def get_engine_version(self, engine: str, engine_version: str) -> EngineInfo:
        """Get the engine version and the cache parameter group family"""
        # Get available engine versions from AWS
        response = self.aws_api.client.describe_cache_engine_versions(
            Engine=engine, EngineVersion=engine_version
        )
        if not response.get("CacheEngineVersions"):
            raise ValueError(
                f"Engine version {engine} {engine_version} is not available"
            )

        # Get the cache parameter group family for this engine version
        engine_details = response["CacheEngineVersions"][0]
        return EngineInfo(
            name=engine,
            version=engine_version,
            family=engine_details["CacheParameterGroupFamily"],
        )

    #
    # Replication Group validations
    #
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

    def _validate_subnets(
        self, cache_subnet_group_name: str, availability_zones: Sequence[str]
    ) -> str | None:
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

        # Check that all requested availability zones are covered by the subnet group
        cache_group_subnet_availability_zones = {
            name
            for s in cache_group_subnets
            if (name := s.get("SubnetAvailabilityZone", {}).get("Name"))
        }
        if not cache_group_subnet_availability_zones.issuperset(availability_zones):
            self.errors.append(
                f"Subnet group {cache_subnet_group_name} does not cover all requested availability zones {availability_zones}. "
                f"Available zones: {cache_group_subnet_availability_zones} "
                "If unsure, just remove the availability_zones from your configuration and use the subnet group defaults."
            )

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

    def _validate_cluster_upgrade(
        self,
        before_engine: str,
        after_engine: str,
        before_version: str,
        after_version: str,
        *,
        apply_immediately: bool,
    ) -> None:
        """Validate that apply_immediately is true when engine version changes"""
        # Check if engine or version changed
        engine_changed = before_engine != after_engine
        version_changed = before_version != after_version

        if (engine_changed or version_changed) and not apply_immediately:
            self.errors.append(
                f"apply_immediately must be true when changing engine from "
                f"{before_engine} {before_version} to {after_engine} {after_version}"
            )

    def _validate_apply_immediately_for_encryption_changes(
        self,
        *,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        apply_immediately: bool,
    ) -> None:
        """Validate that apply_immediately is true when encryption-related fields change.

        AWS rejects a ModifyReplicationGroup call touching transit_encryption_enabled
        or transit_encryption_mode without apply_immediately: "Transit encryption
        modification should be called with applied immediately option." AUTH token
        changes have the same requirement per AWS's own AUTH docs.
        """
        changed_fields = [
            field
            for field in (
                "transit_encryption_enabled",
                "transit_encryption_mode",
                "auth_token_update_strategy",
            )
            if before.get(field) != after.get(field)
        ]
        if changed_fields and not apply_immediately:
            self.errors.append(
                f"apply_immediately must be true when changing {', '.join(changed_fields)}"
            )

    def _validate_transit_encryption_mode(
        self,
        *,
        before_transit_encryption_enabled: bool | None,
        after_transit_encryption_enabled: bool | None,
    ) -> None:
        """Validate that transit_encryption_mode is "required" when enabling transit_encryption_enabled.

        This module always introduces an auth token once transit_encryption_enabled
        is true, and AWS only accepts auth token changes once transit_encryption_mode
        is "required" - so "preferred" (or unset) is never a valid final tenant
        target for this transition, only a transient staging value computed by
        hooks/pre_plan.py. Reject it up front instead of leaving the reconciler
        stuck waiting on transit_encryption_mode forever.
        """
        if (
            not before_transit_encryption_enabled
            and after_transit_encryption_enabled
            and self.input.data.transit_encryption_mode != "required"
        ):
            self.errors.append(
                "transit_encryption_mode must be set to 'required' when enabling "
                "transit_encryption_enabled on an existing resource"
            )

    def _validate_transit_encryption_engine_support(
        self,
        *,
        before_transit_encryption_enabled: bool | None,
        after_transit_encryption_enabled: bool | None,
        actions: Sequence[Action],
        engine_info: EngineInfo,
    ) -> None:
        """Block enabling transit_encryption_enabled when it would replace the cluster.

        Rather than hardcoding AWS's minimum engine version for enabling
        transit encryption in-place (a number that could drift, or need
        revisiting if this module ever supports other engines/versions),
        defer to the pinned Terraform AWS provider's own decision: it already
        knows the real threshold and plans a replace (ActionDelete alongside
        ActionCreate) instead of an in-place update whenever the engine/version
        doesn't support this ModifyReplicationGroup call. If Terraform would
        replace it, block outright - that means destroy + recreate, destroying
        all data - rather than relying on a tenant noticing a `-/+` in a plan
        diff before approving it.
        """
        if before_transit_encryption_enabled or not after_transit_encryption_enabled:
            return  # not the no-auth -> auth enabling transition
        if Action.ActionDelete not in actions:
            return  # Terraform can apply this in place; supported
        self.errors.append(
            "Enabling transit_encryption_enabled on this resource "
            f"({engine_info.name} {engine_info.version}) would replace the "
            "cluster (destroy and recreate), destroying all data. Upgrade the "
            "engine first, then enable encryption as a separate, later change."
        )

    def _validate_replication_group(
        self,
        replication_group_id: str,
        subnet_group_name: str,
        security_groups: Sequence[str],
        availability_zones: Sequence[str],
    ) -> None:
        """Validate a single replication group change"""
        # Only validate replication group ID for new resources
        self._validate_replication_group_id(replication_group_id)

        if vpc_id := self._validate_subnets(
            cache_subnet_group_name=subnet_group_name,
            availability_zones=availability_zones,
        ):
            self._validate_security_groups(
                security_groups=security_groups, vpc_id=vpc_id
            )

    #
    # Parameter Group validations
    #
    def _validate_parameter_group_name(self, name: str) -> None:
        logger.info(f"Validating Elasticache parameter group {name}")
        try:
            self.aws_api.client.describe_cache_parameters(CacheParameterGroupName=name)
            self.errors.append(f"Parameter group {name} already exists!")
        except self.aws_api.client.exceptions.CacheParameterGroupNotFoundFault:
            pass

    def _validate_parameter_group_family(
        self, engine_info: EngineInfo, family: str
    ) -> None:
        """Validate that parameter group family matches engine version using AWS API"""
        logger.info(
            f"Validating parameter group family {family} for {engine_info.name} {engine_info.version}"
        )
        if family != engine_info.family:
            self.errors.append(
                f"Parameter group family '{family}' does not match engine {engine_info.name} {engine_info.version}. "
                f"Expected: {engine_info.family}"
            )

    def validate(self) -> bool:
        """Validate method"""
        engine_info = None
        for change in self.elasticache_replication_group_updates:
            assert change.change  # mypy
            assert change.change.after  # mypy

            engine_info = self.get_engine_version(
                engine=change.change.after["engine"],
                engine_version=change.change.after["engine_version"],
            )

            if Action.ActionCreate in change.change.actions:
                self._validate_replication_group(
                    replication_group_id=change.change.after["replication_group_id"],
                    subnet_group_name=change.change.after["subnet_group_name"],
                    security_groups=change.change.after["security_group_ids"],
                    availability_zones=change.change.after.get(
                        "preferred_cache_cluster_azs", []
                    ),
                )

            if change.change.before is not None:
                # Existing resource - whether Terraform plans this as an
                # in-place update or a replace (older engines force a replace
                # for a transit_encryption_enabled change), so this must not
                # be gated on Action.ActionUpdate alone.
                self._validate_transit_encryption_engine_support(
                    before_transit_encryption_enabled=change.change.before.get(
                        "transit_encryption_enabled"
                    ),
                    after_transit_encryption_enabled=change.change.after.get(
                        "transit_encryption_enabled"
                    ),
                    actions=change.change.actions,
                    engine_info=engine_info,
                )

            # Run validation for version changes
            if Action.ActionUpdate in change.change.actions:
                assert change.change.before  # mypy
                self._validate_cluster_upgrade(
                    before_engine=change.change.before.get("engine"),
                    after_engine=change.change.after.get("engine"),
                    before_version=change.change.before.get("engine_version"),
                    after_version=change.change.after.get("engine_version"),
                    apply_immediately=change.change.after.get(
                        "apply_immediately", False
                    ),
                )
                self._validate_apply_immediately_for_encryption_changes(
                    before=change.change.before,
                    after=change.change.after,
                    apply_immediately=change.change.after.get(
                        "apply_immediately", False
                    ),
                )
                self._validate_transit_encryption_mode(
                    before_transit_encryption_enabled=change.change.before.get(
                        "transit_encryption_enabled"
                    ),
                    after_transit_encryption_enabled=change.change.after.get(
                        "transit_encryption_enabled"
                    ),
                )

        for change in self.elasticache_parameter_group_updates:
            assert change.change  # mypy
            assert change.change.after  # mypy

            if Action.ActionCreate in change.change.actions:
                self._validate_parameter_group_name(name=change.name)
            if engine_info and engine_info.family:
                # Validate parameter group family matches engine version
                self._validate_parameter_group_family(
                    engine_info, change.change.after["family"]
                )

        return not self.errors


if __name__ == "__main__":
    setup_logging()
    app_interface_input = parse_model(AppInterfaceInput, read_input_from_file())
    logger.info("Running Elasticache terraform plan validation")
    plan = TerraformJsonPlanParser(plan_path=Config().plan_file_json)
    validator = ElasticachePlanValidator(plan, app_interface_input)
    if not validator.validate():
        logger.error(validator.errors)
        sys.exit(1)

    logger.info("Validation ended succesfully")
