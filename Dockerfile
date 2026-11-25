FROM quay.io/redhat-services-prod/app-sre-tenant/er-base-terraform-main/er-base-terraform-main:0.6.0-27@sha256:82feaf5e763c606c1708b59c813607b07c5f1ae1a7d55613737b03ab8bb5f8e7 AS base
# keep in sync with pyproject.toml
LABEL konflux.additional-tags="0.12.0"
ENV TERRAFORM_MODULE_SRC_DIR="./terraform"

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f /uv /bin/uv

# Terraform code
COPY --chown=${USER}:root ${TERRAFORM_MODULE_SRC_DIR} ${TERRAFORM_MODULE_SRC_DIR}
RUN terraform-provider-sync

COPY pyproject.toml uv.lock ./
# Test lock file is up to date
RUN uv lock --locked
# Install dependencies
RUN uv sync --frozen --no-group dev --no-install-project

# the source code
COPY README.md ./
COPY hooks ./hooks
COPY hooks_lib ./hooks_lib
COPY er_aws_elasticache ./er_aws_elasticache
# Sync the project
RUN uv sync --frozen --no-group dev


FROM base AS prod
# get cdktf providers
COPY --from=builder ${TF_PLUGIN_CACHE_DIR} ${TF_PLUGIN_CACHE_DIR}
# get our app with the dependencies
COPY --from=builder ${APP_ROOT} ${APP_ROOT}

FROM prod AS test
COPY --from=ghcr.io/astral-sh/uv:0.13.10@sha256:a3ea1357342c1a4bf9a0c53a3deb1b55379aefa037338d8113d5771efa01774f /uv /bin/uv

# install test dependencies
RUN uv sync --frozen

COPY Makefile ./
COPY tests ./tests

RUN make in_container_test
