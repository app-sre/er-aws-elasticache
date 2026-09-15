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

## Design notes

### Engine version is a hard requirement, not just a documented caveat

Enabling `transit_encryption_enabled` on an *existing* replication group only works in-place on
sufficiently new engines (Valkey 7.2+ as of AWS's current documentation). On older engines, the
AWS provider's `ForceNewIf` on `transit_encryption_enabled` makes Terraform **replace** the
cluster (destroy + recreate) instead of updating it, destroying all data.

`hooks/post_plan.py`'s `_validate_transit_encryption_engine_support` blocks this outright with a
clear error rather than relying on a tenant noticing a `-/+ destroy and then create replacement`
in a plan diff before approving it. This check is deliberately **not** gated on
`Action.ActionUpdate` like the other checks in this file — for unsupported engines, Terraform
represents the change as `[delete, create]` (a replace), not `[update]`, so it's gated on
`change.change.before is not None` instead (existing resource, regardless of how Terraform
classifies the change).


### Staging `transit_encryption_enabled` / `auth_token_update_strategy` on existing resources

Switching an existing (already-created) replication group from no-auth to a required AUTH
token is not a single-step AWS operation. Two independent AWS API constraints force a staged,
multi-apply sequence:

1. **`transit_encryption_mode` staging**: enabling `transit_encryption_enabled` on an existing
   resource must be paired with `transit_encryption_mode = "preferred"` in the same call
   ([AWS `ModifyReplicationGroup` reference](https://docs.aws.amazon.com/AmazonElastiCache/latest/APIReference/API_ModifyReplicationGroup.html)).
   Moving from `preferred` to `required` is only accepted as a separate, later call.
2. **`auth_token_update_strategy` staging**: introducing an AUTH token requires
   `ROTATE` first (which only makes the token *optional* — unauthenticated connections still
   work) and `SET` afterward, in a separate apply, to make it *required*
   ([AWS AUTH docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/red-ug/auth.html)).
   Sending `SET` without a prior `ROTATE` fails with `There is no AUTH token to SET`.
3. These two are coupled: AWS also rejects **any** AUTH token operation, including `ROTATE`,
   while `transit_encryption_mode` is `"preferred"` (confirmed live —
   `InvalidParameterValue: The AUTH token modification is only supported when
   encryption-in-transit is enabled`). So the auth-token staging can't even begin until the
   mode staging has landed on `"required"`.

   **Safety note**: the gate checks for a *confirmed* `"preferred"`, not "anything other than
   required" — a resource that predates `transit_encryption_mode` tracking (created before this
   field existed, or without it ever explicitly set) may have no recorded value in state at all,
   even though it's already running with a working, required auth token via this module's
   pre-existing, unconditional `SET`-always behavior. Treating a missing/unknown mode as blocking
   would regress every such already-working production resource the moment this ships; treating
   it as "assume already required" preserves existing behavior while still correctly blocking the
   one case we've confirmed is actually broken (`"preferred"`).

Combined, going from no-auth to fully-required-auth takes up to 4 automatic reconcile loops:

| Loop | Prior state                        | This run                                                           | Why                                                |
| ---- | ---------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------- |
| 1    | `transit_encryption_enabled=false` | enable + `transit_encryption_mode=preferred`; auth token untouched | AWS requires enabling + `preferred` together       |
| 2    | `mode=preferred`                   | `transit_encryption_mode` → `required`; auth token still untouched | `preferred` must already be live before `required` |
| 3    | `mode=required`                    | `auth_token_update_strategy=ROTATE`                                | now unblocked; introduces the token (optional)     |
| 4    | marker shows `ROTATE`              | `auth_token_update_strategy=SET`                                   | finalizes the token as required                    |

**The tenant contract**: `transit_encryption_mode` must be set to `"required"` explicitly by
the tenant (alongside `transit_encryption_enabled: true` and `apply_immediately: true`) — this
module stages the *path* there, it does not choose or default the *destination*.
`transit_encryption_mode: "preferred"` is rejected by `hooks/post_plan.py`'s
`_validate_transit_encryption_mode` for this transition, since this module always generates an
auth token whenever `transit_encryption_enabled` is true (no separate "no auth wanted" toggle),
and `preferred`-forever would leave the reconciler permanently stuck waiting for `required`.

**Implementation**:

* `hooks/pre_plan.py` reads the current Terraform state (`terraform show -json`, via
  `hooks_lib.terraform_state.get_current_state`) and computes both `auth_token_update_strategy`
  and `transit_encryption_mode_override` for this run, writing them to
  `transit_encryption_staging.auto.tfvars.json` in the module directory.
* Both are declared as internal-only variables in `terraform/transit_encryption_staging.tf`,
  deliberately **not** part of `ElasticacheData`/the generated `variables.tf`. If they were,
  `terraform.tfvars.json` (generated from `ElasticacheData`) would carry a value passed via an
  explicit `-var-file` CLI flag — which always wins over an auto-loaded `*.auto.tfvars.json`
  override in Terraform's precedence order, making the hook's override meaningless.
* Progress toward `SET` is tracked via a dedicated `terraform_data.auth_token_rotation`
  resource, not AWS's own `describe_replication_groups` or the replication group's own
  `auth_token_update_strategy` state attribute. AWS's read API can't distinguish an optional
  (`ROTATE`-only) token from a required (`SET`) one once the operation settles, and the AWS
  provider's v5→v6 state migration force-sets `auth_token_update_strategy` to `ROTATE` for any
  pre-existing state that predates the attribute — neither is a reliable signal for "did we
  already rotate this specific token in." `transit_encryption_mode` doesn't have this problem
  and is read directly from the replication group's own state.
* `hooks/post_apply.py`'s `staging_complete` check makes the reconciler retry quickly
  (`sys.exit(1)`) instead of waiting for the next ~24h scheduled reconcile while any of the
  above stages are incomplete.

**Known limitation: a failed first `ROTATE` attempt is indistinguishable from a legacy
resource.** `random_password.this[0]` must exist *before* `aws_elasticache_replication_group.this`
is applied (its `auth_token` attribute references `random_password.this[0].result`), so it
cannot itself `depends_on` the replication group the way `terraform_data.auth_token_rotation`
does (that would be a dependency cycle: the replication group needs the password's value as
an input). This means `random_password.this[0]` can commit to state even if the very same
apply's `ModifyReplicationGroup` call fails.

Concretely: on the very first `ROTATE` for a resource (marker and `random_password.this[0]`
both absent beforehand), if that apply's AWS call fails after `random_password.this[0]` has
already been created, the next run sees `marker=None, random_password=<present>` — exactly
the same shape `compute_auth_token_update_strategy` treats as "legacy resource, already
steady-state" (see the safety note above). It picks `SET` instead of retrying `ROTATE`,
which AWS rejects (`There is no AUTH token to SET`), stalling the reconcile loop.

This is a narrow race (requires the `ModifyReplicationGroup` call to fail on that specific
apply) with no data loss — recovery is manual: inspect state for a `random_password.this[0]`
with no corresponding `terraform_data.auth_token_rotation`, and either `terraform state rm`
the stray `random_password.this[0]` (forcing a clean re-attempt at `ROTATE`) or manually set
`transit_encryption_staging.auto.tfvars.json`'s `auth_token_update_strategy` to `"ROTATE"` for
one apply. Not automated because it can't be disambiguated purely from Terraform state without
either accepting a dependency cycle or introducing a second state machine to track the first
one's reliability — not worth the added complexity for a failure mode this narrow.

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
