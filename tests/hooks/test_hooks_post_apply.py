# ruff: file-ignore[call-datetime-now-without-tzinfo]
from datetime import datetime as dt
from typing import TYPE_CHECKING

import pytest
from external_resources_io.config import Action
from external_resources_io.terraform import (
    Change,
    ResourceChange,
    TerraformJsonPlanParser,
)

from hooks.post_apply import (
    default_cooldown,
    main,
    staging_complete,
    terraform_changes,
)
from hooks_lib.service_updates import ServiceUpdate
from hooks_lib.terraform_state import TerraformState

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from er_aws_elasticache.app_interface_input import AppInterfaceInput

SERVICE_UPDATE_ITEM = ServiceUpdate(
    name="update-1",
    release_date=dt.now(),
    severity="critical",
    status="not-applied",
    type="security",
)


def _state(resources: dict[str, dict]) -> TerraformState:
    return TerraformState.model_validate({
        "values": {
            "root_module": {
                "resources": [
                    {"address": address, "values": values}
                    for address, values in resources.items()
                ]
            }
        }
    })


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
def test_main(  # ruff: ignore[too-many-arguments]
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
    mocker.patch("hooks.post_apply.staging_complete", return_value=True)
    main(mock_plan, ai_input, dry_run=dry_run_flag, action=Action.APPLY)

    if expected_apply_call:
        mock_service_updates_manager.return_value.apply_service_update.assert_called_once()
    else:
        mock_service_updates_manager.return_value.apply_service_update.assert_not_called()


# staging_complete


def test_staging_complete_when_transit_encryption_disabled(
    ai_input: AppInterfaceInput,
) -> None:
    ai_input.data.transit_encryption_enabled = False

    assert staging_complete(ai_input, _state({})) is True


def test_staging_incomplete_when_mode_not_yet_reached(
    ai_input: AppInterfaceInput,
) -> None:
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "preferred",
        },
    })

    assert staging_complete(ai_input, state) is False


def test_staging_complete_when_mode_missing_assumed_required(
    ai_input: AppInterfaceInput,
) -> None:
    """A legacy resource with no recorded mode must not be stuck retrying forever.

    random_password.this is included because it's gated identically to the
    marker in main.tf - a real legacy resource (predating this fix) would
    already have it from the old unconditional behavior. Without it here,
    this fixture wasn't distinguishable from "mode ready, token never
    introduced" - exactly the APPSRE-15246 follow-up bug this file now
    guards against (missing exit-1 between loop 2 and loop 3).
    """
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {"transit_encryption_enabled": True},
        "random_password.this[0]": {"keepers": None},
    })

    assert staging_complete(ai_input, state) is True


def test_staging_incomplete_when_auth_token_never_introduced(
    ai_input: AppInterfaceInput,
) -> None:
    """Mode just reached required, but the token was never introduced - must retry fast, not wait ~24h."""
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
    })

    assert staging_complete(ai_input, state) is False


def test_staging_incomplete_when_marker_not_yet_set(
    ai_input: AppInterfaceInput,
) -> None:
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "ROTATE"},
        "random_password.this[0]": {"keepers": None},
    })

    assert staging_complete(ai_input, state) is False


def test_staging_complete_when_fully_settled(ai_input: AppInterfaceInput) -> None:
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "SET"},
        "random_password.this[0]": {"keepers": None},
    })

    assert staging_complete(ai_input, state) is True


# main() fast-retry behavior


def test_main_exits_when_staging_incomplete(
    mocker: MockerFixture,
    ai_input: AppInterfaceInput,
    mock_plan: TerraformJsonPlanParser,
) -> None:
    mocker.patch("hooks.post_apply.staging_complete", return_value=False)
    mocker.patch("hooks.post_apply.get_current_state")

    with pytest.raises(SystemExit) as exc_info:
        main(mock_plan, ai_input, dry_run=False, action=Action.APPLY)

    assert exc_info.value.code == 1


def test_main_skips_staging_check_on_dry_run(
    mocker: MockerFixture,
    ai_input: AppInterfaceInput,
    mock_plan: TerraformJsonPlanParser,
) -> None:
    staging_complete_mock = mocker.patch(
        "hooks.post_apply.staging_complete", return_value=False
    )
    mocker.patch("hooks.post_apply.ServiceUpdatesManager")
    mocker.patch("hooks.post_apply.terraform_changes", return_value=False)

    main(mock_plan, ai_input, dry_run=True, action=Action.APPLY)

    staging_complete_mock.assert_not_called()


def test_main_skips_staging_check_on_destroy(
    mocker: MockerFixture,
    ai_input: AppInterfaceInput,
    mock_plan: TerraformJsonPlanParser,
) -> None:
    staging_complete_mock = mocker.patch(
        "hooks.post_apply.staging_complete", return_value=False
    )
    mocker.patch("hooks.post_apply.ServiceUpdatesManager")
    mocker.patch("hooks.post_apply.terraform_changes", return_value=False)

    main(mock_plan, ai_input, dry_run=False, action=Action.DESTROY)

    staging_complete_mock.assert_not_called()
