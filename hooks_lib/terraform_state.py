from typing import Any

from external_resources_io.terraform import terraform_run
from pydantic import BaseModel


class StateResource(BaseModel):
    """A single resource entry from `terraform show -json` state output."""

    address: str
    values: dict[str, Any] = {}


class StateRootModule(BaseModel):
    """The root_module section of `terraform show -json` state output."""

    resources: list[StateResource] = []


class StateValues(BaseModel):
    """The values section of `terraform show -json` state output."""

    root_module: StateRootModule = StateRootModule()


class TerraformState(BaseModel):
    """Parsed `terraform show -json` state output (distinct from the plan format)."""

    values: StateValues = StateValues()

    def get_resource(self, address: str) -> dict[str, Any] | None:
        """Get a resource's values by its address, e.g. 'aws_elasticache_replication_group.this'."""
        for resource in self.values.root_module.resources:
            if resource.address == address:
                return resource.values
        return None


def get_current_state() -> TerraformState:
    """Read the current Terraform state, shared by hooks that run before or after apply."""
    output = terraform_run(["show", "-json"], dry_run=False)
    return TerraformState.model_validate_json(output) if output else TerraformState()
