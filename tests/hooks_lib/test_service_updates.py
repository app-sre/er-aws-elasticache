# ruff: noqa: DTZ001
from collections.abc import Sequence
from datetime import datetime as dt
from datetime import timedelta

import pytest
from pytest_mock import MockerFixture

from hooks_lib.aws_api import AWSApi
from hooks_lib.service_updates import ServiceUpdate, ServiceUpdatesManager

SERVICE_UPDATE_ITEM = ServiceUpdate(
    name="test-service-update",
    release_date=dt(2025, 1, 1),
    severity="critical",
    status="not-applied",
    type="security",
)
RAW_SERVICE_UPDATE_ITEM = {
    "ServiceUpdateName": SERVICE_UPDATE_ITEM.name,
    "ServiceUpdateReleaseDate": SERVICE_UPDATE_ITEM.release_date,
    "ServiceUpdateSeverity": SERVICE_UPDATE_ITEM.severity,
    "UpdateActionStatus": SERVICE_UPDATE_ITEM.status,
    "ServiceUpdateType": SERVICE_UPDATE_ITEM.type,
}


@pytest.mark.parametrize(
    ("service_updates", "expected"),
    [
        ([], False),
        ([SERVICE_UPDATE_ITEM], True),
    ],
)
def test_service_updates_update_in_progress(
    mocker: MockerFixture, service_updates: list, *, expected: bool
) -> None:
    aws_api_class = mocker.create_autospec(spec=AWSApi, spec_set=True)
    aws_api_class.return_value.get_service_updates.return_value = service_updates
    sumgr = ServiceUpdatesManager(
        "test-replication-group-id", "us-west-2", aws_api_class=aws_api_class
    )
    assert sumgr.update_in_progress is expected


@pytest.mark.parametrize(
    ("service_updates", "severities", "released_before", "expected"),
    [
        # no service updates
        ([], ["critical"], dt(2025, 1, 1), []),
        # no service updates with the specified severity
        ([RAW_SERVICE_UPDATE_ITEM], ["low"], dt(2025, 1, 1), []),
        # no service updates released before the specified date
        ([RAW_SERVICE_UPDATE_ITEM], ["critical"], dt(2024, 1, 1), []),
        # service updates with the specified severity and released before the specified date
        (
            [RAW_SERVICE_UPDATE_ITEM],
            [SERVICE_UPDATE_ITEM.severity],
            SERVICE_UPDATE_ITEM.release_date + timedelta(days=1),
            [SERVICE_UPDATE_ITEM],
        ),
    ],
)
def test_service_updates_list_service_updates(
    mocker: MockerFixture,
    service_updates: list,
    severities: Sequence[str],
    released_before: dt,
    *,
    expected: bool,
) -> None:
    aws_api_class = mocker.create_autospec(spec=AWSApi, spec_set=True)
    aws_api_class.return_value.get_service_updates.return_value = service_updates
    sumgr = ServiceUpdatesManager(
        "test-replication-group-id", "us-west-2", aws_api_class=aws_api_class
    )
    assert sumgr.service_updates(severities, released_before) == expected


@pytest.mark.parametrize("update_in_progress", [True, False])
def test_service_updates_apply_service_update(
    mocker: MockerFixture, *, update_in_progress: bool
) -> None:
    aws_api_class = mocker.create_autospec(spec=AWSApi, spec_set=True)
    sumgr = ServiceUpdatesManager(
        "test-replication-group-id", "us-west-2", aws_api_class=aws_api_class
    )
    mocker.patch.object(
        type(sumgr),
        "update_in_progress",
        new_callable=mocker.PropertyMock,
        return_value=update_in_progress,
    )
    if update_in_progress:
        with pytest.raises(RuntimeError):
            sumgr.apply_service_update(SERVICE_UPDATE_ITEM)
    else:
        sumgr.apply_service_update(SERVICE_UPDATE_ITEM, wait_for_completion=False)
        aws_api_class.return_value.batch_apply_service_updates.assert_called_once_with(
            replication_group_id="test-replication-group-id",
            service_update_name="test-service-update",
        )
