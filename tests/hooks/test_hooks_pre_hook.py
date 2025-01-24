import pytest
from pytest_mock import MockerFixture

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks.pre_hook import (
    main,
)
from hooks_lib.service_updates import ServiceUpdatesManager


@pytest.mark.parametrize("update_in_progress", [True, False])
def test_main(
    mocker: MockerFixture, *, update_in_progress: bool, ai_input: AppInterfaceInput
) -> None:
    mocker.patch.object(
        ServiceUpdatesManager,
        "update_in_progress",
        new_callable=mocker.PropertyMock,
        return_value=update_in_progress,
    )
    sys_exit_mock = mocker.patch("sys.exit")

    main(ai_input)

    if update_in_progress:
        sys_exit_mock.assert_called_once_with(1)
    else:
        sys_exit_mock.assert_not_called()
