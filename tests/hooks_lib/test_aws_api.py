import pytest
from pytest_mock import MockerFixture

from hooks_lib.aws_api import AWSApi


@pytest.fixture
def aws_api() -> AWSApi:
    return AWSApi(config_options={"region_name": "us-east-1"})


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
