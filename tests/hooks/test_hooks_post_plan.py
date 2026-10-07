# ruff: file-ignore[private-member-access]
import logging
import runpy
from copy import deepcopy
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from external_resources_io.terraform import (
    Action,
    Change,
    Plan,
    ResourceChange,
    TerraformJsonPlanParser,
)

from er_aws_elasticache.app_interface_input import AppInterfaceInput, ElasticacheData
from hooks.post_plan import ElasticachePlanValidator, EngineInfo

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture


@pytest.fixture
def mock_aws_client() -> MagicMock:
    """Mock AWS ElastiCache client"""
    client = MagicMock()

    # Mock describe_replication_groups
    client.exceptions.ReplicationGroupNotFoundFault = LookupError

    # Mock describe_cache_parameters
    client.exceptions.CacheParameterGroupNotFoundFault = Exception

    # Mock describe_cache_engine_versions
    client.describe_cache_engine_versions.return_value = {
        "CacheEngineVersions": [
            {
                "CacheParameterGroupFamily": "redis7.x",
                "Engine": "redis",
                "EngineVersion": "7.0.7",
            }
        ]
    }

    return client


@pytest.fixture
def mock_aws_api(mock_aws_client: MagicMock) -> Generator[MagicMock]:
    """Mock AWSApi instance"""
    with patch("hooks.post_plan.AWSApi") as mock_aws_api_class:
        aws_api = MagicMock()
        aws_api.client = mock_aws_client
        aws_api.get_node_type_availability_zones.return_value = {
            "us-east-1a",
            "us-east-1b",
        }
        aws_api.get_replication_group_availability_zones.return_value = {
            "us-east-1a",
        }

        # Mock get_cache_group_subnets
        aws_api.get_cache_group_subnets.return_value = [
            {
                "SubnetIdentifier": "subnet-123",
                "SubnetAvailabilityZone": {"Name": "us-east-1a"},
            },
            {
                "SubnetIdentifier": "subnet-456",
                "SubnetAvailabilityZone": {"Name": "us-east-1b"},
            },
        ]

        # Mock get_subnets
        aws_api.get_subnets.return_value = [
            {"SubnetId": "subnet-123", "VpcId": "vpc-123"},
            {"SubnetId": "subnet-456", "VpcId": "vpc-123"},
        ]

        # Mock get_security_groups
        aws_api.get_security_groups.return_value = [
            {"GroupId": "sg-123", "VpcId": "vpc-123"},
            {"GroupId": "sg-456", "VpcId": "vpc-123"},
        ]

        mock_aws_api_class.return_value = aws_api
        yield aws_api


@pytest.fixture
def terraform_plan() -> MagicMock:
    """Mock TerraformJsonPlanParser"""
    plan = MagicMock(spec=TerraformJsonPlanParser)
    plan.plan = MagicMock(spec=Plan)
    plan.plan.resource_changes = []
    return plan


@pytest.fixture
def replication_group_change() -> ResourceChange:
    """Sample replication group resource change"""
    return ResourceChange(
        address="aws_elasticache_replication_group.test",
        mode="managed",
        type="aws_elasticache_replication_group",
        name="test",
        provider_name="registry.terraform.io/hashicorp/aws",
        change=Change(
            actions=[Action.ActionCreate],
            before=None,
            after={
                "replication_group_id": "test-cluster",
                "engine": "redis",
                "engine_version": "7.0.7",
                "node_type": "cache.t4g.micro",
                "subnet_group_name": "test-subnet-group",
                "security_group_ids": ["sg-123", "sg-456"],
                "apply_immediately": True,
            },
            after_unknown=None,
        ),
    )


@pytest.fixture
def replication_group_update(
    replication_group_change: ResourceChange,
) -> ResourceChange:
    """An existing group with unchanged node type and placement."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.after |= {
        "multi_az_enabled": False,
        "num_cache_clusters": 2,
    }
    replication_group_change.change.before = dict(replication_group_change.change.after)
    return replication_group_change


@pytest.fixture
def parameter_group_change() -> ResourceChange:
    """Sample parameter group resource change"""
    return ResourceChange(
        address="aws_elasticache_parameter_group.test",
        mode="managed",
        type="aws_elasticache_parameter_group",
        name="test-pg",
        provider_name="registry.terraform.io/hashicorp/aws",
        change=Change(
            actions=[Action.ActionCreate],
            before=None,
            after={"family": "redis7.x", "name": "test-pg"},
            after_unknown=None,
        ),
    )


@pytest.fixture
def validator(
    terraform_plan: MagicMock,
    ai_input: AppInterfaceInput,
    mock_aws_api: MagicMock,  # ruff: ignore[unused-function-argument]
) -> ElasticachePlanValidator:
    """ElasticachePlanValidator instance"""
    return ElasticachePlanValidator(terraform_plan, ai_input)


def test_engine_info_creation() -> None:
    """EngineInfo: Test model instance creation"""
    engine_info = EngineInfo(name="redis", family="redis7.x", version="7.0.7")

    assert engine_info.name == "redis"
    assert engine_info.family == "redis7.x"
    assert engine_info.version == "7.0.7"


@pytest.mark.parametrize(
    ("name", "family", "version"),
    [
        ("redis", "redis7.x", "7.0.7"),
        ("redis", "redis6.x", "6.2.13"),
    ],
)
def test_engine_info_parametrized(name: str, family: str, version: str) -> None:
    """EngineInfo: Test model creation with different engine types"""
    engine_info = EngineInfo(name=name, family=family, version=version)

    assert engine_info.name == name
    assert engine_info.family == family
    assert engine_info.version == version


def test_validator_initialization(
    validator: ElasticachePlanValidator, ai_input: AppInterfaceInput
) -> None:
    """ElasticachePlanValidator: Test validator initialization"""
    assert validator.input == ai_input
    assert validator.errors == []
    assert validator.aws_api is not None


def test_validator_elasticache_replication_group_updates_empty(
    validator: ElasticachePlanValidator,
) -> None:
    """ElasticachePlanValidator: Test empty replication group updates"""
    assert validator.elasticache_replication_group_updates == []


def test_validator_elasticache_replication_group_updates_with_changes(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
) -> None:
    """ElasticachePlanValidator: Test replication group updates with changes"""
    validator.plan.plan.resource_changes = [replication_group_change]

    updates = validator.elasticache_replication_group_updates
    assert len(updates) == 1
    assert updates[0] == replication_group_change


def test_validator_elasticache_parameter_group_updates_empty(
    validator: ElasticachePlanValidator,
) -> None:
    """ElasticachePlanValidator: Test empty parameter group updates"""
    assert validator.elasticache_parameter_group_updates == []


def test_validator_elasticache_parameter_group_updates_with_changes(
    validator: ElasticachePlanValidator,
    parameter_group_change: ResourceChange,
) -> None:
    """ElasticachePlanValidator: Test parameter group updates with changes"""
    validator.plan.plan.resource_changes = [parameter_group_change]

    updates = validator.elasticache_parameter_group_updates
    assert len(updates) == 1
    assert updates[0] == parameter_group_change


@pytest.mark.parametrize(
    ("actions", "should_include"),
    [
        ([Action.ActionCreate], True),
        ([Action.ActionUpdate], True),
        ([Action.ActionDelete], False),
        ([Action.ActionNoop], False),
        ([Action.ActionCreate, Action.ActionUpdate], True),
    ],
)
def test_validator_replication_group_filter_by_actions(
    validator: ElasticachePlanValidator,
    actions: list[Action],
    *,
    should_include: bool,
) -> None:
    """ElasticachePlanValidator: Test filtering replication group changes by actions"""
    change = ResourceChange(
        address="aws_elasticache_replication_group.test",
        mode="managed",
        type="aws_elasticache_replication_group",
        name="test",
        provider_name="registry.terraform.io/hashicorp/aws",
        change=Change(
            actions=actions,
            before=None,
            after={"replication_group_id": "test"},
            after_unknown=None,
        ),
    )

    validator.plan.plan.resource_changes = [change]
    updates = validator.elasticache_replication_group_updates
    assert bool(len(updates)) == should_include


def test_replication_group_validate_id_not_exists(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ReplicationGroup: Test validation when replication group doesn't exist (valid case)"""
    mock_aws_client.describe_replication_groups.side_effect = (
        mock_aws_client.exceptions.ReplicationGroupNotFoundFault()
    )

    validator._validate_replication_group_id("new-cluster")
    assert validator.errors == []


def test_replication_group_validate_id_exists(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ReplicationGroup: Test validation when replication group exists (error case)"""
    mock_aws_client.describe_replication_groups.return_value = {
        "ReplicationGroups": [{"ReplicationGroupId": "existing-cluster"}]
    }

    validator._validate_replication_group_id("existing-cluster")
    assert len(validator.errors) == 1
    assert "already exists" in validator.errors[0]


def test_replication_group_validate_subnets_same_vpc(
    validator: ElasticachePlanValidator,
    mock_aws_api: MagicMock,  # ruff: ignore[unused-function-argument]
) -> None:
    """ReplicationGroup: Test subnet validation with subnets in same VPC"""
    vpc_id = validator._validate_subnets("test-subnet-group", availability_zones=[])

    assert vpc_id == "vpc-123"
    assert validator.errors == []


def test_replication_group_validate_subnets_different_vpcs(
    validator: ElasticachePlanValidator, mock_aws_api: MagicMock
) -> None:
    """ReplicationGroup: Test subnet validation with subnets in different VPCs"""
    mock_aws_api.get_subnets.return_value = [
        {"SubnetId": "subnet-123", "VpcId": "vpc-123"},
        {"SubnetId": "subnet-456", "VpcId": "vpc-456"},
    ]

    validator._validate_subnets("test-subnet-group", availability_zones=[])
    assert len(validator.errors) == 1
    assert "same VPC" in validator.errors[0]


def test_replication_group_validate_subnets_missing_vpc_id(
    validator: ElasticachePlanValidator, mock_aws_api: MagicMock
) -> None:
    """ReplicationGroup: Test subnet validation with missing VPC ID"""
    mock_aws_api.get_subnets.return_value = [
        {"SubnetId": "subnet-123"},  # Missing VpcId
        {"SubnetId": "subnet-456", "VpcId": "vpc-456"},
    ]

    validator._validate_subnets("test-subnet-group", availability_zones=[])
    assert len(validator.errors) == 1
    assert "VpcId not found" in validator.errors[0]


def test_replication_group_validate_subnets_bad_availability_zones(
    validator: ElasticachePlanValidator,
    mock_aws_api: MagicMock,  # ruff: ignore[unused-function-argument]
) -> None:
    """ReplicationGroup: Test subnet validation with not covered availability zones"""
    validator._validate_subnets("test-subnet-group", availability_zones=["some-zone"])
    assert len(validator.errors) == 1
    assert (
        "Subnet group test-subnet-group does not cover all requested"
        in validator.errors[0]
    )


def test_replication_group_validate_security_groups_valid(
    validator: ElasticachePlanValidator,
    mock_aws_api: MagicMock,  # ruff: ignore[unused-function-argument]
) -> None:
    """ReplicationGroup: Test security group validation with valid groups"""
    validator._validate_security_groups(["sg-123", "sg-456"], "vpc-123")
    assert validator.errors == []


def test_replication_group_validate_security_groups_not_found(
    validator: ElasticachePlanValidator, mock_aws_api: MagicMock
) -> None:
    """ReplicationGroup: Test security group validation with missing groups"""
    mock_aws_api.get_security_groups.return_value = [
        {"GroupId": "sg-123", "VpcId": "vpc-123"}
    ]

    validator._validate_security_groups(["sg-123", "sg-missing"], "vpc-123")
    assert len(validator.errors) == 1
    assert "not found" in validator.errors[0]


def test_replication_group_validate_security_groups_wrong_vpc(
    validator: ElasticachePlanValidator, mock_aws_api: MagicMock
) -> None:
    """ReplicationGroup: Test security group validation with wrong VPC"""
    mock_aws_api.get_security_groups.return_value = [
        {"GroupId": "sg-123", "VpcId": "vpc-wrong"},
        {"GroupId": "sg-456", "VpcId": "vpc-123"},
    ]

    validator._validate_security_groups(["sg-123", "sg-456"], "vpc-123")
    assert len(validator.errors) == 1
    assert "does not belong to the same VPC" in validator.errors[0]


@pytest.mark.parametrize(
    ("engine", "version", "expected_family"),
    [
        ("redis", "7.0.7", "redis7.x"),
        ("redis", "6.2.13", "redis6.x"),
    ],
)
def test_replication_group_validate_engine_version_valid(
    validator: ElasticachePlanValidator,
    mock_aws_client: MagicMock,
    engine: str,
    version: str,
    expected_family: str,
) -> None:
    """ReplicationGroup: Test engine version validation with valid versions"""
    mock_aws_client.describe_cache_engine_versions.return_value = {
        "CacheEngineVersions": [{"CacheParameterGroupFamily": expected_family}]
    }

    engine_info = validator.get_engine_version(engine, version)
    assert engine_info.family == expected_family
    assert engine_info.name == engine
    assert engine_info.version == version


def test_replication_group_validate_engine_version_invalid(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ReplicationGroup: Test engine version validation with invalid version"""
    mock_aws_client.describe_cache_engine_versions.return_value = {
        "CacheEngineVersions": []
    }

    with pytest.raises(ValueError, match="not available"):
        validator.get_engine_version("redis", "invalid")


def test_replication_group_validate_apply_immediately_for_version_change_required(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: Test apply_immediately validation when version changes (required)"""
    validator._validate_cluster_upgrade(
        before_engine="redis",
        after_engine="redis",
        before_version="6.2.13",
        after_version="7.0.7",
        apply_immediately=False,
    )
    assert len(validator.errors) == 1
    assert "apply_immediately must be true" in validator.errors[0]


def test_replication_group_validate_apply_immediately_for_version_change_correct(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: Test apply_immediately validation when correctly set"""
    validator._validate_cluster_upgrade(
        before_engine="redis",
        after_engine="redis",
        before_version="6.2.13",
        after_version="7.0.7",
        apply_immediately=True,
    )
    assert validator.errors == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({"transit_encryption_enabled": False}, {"transit_encryption_enabled": True}),
        (
            {"transit_encryption_mode": "preferred"},
            {"transit_encryption_mode": "required"},
        ),
        (
            {"auth_token_update_strategy": "ROTATE"},
            {"auth_token_update_strategy": "SET"},
        ),
        (
            {"auth_token_update_strategy": "SET"},
            {"auth_token_update_strategy": "ROTATE"},
        ),
        (
            {"auth_token_update_strategy": None},
            {"auth_token_update_strategy": "ROTATE"},
        ),
    ],
)
def test_replication_group_validate_apply_immediately_for_encryption_changes_required(
    validator: ElasticachePlanValidator,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    """ReplicationGroup: apply_immediately is required for each of the three encryption-related fields, in either direction"""
    validator._validate_apply_immediately_for_encryption_changes(
        before=before, after=after, apply_immediately=False
    )
    assert len(validator.errors) == 1
    assert "apply_immediately must be true" in validator.errors[0]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({"transit_encryption_enabled": False}, {"transit_encryption_enabled": True}),
        (
            {"transit_encryption_mode": "preferred"},
            {"transit_encryption_mode": "required"},
        ),
        (
            {"auth_token_update_strategy": "ROTATE"},
            {"auth_token_update_strategy": "SET"},
        ),
        (
            {"auth_token_update_strategy": "SET"},
            {"auth_token_update_strategy": "ROTATE"},
        ),
        (
            {"auth_token_update_strategy": None},
            {"auth_token_update_strategy": "ROTATE"},
        ),
    ],
)
def test_replication_group_validate_apply_immediately_for_encryption_changes_correct(
    validator: ElasticachePlanValidator,
    before: dict[str, object],
    after: dict[str, object],
) -> None:
    """ReplicationGroup: a well-formed tenant change (apply_immediately correctly set) must not be rejected.

    Mirrors the "required" test above field-for-field and direction-for-direction -
    a tenant setting reset_password together with apply_immediately: true in the
    same MR (the normal, correct way to request a rotation) must see a clean plan,
    not just a rejection when apply_immediately is missing.
    """
    validator._validate_apply_immediately_for_encryption_changes(
        before=before, after=after, apply_immediately=True
    )
    assert validator.errors == []


def test_replication_group_validate_encryption_changes_unchanged(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: No error when nothing relevant changed, even without apply_immediately"""
    validator._validate_apply_immediately_for_encryption_changes(
        before={"transit_encryption_enabled": True},
        after={"transit_encryption_enabled": True},
        apply_immediately=False,
    )
    assert validator.errors == []


def test_validate_transit_encryption_mode_missing_rejected(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: enabling transit_encryption_enabled without transit_encryption_mode=required is rejected"""
    validator.input.data.transit_encryption_mode = None
    validator._validate_transit_encryption_mode(
        before_transit_encryption_enabled=False,
        after_transit_encryption_enabled=True,
    )
    assert len(validator.errors) == 1
    assert "transit_encryption_mode must be set to 'required'" in validator.errors[0]


def test_validate_transit_encryption_mode_preferred_rejected(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: "preferred" is never accepted as the tenant's final declared mode for this transition"""
    validator.input.data.transit_encryption_mode = "preferred"
    validator._validate_transit_encryption_mode(
        before_transit_encryption_enabled=False,
        after_transit_encryption_enabled=True,
    )
    assert len(validator.errors) == 1
    assert "transit_encryption_mode must be set to 'required'" in validator.errors[0]


def test_validate_transit_encryption_mode_required_accepted(
    validator: ElasticachePlanValidator,
) -> None:
    validator.input.data.transit_encryption_mode = "required"
    validator._validate_transit_encryption_mode(
        before_transit_encryption_enabled=False,
        after_transit_encryption_enabled=True,
    )
    assert validator.errors == []


def test_validate_transit_encryption_mode_not_enabling_skips_check(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: the check only applies to the false->true enabling transition"""
    validator.input.data.transit_encryption_mode = None
    validator._validate_transit_encryption_mode(
        before_transit_encryption_enabled=True,
        after_transit_encryption_enabled=True,
    )
    assert validator.errors == []


def test_validate_transit_encryption_engine_support_blocks_when_replace_planned(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: blocked whenever Terraform itself plans a replace (ActionDelete present).

    Deliberately engine/version-agnostic: this defers to the pinned Terraform
    AWS provider's own decision instead of a hardcoded version threshold, so
    it stays correct even if support for other engines/versions changes
    later - see hooks/post_plan.py docstring.
    """
    validator._validate_transit_encryption_engine_support(
        before_transit_encryption_enabled=False,
        after_transit_encryption_enabled=True,
        actions=[Action.ActionDelete, Action.ActionCreate],
        engine_info=EngineInfo(name="redis", family="redis6.x", version="6.2"),
    )
    assert len(validator.errors) == 1
    assert "would replace the cluster" in validator.errors[0]


def test_validate_transit_encryption_engine_support_allows_in_place_update(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: allowed whenever Terraform can apply this as an in-place update"""
    validator._validate_transit_encryption_engine_support(
        before_transit_encryption_enabled=False,
        after_transit_encryption_enabled=True,
        actions=[Action.ActionUpdate],
        engine_info=EngineInfo(name="valkey", family="valkey7", version="7.2"),
    )
    assert validator.errors == []


def test_validate_transit_encryption_engine_support_skips_when_not_enabling(
    validator: ElasticachePlanValidator,
) -> None:
    """ReplicationGroup: the check only applies to the false->true enabling transition"""
    validator._validate_transit_encryption_engine_support(
        before_transit_encryption_enabled=True,
        after_transit_encryption_enabled=True,
        actions=[Action.ActionDelete, Action.ActionCreate],
        engine_info=EngineInfo(name="redis", family="redis6.x", version="6.2"),
    )
    assert validator.errors == []


def test_validate_transit_encryption_engine_support_fires_on_replace_action(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ReplicationGroup: must fire for a replace plan (older engines force delete+create, not update)"""
    mock_aws_client.describe_cache_engine_versions.return_value = {
        "CacheEngineVersions": [{"CacheParameterGroupFamily": "redis6.x"}]
    }
    mock_aws_client.describe_replication_groups.side_effect = (
        mock_aws_client.exceptions.ReplicationGroupNotFoundFault()
    )
    change = ResourceChange(
        address="aws_elasticache_replication_group.test",
        mode="managed",
        type="aws_elasticache_replication_group",
        name="test",
        provider_name="registry.terraform.io/hashicorp/aws",
        change=Change(
            actions=[Action.ActionDelete, Action.ActionCreate],
            before={
                "engine": "redis",
                "engine_version": "6.2",
                "transit_encryption_enabled": False,
            },
            after={
                "engine": "redis",
                "engine_version": "6.2",
                "transit_encryption_enabled": True,
                "node_type": "cache.t4g.micro",
                "replication_group_id": "test-cluster",
                "subnet_group_name": "test-subnet-group",
                "security_group_ids": ["sg-123"],
                "apply_immediately": True,
            },
            after_unknown=None,
        ),
    )
    validator.plan.plan.resource_changes = [change]

    result = validator.validate()

    assert result is False
    assert any("would replace the cluster" in error for error in validator.errors)


def test_replication_group_validate_create(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ReplicationGroup: Test complete replication group validation for create action"""
    mock_aws_client.describe_replication_groups.side_effect = (
        mock_aws_client.exceptions.ReplicationGroupNotFoundFault()
    )

    validator._validate_replication_group(
        replication_group_id="test-cluster",
        subnet_group_name="test-subnet-group",
        security_groups=["sg-123", "sg-456"],
        availability_zones=["us-east-1a"],
    )

    assert validator.errors == []


def test_replication_group_validate_update(
    validator: ElasticachePlanValidator,
    mock_aws_client: MagicMock,  # ruff: ignore[unused-function-argument]
) -> None:
    """ReplicationGroup: Test cluster upgrade validation for update action"""
    validator._validate_cluster_upgrade(
        before_engine="redis",
        after_engine="redis",
        before_version="6.2.13",
        after_version="7.0.7",
        apply_immediately=True,
    )

    assert validator.errors == []


def test_parameter_group_validate_name_not_exists(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ParameterGroup: Test parameter group name validation when group doesn't exist"""
    mock_aws_client.describe_cache_parameters.side_effect = (
        mock_aws_client.exceptions.CacheParameterGroupNotFoundFault()
    )

    validator._validate_parameter_group_name("new-pg")
    assert validator.errors == []


def test_parameter_group_validate_name_exists(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ParameterGroup: Test parameter group name validation when group exists"""
    mock_aws_client.describe_cache_parameters.return_value = {"Parameters": []}

    validator._validate_parameter_group_name("existing-pg")
    assert len(validator.errors) == 1
    assert "already exists" in validator.errors[0]


def test_parameter_group_validate_family_matching(
    validator: ElasticachePlanValidator,
) -> None:
    """ParameterGroup: Test parameter group family validation with matching family"""
    engine_info = EngineInfo(name="redis", family="redis7.x", version="7.0.7")

    validator._validate_parameter_group_family(engine_info, "redis7.x")
    assert validator.errors == []


def test_parameter_group_validate_family_mismatch(
    validator: ElasticachePlanValidator,
) -> None:
    """ParameterGroup: Test parameter group family validation with mismatched family"""
    engine_info = EngineInfo(name="redis", family="redis7.x", version="7.0.7")

    validator._validate_parameter_group_family(engine_info, "redis6.x")
    assert len(validator.errors) == 1
    assert "does not match engine" in validator.errors[0]


def test_parameter_group_validate_create(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """ParameterGroup: Test complete parameter group validation for create action"""
    mock_aws_client.describe_cache_parameters.side_effect = (
        mock_aws_client.exceptions.CacheParameterGroupNotFoundFault()
    )

    engine_info = EngineInfo(name="redis", family="redis7.x", version="7.0.7")

    validator._validate_parameter_group_name("test-pg")
    validator._validate_parameter_group_family(engine_info, "redis7.x")
    assert validator.errors == []


def test_parameter_group_validate_update(
    validator: ElasticachePlanValidator,
    mock_aws_client: MagicMock,  # ruff: ignore[unused-function-argument]
) -> None:
    """ParameterGroup: Test parameter group validation for update action"""
    engine_info = EngineInfo(name="redis", family="redis7.x", version="7.0.7")

    validator._validate_parameter_group_family(engine_info, "redis7.x")
    assert validator.errors == []


def test_validate_no_changes(validator: ElasticachePlanValidator) -> None:
    """Validate: Test validation with no changes"""
    result = validator.validate()
    assert result is True
    assert validator.errors == []


def test_validate_with_valid_changes(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    parameter_group_change: ResourceChange,
    mock_aws_client: MagicMock,
) -> None:
    """Validate: Test validation with valid changes"""
    mock_aws_client.describe_replication_groups.side_effect = (
        mock_aws_client.exceptions.ReplicationGroupNotFoundFault()
    )
    mock_aws_client.describe_cache_parameters.side_effect = (
        mock_aws_client.exceptions.CacheParameterGroupNotFoundFault()
    )

    validator.plan.plan.resource_changes = [
        replication_group_change,
        parameter_group_change,
    ]

    result = validator.validate()
    assert result is True
    assert validator.errors == []


def test_validate_with_errors(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    parameter_group_change: ResourceChange,
    mock_aws_client: MagicMock,
) -> None:
    """Validate: Test validation with errors"""
    # Make replication group exist (error condition)
    mock_aws_client.describe_replication_groups.return_value = {
        "ReplicationGroups": [{"ReplicationGroupId": "test-cluster"}]
    }
    mock_aws_client.describe_cache_parameters.side_effect = (
        mock_aws_client.exceptions.CacheParameterGroupNotFoundFault()
    )

    validator.plan.plan.resource_changes = [
        replication_group_change,
        parameter_group_change,
    ]

    result = validator.validate()
    assert result is False
    assert len(validator.errors) > 0


def test_validate_auth_token_rotation_with_apply_immediately_passes(
    validator: ElasticachePlanValidator,
    mock_aws_client: MagicMock,  # ruff: ignore[unused-function-argument]
) -> None:
    """Validate: a well-formed reset_password change produces a clean plan.

    apply_immediately: true set in the same MR (matching the tenant-facing
    contract) must produce a clean plan end-to-end, not just when the
    validator method is called in isolation.
    """
    change = ResourceChange(
        address="aws_elasticache_replication_group.test",
        mode="managed",
        type="aws_elasticache_replication_group",
        name="test",
        provider_name="registry.terraform.io/hashicorp/aws",
        change=Change(
            actions=[Action.ActionUpdate],
            before={
                "engine": "redis",
                "engine_version": "7.0.7",
                "auth_token_update_strategy": "SET",
                "transit_encryption_enabled": True,
                "transit_encryption_mode": "required",
            },
            after={
                "engine": "redis",
                "engine_version": "7.0.7",
                "auth_token_update_strategy": "ROTATE",
                "transit_encryption_enabled": True,
                "transit_encryption_mode": "required",
                "apply_immediately": True,
            },
            after_unknown=None,
        ),
    )
    validator.plan.plan.resource_changes = [change]

    result = validator.validate()

    assert result is True
    assert validator.errors == []


def test_validate_multiple_replication_groups(
    validator: ElasticachePlanValidator, mock_aws_client: MagicMock
) -> None:
    """Validate: Test validation with multiple replication groups"""
    mock_aws_client.describe_replication_groups.side_effect = (
        mock_aws_client.exceptions.ReplicationGroupNotFoundFault()
    )

    changes = []
    for i in range(3):
        change = ResourceChange(
            address=f"aws_elasticache_replication_group.test_{i}",
            mode="managed",
            type="aws_elasticache_replication_group",
            name=f"test_{i}",
            provider_name="registry.terraform.io/hashicorp/aws",
            change=Change(
                actions=[Action.ActionCreate],
                before=None,
                after={
                    "replication_group_id": f"test-cluster-{i}",
                    "node_type": "cache.t4g.micro",
                    "engine": "redis",
                    "engine_version": "7.0.7",
                    "subnet_group_name": "test-subnet-group",
                    "security_group_ids": ["sg-123"],
                    "apply_immediately": True,
                },
                after_unknown=None,
            ),
        )
        changes.append(change)

    validator.plan.plan.resource_changes = changes

    result = validator.validate()
    assert result is True
    assert validator.errors == []


@pytest.mark.parametrize(
    ("engine", "version", "family"),
    [
        ("redis", "7.0.7", "redis7.x"),
        ("redis", "6.2.13", "redis6.x"),
    ],
)
def test_engine_version_family_mapping(
    validator: ElasticachePlanValidator,
    mock_aws_client: MagicMock,
    engine: str,
    version: str,
    family: str,
) -> None:
    """EngineVersion: Test engine version to family mapping"""
    mock_aws_client.describe_cache_engine_versions.return_value = {
        "CacheEngineVersions": [{"CacheParameterGroupFamily": family}]
    }

    engine_info = validator.get_engine_version(engine, version)
    assert engine_info.family == family
    assert engine_info.name == engine
    assert engine_info.version == version


@pytest.mark.parametrize(
    ("actions", "resource_type", "expected_rg_count", "expected_pg_count"),
    [
        ([Action.ActionCreate], "aws_elasticache_replication_group", 1, 0),
        ([Action.ActionUpdate], "aws_elasticache_replication_group", 1, 0),
        ([Action.ActionDelete], "aws_elasticache_replication_group", 0, 0),
        ([Action.ActionCreate], "aws_elasticache_parameter_group", 0, 1),
        ([Action.ActionUpdate], "aws_elasticache_parameter_group", 0, 1),
        ([Action.ActionDelete], "aws_elasticache_parameter_group", 0, 0),
        ([Action.ActionCreate], "aws_instance", 0, 0),
    ],
)
def test_resource_filtering(
    validator: ElasticachePlanValidator,
    actions: list[Action],
    resource_type: str,
    expected_rg_count: int,
    expected_pg_count: int,
) -> None:
    """ResourceFiltering: Test resource filtering by type and action"""
    change = ResourceChange(
        address=f"{resource_type}.test",
        mode="managed",
        type=resource_type,
        name="test",
        provider_name="registry.terraform.io/hashicorp/aws",
        change=Change(
            actions=actions, before=None, after={"test": "value"}, after_unknown=None
        ),
    )

    validator.plan.plan.resource_changes = [change]

    rg_updates = validator.elasticache_replication_group_updates
    pg_updates = validator.elasticache_parameter_group_updates

    assert len(rg_updates) == expected_rg_count
    assert len(pg_updates) == expected_pg_count


@pytest.mark.parametrize(
    "actions",
    [
        [Action.ActionCreate],
        [Action.ActionDelete, Action.ActionCreate],
        [Action.ActionCreate, Action.ActionDelete],
        [Action.ActionUpdate],
    ],
)
@pytest.mark.parametrize("available", [True, False])
def test_validate_node_type_in_requested_availability_zone(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    actions: list[Action],
    *,
    available: bool,
) -> None:
    """Reject unsupported placements before apply, including replacement plans."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = actions
    replication_group_change.change.after |= {
        "replication_group_id": "lightwell-experience-redis-stage",
        "preferred_cache_cluster_azs": ["us-east-1e"],
    }
    if actions != [Action.ActionCreate]:
        replication_group_change.change.before = {
            **replication_group_change.change.after,
            "node_type": "cache.t3.micro",
            "replication_group_id": "old-cluster",
        }
    mock_aws_api.client.describe_replication_groups.side_effect = (
        mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault()
    )
    mock_aws_api.client.list_allowed_node_type_modifications.return_value = {
        "ScaleUpModifications": ["cache.t4g.micro"],
        "ScaleDownModifications": [],
    }
    mock_aws_api.get_cache_group_subnets.return_value = [
        {
            "SubnetIdentifier": "subnet-123",
            "SubnetAvailabilityZone": {"Name": "us-east-1e"},
        }
    ]
    mock_aws_api.get_replication_group_availability_zones.return_value = {"us-east-1e"}
    mock_aws_api.get_node_type_availability_zones.return_value = (
        {"us-east-1e"} if available else {"us-east-1a"}
    )
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is available
    if not available:
        assert any(
            "lightwell-experience-redis-stage" in error
            and "cache.t4g.micro" in error
            and "us-east-1e" in error
            for error in validator.errors
        )
    mock_aws_api.get_node_type_availability_zones.assert_called_once_with(
        node_type="cache.t4g.micro"
    )


@pytest.mark.parametrize("availability_zones", [[], None])
@pytest.mark.parametrize("available", [True, False])
def test_validate_automatic_placement_uses_eligible_subnet_zones(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    availability_zones: list[str] | None,
    *,
    available: bool,
) -> None:
    """An unused unsupported AZ must not block AWS's automatic placement."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.after["preferred_cache_cluster_azs"] = (
        availability_zones
    )
    replication_group_change.change.after |= {
        "automatic_failover_enabled": True,
        "num_cache_clusters": 2,
        "multi_az_enabled": None,
    }
    mock_aws_api.client.describe_replication_groups.side_effect = (
        mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault()
    )
    mock_aws_api.get_node_type_availability_zones.return_value = (
        {"us-east-1a"} if available else {"us-east-1c"}
    )
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is available
    if not available:
        assert any("not offered" in error for error in validator.errors)


def test_validate_node_type_update_checks_current_member_zones(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    mock_aws_client: MagicMock,
) -> None:
    """A resize must validate occupied AZs, not unrelated subnet-group AZs."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "node_type": "cache.t3.micro",
    }
    mock_aws_client.list_allowed_node_type_modifications.return_value = {
        "ScaleUpModifications": ["cache.t4g.micro"],
    }
    mock_aws_api.get_replication_group_availability_zones.return_value = {"us-east-1e"}
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is False
    assert any("us-east-1e" in error for error in validator.errors)
    mock_aws_api.get_replication_group_availability_zones.assert_called_once_with(
        replication_group_id="test-cluster"
    )


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize(
    "modification_type", ["ScaleUpModifications", "ScaleDownModifications"]
)
def test_validate_resize_checks_elasticache_allowed_node_types(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_client: MagicMock,
    modification_type: str,
    *,
    allowed: bool,
) -> None:
    """EC2 offerings alone must not override ElastiCache's resize restrictions."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "node_type": "cache.t3.micro",
    }
    mock_aws_client.list_allowed_node_type_modifications.return_value = {
        modification_type: ["cache.t4g.micro"] if allowed else [],
    }
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is allowed
    if not allowed:
        assert any(
            "cache.t4g.micro" in error and "test-cluster" in error
            for error in validator.errors
        )
    mock_aws_client.list_allowed_node_type_modifications.assert_called_once_with(
        ReplicationGroupId="test-cluster"
    )


@pytest.mark.parametrize(
    "field", ["num_cache_clusters", "num_node_groups", "replicas_per_node_group"]
)
@pytest.mark.parametrize("available", [True, False])
def test_validate_scale_out_checks_subnet_zones(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    field: str,
    *,
    available: bool,
) -> None:
    """Automatic scale-out needs an eligible subnet AZ, not every subnet AZ."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.after[field] = 3
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        field: 2,
    }
    mock_aws_api.get_node_type_availability_zones.return_value = (
        {"us-east-1a"} if available else {"us-east-1c"}
    )
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is available
    if not available:
        assert any("not offered" in error for error in validator.errors)


def test_validate_unrelated_update_skips_node_type_availability(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Do not block unrelated changes or removal of nodes on placement checks."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.after["num_cache_clusters"] = 2
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "num_cache_clusters": 3,
    }
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is True
    mock_aws_api.get_node_type_availability_zones.assert_not_called()


def test_validate_availability_api_error_is_not_success(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    mock_aws_client: MagicMock,
) -> None:
    """Preserve AWS errors instead of treating missing permissions as availability."""
    mock_aws_client.describe_replication_groups.side_effect = (
        mock_aws_client.exceptions.ReplicationGroupNotFoundFault()
    )
    mock_aws_api.get_node_type_availability_zones.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "access denied"}},
        "DescribeInstanceTypeOfferings",
    )
    validator.plan.plan.resource_changes = [replication_group_change]

    with pytest.raises(ClientError, match=r"UnauthorizedOperation.*access denied"):
        validator.validate()


def test_validate_replacement_can_reuse_id_after_destroy(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_client: MagicMock,
) -> None:
    """A destroy-before-create replacement is not a duplicate resource name."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionDelete, Action.ActionCreate]
    replication_group_change.change.before = dict(replication_group_change.change.after)
    mock_aws_client.describe_replication_groups.return_value = {
        "ReplicationGroups": [{"ReplicationGroupId": "test-cluster"}]
    }
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is True
    mock_aws_client.describe_replication_groups.assert_not_called()


def test_validate_placement_update_requires_subnet_zone_membership(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """An offered AZ is still invalid if the target subnet group does not cover it."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = dict(replication_group_change.change.after)
    replication_group_change.change.after["preferred_cache_cluster_azs"] = [
        "us-east-1e"
    ]
    mock_aws_api.get_node_type_availability_zones.return_value = {
        "us-east-1a",
        "us-east-1b",
        "us-east-1e",
    }
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is False
    assert any(
        "test-subnet-group" in error and "us-east-1e" in error
        for error in validator.errors
    )


def test_validate_unspecified_placement_normalization_is_not_scale_out(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Null and empty preferred AZs both mean automatic placement."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "preferred_cache_cluster_azs": None,
    }
    replication_group_change.change.after["preferred_cache_cluster_azs"] = []
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is True
    mock_aws_api.get_node_type_availability_zones.assert_not_called()


def test_validate_resize_does_not_check_unused_subnet_zones(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """An unsupported but unoccupied subnet AZ must not block a valid resize."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "node_type": "cache.t3.micro",
    }
    mock_aws_api.client.list_allowed_node_type_modifications.return_value = {
        "ScaleDownModifications": ["cache.t4g.micro"],
    }
    mock_aws_api.get_node_type_availability_zones.return_value = {"us-east-1a"}
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is True
    mock_aws_api.get_cache_group_subnets.assert_not_called()


def test_validate_combined_engine_and_node_type_change_uses_planned_placement(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Current-engine resize targets cannot predict the planned upgraded engine."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "engine_version": "6.2",
        "node_type": "cache.t3.micro",
    }
    mock_aws_api.get_node_type_availability_zones.return_value = {"us-east-1a"}
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is True
    mock_aws_api.client.list_allowed_node_type_modifications.assert_not_called()
    mock_aws_api.get_node_type_availability_zones.assert_called_once_with(
        node_type="cache.t4g.micro"
    )


def test_validate_resize_fails_without_current_member_zones(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Missing placement metadata must not silently pass validation."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = [Action.ActionUpdate]
    replication_group_change.change.before = {
        **replication_group_change.change.after,
        "node_type": "cache.t3.micro",
    }
    mock_aws_api.get_replication_group_availability_zones.return_value = set()
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is False
    assert any(
        "Cannot determine availability zones" in error and "test-cluster" in error
        for error in validator.errors
    )


@pytest.fixture
def post_plan_hook(
    mocker: MockerFixture,
    ai_input: AppInterfaceInput,
    terraform_plan: MagicMock,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Run the actual hook with mocked input, plan and AWS I/O."""
    mocker.patch("external_resources_io.log.setup_logging")
    mocker.patch("external_resources_io.input.read_input_from_file", return_value={})
    mocker.patch("external_resources_io.input.parse_model", return_value=ai_input)
    mocker.patch(
        "external_resources_io.terraform.TerraformJsonPlanParser",
        return_value=terraform_plan,
    )
    mocker.patch("hooks_lib.aws_api.AWSApi", return_value=mock_aws_api)
    mock_aws_api.client.describe_replication_groups.side_effect = (
        mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault()
    )
    terraform_plan.plan.resource_changes = [replication_group_change]


@pytest.mark.usefixtures("post_plan_hook")
@pytest.mark.parametrize("dry_run", ["True", "False"])
def test_post_plan_rejects_unavailable_node_type_with_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_aws_api: MagicMock,
    dry_run: str,
) -> None:
    """The actual hook fails with an actionable log in dry-run and real apply."""
    monkeypatch.setenv("DRY_RUN", dry_run)
    monkeypatch.setenv("ACTION", "Apply")
    mock_aws_api.get_node_type_availability_zones.return_value = set()

    with pytest.raises(SystemExit, match="1") as error:
        runpy.run_path("hooks/post_plan.py", run_name="__main__")

    assert error.value.code == 1
    assert "test-cluster" in caplog.text
    assert "cache.t4g.micro" in caplog.text
    assert "us-east-1a" in caplog.text
    assert "Validation ended succesfully" not in caplog.text


@pytest.mark.usefixtures("post_plan_hook")
def test_post_plan_valid_placement_passes_dry_run(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_aws_api: MagicMock,
) -> None:
    """The actual hook accepts automatic placement with an unsupported unused AZ."""
    monkeypatch.setenv("DRY_RUN", "True")
    monkeypatch.setenv("ACTION", "Apply")
    caplog.set_level(logging.INFO)
    mock_aws_api.get_node_type_availability_zones.return_value = {"us-east-1a"}

    runpy.run_path("hooks/post_plan.py", run_name="__main__")

    assert "Validation ended succesfully" in caplog.text


@pytest.mark.parametrize(
    ("available_zones", "expected"),
    [
        ({"us-east-1a"}, False),
        ({"us-east-1a", "us-east-1b"}, True),
    ],
)
def test_validate_multi_az_automatic_placement_needs_two_eligible_zones(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    available_zones: set[str],
    *,
    expected: bool,
) -> None:
    """Default failover does not require Multi-AZ placement, but explicit Multi-AZ does."""
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.after |= {
        "automatic_failover_enabled": True,
        "num_cache_clusters": 2,
        "multi_az_enabled": True,
    }
    mock_aws_api.client.describe_replication_groups.side_effect = (
        mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault()
    )
    mock_aws_api.get_node_type_availability_zones.return_value = available_zones
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is expected
    if not expected:
        assert any("Multi-AZ" in error for error in validator.errors)


@pytest.mark.usefixtures("post_plan_hook")
def test_post_plan_preserves_aws_error_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_aws_api: MagicMock,
) -> None:
    """Read API failures must stop the hook with the original AWS error visible."""
    monkeypatch.setenv("DRY_RUN", "True")
    monkeypatch.setenv("ACTION", "Apply")
    mock_aws_api.get_node_type_availability_zones.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "access denied"}},
        "DescribeInstanceTypeOfferings",
    )

    with pytest.raises(SystemExit, match="1") as error:
        runpy.run_path("hooks/post_plan.py", run_name="__main__")

    assert error.value.code == 1
    assert "DescribeInstanceTypeOfferings" in caplog.text
    assert "UnauthorizedOperation" in caplog.text
    assert "access denied" in caplog.text
    assert "Validation ended succesfully" not in caplog.text


@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("valid", [False, True])
def test_validate_multi_az_enablement_on_update(
    validator: ElasticachePlanValidator,
    replication_group_update: ResourceChange,
    mock_aws_api: MagicMock,
    *,
    scale_out: bool,
    valid: bool,
) -> None:
    """Validate occupied AZs for enablement alone and possible AZs after scale-out."""
    assert replication_group_update.change
    assert replication_group_update.change.after
    replication_group_update.change.after["multi_az_enabled"] = True
    if scale_out:
        replication_group_update.change.after["num_cache_clusters"] = 3
    mock_aws_api.get_replication_group_availability_zones.return_value = (
        {"us-east-1a", "us-east-1b"} if valid and not scale_out else {"us-east-1a"}
    )
    mock_aws_api.get_node_type_availability_zones.return_value = (
        {"us-east-1a", "us-east-1b"} if valid or not scale_out else {"us-east-1a"}
    )
    validator.plan.plan.resource_changes = [replication_group_update]

    assert validator.validate() is valid
    if not valid:
        assert any("Multi-AZ" in error for error in validator.errors)


@pytest.mark.parametrize("enabled_after", [True, False])
def test_validate_non_enabling_multi_az_does_not_read_placement(
    validator: ElasticachePlanValidator,
    replication_group_update: ResourceChange,
    mock_aws_api: MagicMock,
    *,
    enabled_after: bool,
) -> None:
    """Unrelated changes must not acquire new placement-validation prerequisites."""
    assert replication_group_update.change
    assert replication_group_update.change.before
    assert replication_group_update.change.after
    replication_group_update.change.before["multi_az_enabled"] = True
    replication_group_update.change.after["multi_az_enabled"] = enabled_after
    validator.plan.plan.resource_changes = [replication_group_update]

    assert validator.validate() is True
    mock_aws_api.get_node_type_availability_zones.assert_not_called()
    mock_aws_api.get_replication_group_availability_zones.assert_not_called()


def test_validate_multi_az_enablement_uses_existing_nodes_not_new_offerings(
    validator: ElasticachePlanValidator,
    replication_group_update: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """A flag-only update does not allocate new nodes or need new-node offerings."""
    assert replication_group_update.change
    assert replication_group_update.change.after
    replication_group_update.change.after["multi_az_enabled"] = True
    mock_aws_api.get_replication_group_availability_zones.return_value = {
        "us-east-1a",
        "us-east-1b",
    }
    mock_aws_api.get_node_type_availability_zones.return_value = {"us-east-1a"}
    validator.plan.plan.resource_changes = [replication_group_update]

    assert validator.validate() is True
    mock_aws_api.get_node_type_availability_zones.assert_not_called()
    mock_aws_api.get_cache_group_subnets.assert_not_called()


@pytest.mark.parametrize(
    "operation",
    [
        "get_replication_group_availability_zones",
        "list_allowed_node_type_modifications",
    ],
)
def test_validate_missing_replication_group_preserves_errors_and_continues(
    validator: ElasticachePlanValidator,
    replication_group_update: ResourceChange,
    mock_aws_api: MagicMock,
    operation: str,
) -> None:
    """Missing AWS groups are resource-specific errors, not fatal to the whole plan."""
    assert replication_group_update.change
    assert replication_group_update.change.before
    replication_group_update.change.before["node_type"] = "cache.t3.micro"
    healthy_group = deepcopy(replication_group_update)
    assert healthy_group.change
    assert healthy_group.change.before
    assert healthy_group.change.after
    healthy_group.change.before["replication_group_id"] = "healthy-group"
    healthy_group.change.after["replication_group_id"] = "healthy-group"
    validator.plan.plan.resource_changes = [replication_group_update, healthy_group]
    validator.errors.append("Earlier validation finding")
    missing_group = mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault(
        "group disappeared from AWS"
    )
    allowed_types = {"ScaleUpModifications": ["cache.t4g.micro"]}
    mock_aws_api.client.list_allowed_node_type_modifications.return_value = (
        allowed_types
    )
    if operation == "get_replication_group_availability_zones":
        mock_aws_api.get_replication_group_availability_zones.side_effect = [
            missing_group,
            {"us-east-1a"},
        ]
    else:
        mock_aws_api.client.list_allowed_node_type_modifications.side_effect = [
            missing_group,
            allowed_types,
        ]

    assert validator.validate() is False
    assert validator.errors[0] == "Earlier validation finding"
    assert any(
        "test-cluster" in error and "not found" in error for error in validator.errors
    )
    mock_aws_api.client.list_allowed_node_type_modifications.assert_called_with(
        ReplicationGroupId="healthy-group"
    )


def test_validate_create_fetches_subnet_group_once(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Placement and network checks must share the same subnet-group snapshot."""
    mock_aws_api.client.describe_replication_groups.side_effect = (
        mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault()
    )
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is True
    mock_aws_api.get_cache_group_subnets.assert_called_once_with("test-subnet-group")


@pytest.mark.parametrize(
    "actions",
    [
        [Action.ActionCreate],
        [Action.ActionDelete, Action.ActionCreate],
        [Action.ActionCreate, Action.ActionDelete],
        [Action.ActionUpdate],
    ],
)
@pytest.mark.parametrize("num_node_groups", [None, 1, 2])
def test_validate_az_preferences_respect_effective_shard_count(
    validator: ElasticachePlanValidator,
    replication_group_change: ResourceChange,
    mock_aws_api: MagicMock,
    actions: list[Action],
    num_node_groups: int | None,
) -> None:
    """Ignore multi-shard preferences, including shard counts computed from state."""
    validator.input = AppInterfaceInput(
        data=ElasticacheData(
            region="us-east-1",
            identifier="test-cluster",
            output_prefix="test-cluster",
            engine="valkey",
            engine_version="7.2",
            node_type="cache.t4g.micro",
            replication_group_id="test-cluster",
            security_group_ids=["sg-123", "sg-456"],
            subnet_group_name="test-subnet-group",
            availability_zones=["us-east-1e"],
        ),
        provision=validator.input.provision,
    )
    assert validator.input.data.num_node_groups is None
    assert replication_group_change.change
    assert replication_group_change.change.after
    replication_group_change.change.actions = actions
    replication_group_change.change.after |= {
        "engine": "valkey",
        "engine_version": "7.2",
        "num_node_groups": num_node_groups,
        "preferred_cache_cluster_azs": ["us-east-1e"],
    }
    if actions != [Action.ActionCreate]:
        replication_group_change.change.before = {
            **replication_group_change.change.after,
            "node_type": "cache.t3.micro",
            "preferred_cache_cluster_azs": ["us-east-1a"],
            "replication_group_id": (
                "old-cluster" if Action.ActionDelete in actions else "test-cluster"
            ),
        }
    mock_aws_api.client.describe_cache_engine_versions.return_value = {
        "CacheEngineVersions": [{"CacheParameterGroupFamily": "valkey7"}]
    }
    mock_aws_api.client.describe_replication_groups.side_effect = (
        mock_aws_api.client.exceptions.ReplicationGroupNotFoundFault()
    )
    mock_aws_api.get_replication_group_availability_zones.return_value = {
        "us-east-1a",
        "us-east-1b",
    }
    mock_aws_api.client.list_allowed_node_type_modifications.return_value = {
        "ScaleUpModifications": ["cache.t4g.micro"]
    }
    validator.plan.plan.resource_changes = [replication_group_change]

    assert validator.validate() is ((num_node_groups or 0) > 1)
    if (num_node_groups or 0) > 1:
        assert validator.errors == []
    else:
        assert any("us-east-1e" in error for error in validator.errors)


def test_validate_ignored_preference_change_does_not_allocate_new_nodes(
    validator: ElasticachePlanValidator,
    replication_group_update: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """An ineffective preference-only change must not trigger placement reads."""
    assert replication_group_update.change
    assert replication_group_update.change.before
    assert replication_group_update.change.after
    replication_group_update.change.before["num_node_groups"] = 2
    replication_group_update.change.after |= {
        "num_node_groups": 2,
        "preferred_cache_cluster_azs": ["us-east-1e"],
    }
    validator.plan.plan.resource_changes = [replication_group_update]

    assert validator.validate() is True
    mock_aws_api.get_node_type_availability_zones.assert_not_called()
    mock_aws_api.get_cache_group_subnets.assert_not_called()
    mock_aws_api.get_replication_group_availability_zones.assert_not_called()


def test_validate_multishard_resize_still_checks_occupied_azs(
    validator: ElasticachePlanValidator,
    replication_group_update: ResourceChange,
    mock_aws_api: MagicMock,
) -> None:
    """Ignored preferences must not weaken validation of real occupied AZs."""
    assert replication_group_update.change
    assert replication_group_update.change.before
    assert replication_group_update.change.after
    replication_group_update.change.before["node_type"] = "cache.t3.micro"
    replication_group_update.change.before["num_node_groups"] = 2
    replication_group_update.change.after |= {
        "num_node_groups": 2,
        "preferred_cache_cluster_azs": ["us-east-1a"],
    }
    mock_aws_api.get_replication_group_availability_zones.return_value = {"us-east-1e"}
    mock_aws_api.client.list_allowed_node_type_modifications.return_value = {
        "ScaleUpModifications": ["cache.t4g.micro"]
    }
    validator.plan.plan.resource_changes = [replication_group_update]

    assert validator.validate() is False
    assert any("us-east-1e" in error for error in validator.errors)
