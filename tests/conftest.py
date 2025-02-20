import pytest
from external_resources_io.input import parse_model

from er_aws_elasticache.app_interface_input import AppInterfaceInput


@pytest.fixture
def raw_input_data() -> dict:
    """Fixture to provide test data for the AppInterfaceInput."""
    return {
        "data": {
            "replication_group_id": "elasticache-example-01",
            "replication_group_description": "test instance",
            "node_type": "cache.t4g.micro",
            "automatic_failover_enabled": True,
            "auto_minor_version_upgrade": False,
            "engine": "redis",
            "at_rest_encryption_enabled": True,
            "transit_encryption_enabled": True,
            "engine_version": "6.2",
            "apply_immediately": True,
            "security_group_ids": ["sg-123456789"],
            "maintenance_window": "wed:10:00-wed:11:00",
            "snapshot_window": "03:30-05:30",
            "snapshot_retention_limit": 2,
            "subnet_group_name": "default",
            "number_cache_clusters": 2,
            "identifier": "example-elasticache",
            "parameter_group": {
                "family": "redis6.x",
                "description": "Just an example parameter group",
                "parameters": [{"name": "tcp-keepalive", "value": "300"}],
                "name": "elasticache-example-01-pg",
            },
            "output_resource_name": "example-elasticache",
            "output_prefix": "example-elasticache-elasticache",
            "tags": {
                "managed_by_integration": "external_resources",
                "cluster": "appint-ex-01",
                "namespace": "example-elasticache-01",
                "environment": "production",
                "app": "elasticache-example",
            },
            "default_tags": [{"tags": {"app": "app-sre-infra"}}],
            "region": "us-east-1",
            "parameter_group_name": "elasticache-example-01-pg",
            "environment": "production",
            "service_updates_enabled": True,
            "service_updates_severities": ["critical", "important"],
            "service_updates_cooldown_days": None,
        },
        "provision": {
            "provision_provider": "aws",
            "provisioner": "app-int-example-01",
            "provider": "elasticache",
            "identifier": "example-elasticache",
            "target_cluster": "appint-ex-01",
            "target_namespace": "example-elasticache-01",
            "target_secret_name": "example-elasticache",
            "module_provision_data": {
                "tf_state_bucket": "external-resources-terraform-state-dev",
                "tf_state_region": "us-east-1",
                "tf_state_dynamodb_table": "external-resources-terraform-lock",
                "tf_state_key": "aws/app-int-example-01/elasticache/example-elasticache/terraform.tfstate",
            },
        },
    }


@pytest.fixture
def ai_input(raw_input_data: dict) -> AppInterfaceInput:
    """Fixture to provide the AppInterfaceInput."""
    return parse_model(AppInterfaceInput, raw_input_data)
