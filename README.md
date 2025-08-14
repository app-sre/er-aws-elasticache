# External Resources Elasticache Module

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

External Resources module to provision and manage Elasticache clusters in AWS with app-interface.

## Tech stack

* Terraform
* AWS provider
* Random provider
* Python 3.12
* Pydantic

## Development

Prepare your local development environment:

```bash
make dev
```

See the `Makefile` for more details.

### Update Terraform modules

To update the Terraform modules used in this project, bump the version in [versions.tf](/terraform/versions.tf) and update the Terraform lockfile via:

```bash
make providers-lock
```

### Development workflow

1. Make changes to the code.
1. Build the image with `make build`.
1. Run the image manually with a proper input file and credentials. See the [Debugging](#debugging) section below.
1. Please don't forget to remove (`-e ACTION=Destroy`) any development AWS resources you create, as they will incur costs.

### Running the Terraform Tests

Unfortunately, Terraform tests require AWS credentials to run, even if they don't create or change AWS resources (`command = plan`). Ensure you have the necessary credentials set up in your environment. For example, use `rh-aws-saml-login` to enter the `ter-int-dev` accounts.

```bash
rh-aws-saml-login ter-int-dev
```

With a proper AWS credentials in place, you should be able to run the Terraform tests without any issues.

```bash
make terraform-test-full
```

## Debugging

To debug and run the module locally, run the following commands:

```bash
# setup the environment
$ export VERSION=$(grep konflux.additional-tags Dockerfile | cut -f2 -d\")
$ export IMAGE=quay.io/redhat-services-prod/app-sre-tenant/er-aws-elasticache-main/er-aws-elasticache-main:$VERSION

# Get the input file from app-interface
qontract-cli --config=<CONFIG_TOML> external-resources --provisioner <AWS_ACCOUNT_NAME> --provider elasticache --identifier <IDENTIFIER> get-input > tmp/input.json

# Get the AWS credentials
$ qontract-cli --config=<CONFIG_TOML> external-resources --provisioner <AWS_ACCOUNT_NAME> --provider elasticache --identifier <IDENTIFIER> get-credentials > tmp/credentials

# Run the stack
$ docker run --rm -it \
    --mount type=bind,source=$PWD/tmp/input.json,target=/inputs/input.json \
    --mount type=bind,source=$PWD/tmp/credentials,target=/credentials \
    --mount type=bind,source=$PWD/tmp/work,target=/work \
    -e DRY_RUN=True \
    -e ACTION=Apply \
    "$IMAGE"
```
