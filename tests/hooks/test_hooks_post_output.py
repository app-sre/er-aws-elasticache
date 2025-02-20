import pytest

from hooks.post_output import check


@pytest.mark.parametrize(
    ("outputs", "expected"),
    [
        (
            {
                "db_auth_token": {
                    "sensitive": True,
                    "type": "string",
                    "value": "token",
                },
                "db_endpoint": {
                    "sensitive": False,
                    "type": "string",
                    "value": "hostname",
                },
                "db_port": {
                    "sensitive": False,
                    "type": "number",
                    "value": 6379,
                },
            },
            True,
        ),
        (
            {
                "db_auth_token": {
                    "sensitive": True,
                    "type": "string",
                    "value": "token",
                },
                "db_endpoint": {
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
