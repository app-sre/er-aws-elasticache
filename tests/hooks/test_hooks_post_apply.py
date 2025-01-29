# ruff: noqa: DTZ001, DTZ005
from datetime import datetime as dt

import pytest
from external_resources_io.terraform import (
    Change,
    ResourceChange,
    TerraformJsonPlanParser,
)
from pytest_mock import MockerFixture

from er_aws_elasticache.app_interface_input import AppInterfaceInput
from hooks.post_apply import (
    default_cooldown,
    main,
    terraform_changes,
)
from hooks_lib.service_updates import ServiceUpdate

SERVICE_UPDATE_ITEM = ServiceUpdate(
    name="update-1",
    release_date=dt.now(),
    severity="critical",
    status="not-applied",
    type="security",
)


@pytest.fixture
def mock_plan(mocker: MockerFixture) -> TerraformJsonPlanParser:
    plan = mocker.MagicMock(spec=TerraformJsonPlanParser)
    return plan()


@pytest.mark.parametrize(
    ("plan_changes", "expected_result"),
    [
        ([], False),
        ([ResourceChange(change=Change(actions=["create"], after_unknown=None))], True),
    ],
)
def test_terraform_changes(
    plan_changes: list[ResourceChange],
    *,
    expected_result: bool,
    mock_plan: TerraformJsonPlanParser,
) -> None:
    mock_plan.plan.resource_changes = plan_changes
    assert terraform_changes(mock_plan) == expected_result


@pytest.mark.parametrize(
    ("environment", "expected_cooldown"),
    [
        ("production", 14),
        ("staging", 7),
        ("dev", 5),
        ("stage", 7),
    ],
)
def test_default_cooldown(
    environment: str, expected_cooldown: int, ai_input: AppInterfaceInput
) -> None:
    ai_input.data.environment = environment
    assert default_cooldown(ai_input.data.environment) == expected_cooldown


@pytest.mark.parametrize(
    (
        "service_updates",
        "terraform_changes_flag",
        "dry_run_flag",
        "expected_apply_call",
    ),
    [
        ([], False, True, False),
        ([SERVICE_UPDATE_ITEM], False, True, False),
        ([SERVICE_UPDATE_ITEM], True, False, False),
        ([SERVICE_UPDATE_ITEM], False, False, True),
        ([SERVICE_UPDATE_ITEM], True, True, False),
    ],
)
def test_main(  # noqa: PLR0913
    mocker: MockerFixture,
    service_updates: list[ServiceUpdate],
    *,
    terraform_changes_flag: bool,
    dry_run_flag: bool,
    expected_apply_call: bool,
    ai_input: AppInterfaceInput,
    mock_plan: TerraformJsonPlanParser,
) -> None:
    mock_service_updates_manager = mocker.patch(
        "hooks.post_apply.ServiceUpdatesManager"
    )
    mock_service_updates_manager.return_value.service_updates.return_value = (
        service_updates
    )
    mocker.patch(
        "hooks.post_apply.terraform_changes", return_value=terraform_changes_flag
    )
    main(mock_plan, ai_input, dry_run=dry_run_flag)

    if expected_apply_call:
        mock_service_updates_manager.return_value.apply_service_update.assert_called_once()
    else:
        mock_service_updates_manager.return_value.apply_service_update.assert_not_called()
