# External Resources Elasticache Module

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

External Resources module to provision and manage Elasticache clusters in AWS with app-interface.

## Tech stack

* Terraform CDKTF
* AWS provider
* Random provider
* Python 3.11
* Pydantic

## Development

> :warning: **Attention**
>
> The CDKTF Python module generation needs at least 12GB of memory and takes around 5 minutes to complete.

Prepare your lcoal development environment:

```bash
make dev
```

See the `Makefile` for more details.

## Debugging

To debug and run the module locally, run the following commands:

```bash
# setup the environment
$ export VERSION=$(grep konflux.additional-tags Dockerfile | cut -f2 -d\")
$ export IMAGE=quay.io/redhat-services-prod/app-sre-tenant/er-aws-elasticache-main/er-aws-elasticache-main:$VERSION

# Get the input file from app-interface
qontract-cli --config=<CONFIG_TOML> external-resources --provisioner <AWS_ACCOUNT_NAME> --provider elasticache --identifier <IDENTIFIER> get-input > tmp/input.json

# Get the AWS credentials
$ vault login -method=oidc -address=https://vault.devshift.net
$ vault kv get \
    -mount app-sre/ \
    -field credentials \
    external-resources/<AWS_ACCOUNT_NAME> > tmp/credentials

# Run the stack
$ docker run --rm -it \
    --mount type=bind,source=$PWD/tmp/input.json,target=/inputs/input.json \
    --mount type=bind,source=$PWD/tmp/credentials,target=/credentials \
    "$IMAGE"
```

Get the stack file:

```bash
docker rm -f erv2 && docker run --name cdktf-debug \
  --mount type=bind,source=$PWD/tmp/input.json,target=/inputs/input.json \
  --mount type=bind,source=$PWD/tmp/credentials,target=/credentials  \
  --entrypoint cdktf \
  "$IMAGE" \
  synth --output /tmp/cdktf.out

docker cp cdktf-debug:/tmp/cdktf.out/stacks/CDKTF/cdk.tf.json tmp/cdk.tf.json
```

Compile the plan:

```bash
cd tmp/...
export AWS_SHARED_CREDENTIALS_FILE=../credentials
terraform init
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
```

Run the validation:

```bash
export ER_INPUT_FILE=$PWD/tmp/input.json
python validate_plan.py tmp/plan.json
```
