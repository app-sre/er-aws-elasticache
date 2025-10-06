# ruff: noqa: SLF001
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from external_resources_io.terraform import (
    Action,
    Change,
    Plan,
    ResourceChange,
    TerraformJsonPlanParser,
)

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks.post_plan import ElasticachePlanValidator, EngineInfo


@pytest.fixture
def mock_aws_client() -> MagicMock:
    """Mock AWS ElastiCache client"""
    client = MagicMock()

    # Mock describe_replication_groups
    client.exceptions.ReplicationGroupNotFoundFault = Exception

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
def mock_aws_api(mock_aws_client: MagicMock) -> Generator[MagicMock, None, None]:
    """Mock AWSApi instance"""
    with patch("hooks.post_plan.AWSApi") as mock_aws_api_class:
        aws_api = MagicMock()
        aws_api.client = mock_aws_client

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
                "subnet_group_name": "test-subnet-group",
                "security_group_ids": ["sg-123", "sg-456"],
                "apply_immediately": True,
            },
            after_unknown=None,
        ),
    )


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
    mock_aws_api: MagicMock,  # noqa: ARG001
) -> ElasticachePlanValidator:
    """ElasticachePlanValidator instance"""
    return ElasticachePlanValidator(terraform_plan, ai_input)


def test_engine_info_creation() -> None:
    """EngineInfo: Test dataclass instance creation"""
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
    """EngineInfo: Test dataclass creation with different engine types"""
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
    mock_aws_api: MagicMock,  # noqa: ARG001
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
    mock_aws_api: MagicMock,  # noqa: ARG001
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
    mock_aws_api: MagicMock,  # noqa: ARG001
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
    mock_aws_client: MagicMock,  # noqa: ARG001
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
    mock_aws_client: MagicMock,  # noqa: ARG001
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
