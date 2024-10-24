import pytest
from cdktf import Testing
from cdktf_cdktf_provider_aws.elasticache_parameter_group import (
    ElasticacheParameterGroup,
)
from cdktf_cdktf_provider_aws.elasticache_replication_group import (
    ElasticacheReplicationGroup,
)
from cdktf_cdktf_provider_aws.provider import AwsProvider
from cdktf_cdktf_provider_random.provider import RandomProvider

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from er_aws_elasticache.stack import ElasticacheStack as Stack


@pytest.fixture
def stack(ai_input: AppInterfaceInput) -> Stack:
    """Fixture to get the initialized stack."""
    return Stack(Testing.app(), "CDKTF", ai_input)


@pytest.fixture
def synthesized(stack: Stack) -> str:
    """Fixture to provide the synthesized stack."""
    return Testing.synth(stack)


@pytest.mark.parametrize(
    "provider_name",
    [
        AwsProvider.TF_RESOURCE_TYPE,
        RandomProvider.TF_RESOURCE_TYPE,
    ],
)
def test_stack_has_providers(synthesized: str, provider_name: str) -> None:
    """Test the stack has all the providers."""
    assert Testing.to_have_provider(synthesized, provider_name)


@pytest.mark.parametrize(
    "resource_name",
    [
        ElasticacheReplicationGroup.TF_RESOURCE_TYPE,
        ElasticacheParameterGroup.TF_RESOURCE_TYPE,
    ],
)
def test_stack_has_resources(synthesized: str, resource_name: str) -> None:
    """Test the stack has all the resources."""
    assert Testing.to_have_resource(synthesized, resource_name)


def test_stack_elasticache_replication_group(synthesized: str) -> None:
    """Test the Elasticache replication group resource."""
    assert Testing.to_have_resource_with_properties(
        synthesized,
        ElasticacheReplicationGroup.TF_RESOURCE_TYPE,
        {
            "apply_immediately": True,
            "at_rest_encryption_enabled": True,
            "auth_token": "not-a-real-token",
            "auto_minor_version_upgrade": "false",
            "automatic_failover_enabled": True,
            "depends_on": ["aws_elasticache_parameter_group.elasticache-example-01-pg"],
            "description": "test instance",
            "engine": "redis",
            "engine_version": "6.2",
            "log_delivery_configuration": [],
            "maintenance_window": "wed:10:00-wed:11:00",
            "node_type": "cache.t4g.micro",
            "num_cache_clusters": 2,
            "parameter_group_name": "elasticache-example-01-pg",
            "replication_group_id": "elasticache-example-01",
            "security_group_ids": ["sg-123456789"],
            "snapshot_retention_limit": 2,
            "snapshot_window": "03:30-05:30",
            "subnet_group_name": "default",
            "transit_encryption_enabled": True,
        },
    )


def test_stack_elasticache_parameter_group(synthesized: str) -> None:
    """Test the Elasticache parameter group resource."""
    assert Testing.to_have_resource_with_properties(
        synthesized,
        ElasticacheParameterGroup.TF_RESOURCE_TYPE,
        {
            "description": "Just an example parameter group",
            "family": "redis6.x",
            "name": "elasticache-example-01-pg",
            "parameter": [{"name": "tcp-keepalive", "value": "300"}],
        },
    )
