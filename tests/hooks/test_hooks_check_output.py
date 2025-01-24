import pytest

from hooks.check_output import check


@pytest.mark.parametrize(
    ("outputs", "expected"),
    [
        (
            {
                "glitchtip-dev-elasticache__db_auth_token": {
                    "sensitive": True,
                    "type": "string",
                    "value": "token",
                },
                "glitchtip-dev-elasticache__db_endpoint": {
                    "sensitive": False,
                    "type": "string",
                    "value": "hostname",
                },
                "glitchtip-dev-elasticache__db_port": {
                    "sensitive": False,
                    "type": "number",
                    "value": 6379,
                },
            },
            True,
        ),
        (
            {
                "glitchtip-dev-elasticache__db_auth_token": {
                    "sensitive": True,
                    "type": "string",
                    "value": "token",
                },
                "glitchtip-dev-elasticache__db_endpoint": {
                    "sensitive": False,
                    "type": "string",
                    "value": "hostname",
                },
            },
            False,
        ),
    ],
)
def test_post_checks_check(outputs: dict, expected: bool) -> None:  # noqa: FBT001
    """Test the check function."""
    assert check(outputs) == expected
