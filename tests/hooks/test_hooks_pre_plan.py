import json
from typing import TYPE_CHECKING

from hooks.pre_plan import (
    AUTO_TFVARS_FILENAME,
    compute_auth_token_update_strategy,
    compute_transit_encryption_mode,
    get_current_state,
    main,
)
from hooks_lib.terraform_state import TerraformState

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from er_aws_elasticache.app_interface_input import AppInterfaceInput


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


# compute_auth_token_update_strategy


def test_brand_new_resource_returns_set(ai_input: AppInterfaceInput) -> None:
    """auth_token_update_strategy isn't used during create, but must be non-null so the auth_token is still sent."""
    assert compute_auth_token_update_strategy(ai_input, _state({})) == "SET"


def test_existing_resource_without_encryption_blocks(
    ai_input: AppInterfaceInput,
) -> None:
    """Encryption isn't live yet; the auth token is blocked until it is."""
    state = _state({
        "aws_elasticache_replication_group.this": {"transit_encryption_enabled": False},
    })

    assert compute_auth_token_update_strategy(ai_input, state) is None


def test_encryption_enabled_but_mode_preferred_blocks(
    ai_input: AppInterfaceInput,
) -> None:
    """AWS blocks any AUTH token operation while transit_encryption_mode is preferred."""
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "preferred",
        },
    })

    assert compute_auth_token_update_strategy(ai_input, state) is None


def test_encryption_enabled_but_mode_missing_does_not_block(
    ai_input: AppInterfaceInput,
) -> None:
    """A resource with no recorded mode (but already encrypted) must not be blocked - assumed already "required"."""
    ai_input.data.reset_password = None
    state = _state({
        "aws_elasticache_replication_group.this": {"transit_encryption_enabled": True},
        "random_password.this[0]": {"keepers": None},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "SET"


def test_mode_just_reached_required_rotates(ai_input: AppInterfaceInput) -> None:
    """Neither the marker nor random_password.this exists yet - a genuine first-time introduction, not steady state."""
    ai_input.data.reset_password = None
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "ROTATE"


def test_pending_rotation_gets_finalized(ai_input: AppInterfaceInput) -> None:
    """A previous run rotated a new token in; this run must finalize it with SET.

    random_password.this is included here because it's gated on the exact same
    condition as the marker, so it always exists whenever the marker does -
    the bug this test now guards against (APPSRE-15246 follow-up) was masked
    by an earlier version of this fixture that omitted it, which didn't
    reflect a state Terraform could actually produce.
    """
    ai_input.data.reset_password = None
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "ROTATE"},
        "random_password.this[0]": {"keepers": None},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "SET"


def test_marker_created_but_random_password_missing_still_finalizes(
    ai_input: AppInterfaceInput,
) -> None:
    """If only the marker survived a partial apply failure, finalizing with SET must still take priority."""
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "ROTATE"},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "SET"


def test_random_password_created_but_marker_missing_treated_as_steady_state(
    ai_input: AppInterfaceInput,
) -> None:
    """Without the marker we can't tell this apart from steady state, so it falls through to reset_password."""
    ai_input.data.reset_password = None
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "random_password.this[0]": {"keepers": None},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "SET"


def test_failed_first_rotation_attempt_is_indistinguishable_from_legacy_steady_state(
    ai_input: AppInterfaceInput,
) -> None:
    """Known, accepted limitation - see README's "Known limitation" note.

    random_password.this[0] must exist before aws_elasticache_replication_group.this
    is applied (its auth_token references random_password.this[0].result), so unlike
    the marker it cannot depends_on the replication group - it can commit to state
    even if that same apply's ModifyReplicationGroup call fails. A failed first-ever
    ROTATE therefore produces the exact same state shape as a genuine legacy resource
    (marker absent, random_password present), and this returns "SET" here too - which
    AWS will reject, stalling the reconcile loop until a human intervenes (see README).
    This test pins that known behavior, not the desired one.
    """
    ai_input.data.reset_password = None
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "random_password.this[0]": {"keepers": None},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "SET"


def test_steady_state_stays_set(ai_input: AppInterfaceInput) -> None:
    ai_input.data.reset_password = "reset-1"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "SET"},
        "random_password.this[0]": {"keepers": {"reset_password": "reset-1"}},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "SET"


def test_reset_password_change_restarts_rotation(ai_input: AppInterfaceInput) -> None:
    ai_input.data.reset_password = "reset-2"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "SET"},
        "random_password.this[0]": {"keepers": {"reset_password": "reset-1"}},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "ROTATE"


def test_reset_password_change_during_pending_rotation_restarts_cycle(
    ai_input: AppInterfaceInput,
) -> None:
    """A password change must win over a pending finalize.

    marker.input == "ROTATE" means a previous run already rotated in the
    OLD password. If reset_password changes again before the follow-up SET
    apply, random_password will be replaced with a NEW value in this same
    apply - finalizing with SET here would ask AWS to SET a token it never
    actually ROTATEd in. Must restart the cycle with ROTATE instead.
    """
    ai_input.data.reset_password = "reset-2"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
        "terraform_data.auth_token_rotation[0]": {"input": "ROTATE"},
        "random_password.this[0]": {"keepers": {"reset_password": "reset-1"}},
    })

    assert compute_auth_token_update_strategy(ai_input, state) == "ROTATE"


# compute_transit_encryption_mode


def test_mode_no_desired_value_returns_none(ai_input: AppInterfaceInput) -> None:
    ai_input.data.transit_encryption_mode = None

    assert compute_transit_encryption_mode(ai_input, _state({})) is None


def test_mode_brand_new_resource_passes_through(ai_input: AppInterfaceInput) -> None:
    ai_input.data.transit_encryption_mode = "required"

    assert compute_transit_encryption_mode(ai_input, _state({})) is None


def test_mode_already_at_desired_value_returns_none(
    ai_input: AppInterfaceInput,
) -> None:
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "required",
        },
    })

    assert compute_transit_encryption_mode(ai_input, state) is None


def test_mode_first_time_enabling_stages_preferred(ai_input: AppInterfaceInput) -> None:
    """Desired is required, but encryption was never enabled - must land on preferred first."""
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {"transit_encryption_enabled": False},
    })

    assert compute_transit_encryption_mode(ai_input, state) == "preferred"


def test_mode_stale_value_ignored_when_encryption_was_disabled(
    ai_input: AppInterfaceInput,
) -> None:
    """A stale mode in state must be ignored if encryption itself wasn't enabled - preferred is always the first step."""
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": False,
            "transit_encryption_mode": "required",
        },
    })

    assert compute_transit_encryption_mode(ai_input, state) == "preferred"


def test_mode_missing_on_already_encrypted_resource_assumed_required(
    ai_input: AppInterfaceInput,
) -> None:
    """An already-encrypted resource with no recorded mode is assumed "required", not staged backward to "preferred"."""
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {"transit_encryption_enabled": True},
    })

    assert compute_transit_encryption_mode(ai_input, state) is None


def test_mode_preferred_to_required_staging(ai_input: AppInterfaceInput) -> None:
    """preferred is already live; required can now be requested directly."""
    ai_input.data.transit_encryption_mode = "required"
    state = _state({
        "aws_elasticache_replication_group.this": {
            "transit_encryption_enabled": True,
            "transit_encryption_mode": "preferred",
        },
    })

    assert compute_transit_encryption_mode(ai_input, state) == "required"


def test_mode_desired_preferred_single_step(ai_input: AppInterfaceInput) -> None:
    """A tenant whose final desired mode is "preferred" doesn't need staging through an intermediate value."""
    ai_input.data.transit_encryption_mode = "preferred"
    state = _state({
        "aws_elasticache_replication_group.this": {"transit_encryption_enabled": False},
    })

    assert compute_transit_encryption_mode(ai_input, state) == "preferred"


# main


def test_main_writes_both_keys_when_staging_needed(
    mocker: MockerFixture, tmp_path: Path, ai_input: AppInterfaceInput
) -> None:
    ai_input.data.transit_encryption_mode = "required"
    mocker.patch("hooks.pre_plan.Config").return_value.variables_tf_file = str(
        tmp_path / "variables.tf"
    )
    mocker.patch(
        "hooks.pre_plan.get_current_state",
        return_value=_state({
            "aws_elasticache_replication_group.this": {
                "transit_encryption_enabled": False
            },
        }),
    )

    main(ai_input)

    output_file = tmp_path / AUTO_TFVARS_FILENAME
    assert json.loads(output_file.read_text()) == {
        "auth_token_update_strategy": None,
        "transit_encryption_mode_override": "preferred",
    }


def test_main_skips_state_lookup_when_transit_encryption_disabled(
    mocker: MockerFixture, tmp_path: Path, ai_input: AppInterfaceInput
) -> None:
    mocker.patch("hooks.pre_plan.Config").return_value.variables_tf_file = str(
        tmp_path / "variables.tf"
    )
    get_current_state_mock = mocker.patch("hooks.pre_plan.get_current_state")
    ai_input.data.transit_encryption_enabled = False

    main(ai_input)

    get_current_state_mock.assert_not_called()
    assert not (tmp_path / AUTO_TFVARS_FILENAME).exists()


def test_get_current_state_returns_default_on_empty_output(
    mocker: MockerFixture,
) -> None:
    mocker.patch("hooks_lib.terraform_state.terraform_run", return_value="")

    assert get_current_state() == TerraformState()


def test_get_current_state_parses_terraform_show_output(mocker: MockerFixture) -> None:
    mocker.patch(
        "hooks_lib.terraform_state.terraform_run",
        return_value=json.dumps({
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_elasticache_replication_group.this",
                            "values": {"transit_encryption_enabled": True},
                        }
                    ]
                }
            }
        }),
    )

    state = get_current_state()

    assert state.get_resource("aws_elasticache_replication_group.this") == {
        "transit_encryption_enabled": True
    }
