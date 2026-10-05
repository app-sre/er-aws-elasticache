from typing import TYPE_CHECKING

import pytest

from hooks_lib.aws_api import AWSApi

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture
def aws_api() -> AWSApi:
    return AWSApi(config_options={"region_name": "us-east-1"})


@pytest.mark.parametrize(
    ("property_name", "service"), [("client", "elasticache"), ("ec2_client", "ec2")]
)
def test_client_is_constructed_once_per_instance(
    mocker: MockerFixture,
    aws_api: AWSApi,
    property_name: str,
    service: str,
) -> None:
    """Repeated property reads must reuse the configured boto3 client."""
    create_client = mocker.patch.object(
        aws_api.session,
        "client",
        side_effect=[mocker.sentinel.first_client, mocker.sentinel.second_client],
    )

    assert getattr(aws_api, property_name) is mocker.sentinel.first_client
    assert getattr(aws_api, property_name) is mocker.sentinel.first_client
    create_client.assert_called_once_with(service, config=aws_api.config)


@pytest.mark.parametrize("property_name", ["client", "ec2_client"])
def test_clients_are_not_shared_between_instances(
    mocker: MockerFixture, property_name: str
) -> None:
    """Caching must not mix clients across AWSApi instances or configurations."""
    session = mocker.patch("hooks_lib.aws_api.Session").return_value
    session.client.side_effect = [
        mocker.sentinel.first_client,
        mocker.sentinel.second_client,
    ]
    first = AWSApi(config_options={"region_name": "us-east-1"})
    second = AWSApi(config_options={"region_name": "us-west-2"})

    assert getattr(first, property_name) is mocker.sentinel.first_client
    assert getattr(second, property_name) is mocker.sentinel.second_client
    assert getattr(first, property_name) is mocker.sentinel.first_client
    assert session.client.call_count == len((first, second))


def test_get_cache_group_subnets_not_found(
    mocker: MockerFixture, aws_api: AWSApi
) -> None:
    mock_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "client", new=mock_client)

    mock_client_instance = mock_client.return_value
    mock_client_instance.describe_cache_subnet_groups.return_value = {
        "CacheSubnetGroups": []
    }

    with pytest.raises(
        ValueError, match="Cache subnet group test-cache-group not found"
    ):
        aws_api.get_cache_group_subnets("test-cache-group")

    mock_client_instance.describe_cache_subnet_groups.assert_called_once_with(
        CacheSubnetGroupName="test-cache-group"
    )


def test_get_subnets(mocker: MockerFixture, aws_api: AWSApi) -> None:
    mock_ec2_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "ec2_client", new=mock_ec2_client)

    mock_ec2_client_instance = mock_ec2_client.return_value
    expected_subnets = [{"SubnetId": "subnet-12345"}]
    mock_ec2_client_instance.describe_subnets.return_value = {
        "Subnets": expected_subnets
    }

    result = aws_api.get_subnets(["subnet-12345"])
    assert result == expected_subnets

    mock_ec2_client_instance.describe_subnets.assert_called_once_with(
        SubnetIds=["subnet-12345"]
    )


def test_get_security_groups(mocker: MockerFixture, aws_api: AWSApi) -> None:
    mock_ec2_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "ec2_client", new=mock_ec2_client)

    mock_ec2_client_instance = mock_ec2_client.return_value
    expected_security_groups = [{"GroupId": "sg-12345", "GroupName": "test-group"}]
    mock_ec2_client_instance.describe_security_groups.return_value = {
        "SecurityGroups": expected_security_groups
    }

    result = aws_api.get_security_groups(["sg-12345"])
    assert result == expected_security_groups

    mock_ec2_client_instance.describe_security_groups.assert_called_once_with(
        GroupIds=["sg-12345"]
    )


def test_get_service_updates(mocker: MockerFixture, aws_api: AWSApi) -> None:
    mock_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "client", new=mock_client)

    mock_client_instance = mock_client.return_value
    expected_updates = [
        {"ServiceUpdateName": "update-1", "ServiceUpdateReleaseDate": "2025-01-01"}
    ]
    mock_client_instance.describe_update_actions.return_value = {
        "UpdateActions": expected_updates
    }

    result = aws_api.get_service_updates("replication-group-id")
    assert result == expected_updates

    mock_client_instance.describe_update_actions.assert_called_once_with(
        ReplicationGroupIds=["replication-group-id"],
        ServiceUpdateStatus=["available"],
    )


@pytest.mark.parametrize("node_type", ["cache.t4g.micro", "cache.t4g.invalid"])
def test_get_node_type_availability_zones(
    mocker: MockerFixture, aws_api: AWSApi, node_type: str
) -> None:
    """Query the underlying EC2 instance type and consume every result page."""
    mock_ec2_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "ec2_client", new=mock_ec2_client)
    paginator = mock_ec2_client.return_value.get_paginator.return_value
    paginator.paginate.return_value = [
        {"InstanceTypeOfferings": [{"Location": "us-east-1a"}]},
        {"InstanceTypeOfferings": [{"Location": "us-east-1b"}]},
    ]

    assert aws_api.get_node_type_availability_zones(node_type=node_type) == {
        "us-east-1a",
        "us-east-1b",
    }
    mock_ec2_client.return_value.get_paginator.assert_called_once_with(
        "describe_instance_type_offerings"
    )
    paginator.paginate.assert_called_once_with(
        LocationType="availability-zone",
        Filters=[
            {"Name": "instance-type", "Values": [node_type.removeprefix("cache.")]}
        ],
    )


def test_get_node_type_availability_zones_empty(
    mocker: MockerFixture, aws_api: AWSApi
) -> None:
    """No offerings means unavailable, never an implicit success."""
    mock_ec2_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "ec2_client", new=mock_ec2_client)
    mock_ec2_client.return_value.get_paginator.return_value.paginate.return_value = [
        {"InstanceTypeOfferings": []}
    ]

    assert (
        aws_api.get_node_type_availability_zones(node_type="cache.t4g.invalid") == set()
    )


def test_get_replication_group_availability_zones(
    mocker: MockerFixture, aws_api: AWSApi
) -> None:
    """Collect primary and replica placements across all shards."""
    mock_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "client", new=mock_client)
    mock_client.return_value.describe_replication_groups.return_value = {
        "ReplicationGroups": [
            {
                "NodeGroups": [
                    {
                        "NodeGroupMembers": [
                            {"PreferredAvailabilityZone": "us-east-1a"},
                            {"PreferredAvailabilityZone": "us-east-1b"},
                        ]
                    },
                    {"NodeGroupMembers": [{"PreferredAvailabilityZone": "us-east-1e"}]},
                ]
            }
        ]
    }

    assert aws_api.get_replication_group_availability_zones(
        replication_group_id="test-cluster"
    ) == {"us-east-1a", "us-east-1b", "us-east-1e"}
    mock_client.return_value.describe_replication_groups.assert_called_once_with(
        ReplicationGroupId="test-cluster"
    )


def test_batch_apply_service_updates(mocker: MockerFixture, aws_api: AWSApi) -> None:
    mock_client = mocker.PropertyMock()
    mocker.patch.object(type(aws_api), "client", new=mock_client)

    mock_client_instance = mock_client.return_value
    processed_action = {"ReplicationGroupId": "rg-1", "ServiceUpdateName": "update-1"}
    mock_client_instance.batch_apply_update_action.return_value = {
        "ProcessedUpdateActions": [processed_action],
        "UnprocessedUpdateActions": [],
    }

    result = aws_api.batch_apply_service_updates("rg-1", "update-1")
    assert result == processed_action

    mock_client_instance.batch_apply_update_action.assert_called_once_with(
        ReplicationGroupIds=["rg-1"], ServiceUpdateName="update-1"
    )
