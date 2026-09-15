from hooks_lib.terraform_state import TerraformState


def test_get_resource_found() -> None:
    state = TerraformState.model_validate({
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
    })

    assert state.get_resource("aws_elasticache_replication_group.this") == {
        "transit_encryption_enabled": True
    }


def test_get_resource_not_found() -> None:
    state = TerraformState.model_validate({
        "values": {
            "root_module": {
                "resources": [
                    {"address": "random_password.this[0]", "values": {}},
                ]
            }
        }
    })

    assert state.get_resource("aws_elasticache_replication_group.this") is None


def test_get_resource_empty_state() -> None:
    """An empty/fresh state (no prior apply) has no "values" key at all."""
    state = TerraformState.model_validate({})

    assert state.get_resource("aws_elasticache_replication_group.this") is None
