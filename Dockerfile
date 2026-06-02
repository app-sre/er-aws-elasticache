FROM quay.io/redhat-services-prod/app-sre-tenant/er-base-terraform-main/er-base-terraform-main:0.6.0-1@sha256:f234d99c2970151dc445ecd0870bd320c3ccdb9a9e579f97a84779a640f2f1ee AS base
# keep in sync with pyproject.toml
LABEL konflux.additional-tags="0.9.0"
ENV TERRAFORM_MODULE_SRC_DIR="./terraform"

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.18@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 /uv /bin/uv

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
COPY --from=ghcr.io/astral-sh/uv:0.11.18@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 /uv /bin/uv

# install test dependencies
RUN uv sync --frozen

COPY Makefile ./
COPY tests ./tests

RUN make in_container_test
