FROM quay.io/redhat-services-prod/app-sre-tenant/er-base-terraform-main/er-base-terraform-main:0.3.8-13@sha256:a991d0835739fbed914f6433b0ce281939a4b47e65e6bdd4d994a953e50a63f6 AS base
# keep in sync with pyproject.toml
LABEL konflux.additional-tags="0.7.0"
ENV TERRAFORM_MODULE_SRC_DIR="./terraform"
ENV \
    # Use the virtual environment
    PATH="${APP}/.venv/bin:${PATH}"

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.8.18@sha256:62022a082ce1358336b920e9b7746ac7c95b1b11473aa93ab5e4f01232d6712d /uv /bin/uv

# Python and UV related variables
ENV \
    # compile bytecode for faster startup
    UV_COMPILE_BYTECODE="true" \
    # disable uv cache. it doesn't make sense in a container
    UV_NO_CACHE=true \
    UV_NO_PROGRESS=true

# Terraform code
COPY --chown=app:root ${TERRAFORM_MODULE_SRC_DIR} ${TERRAFORM_MODULE_SRC_DIR}
RUN terraform-provider-sync

COPY pyproject.toml uv.lock ./
# Test lock file is up to date
RUN uv lock --locked
# Install dependencies
RUN uv sync --frozen --no-group dev --no-install-project --python /usr/bin/python3

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
COPY --from=builder ${APP} ${APP}

FROM prod AS test
COPY --from=ghcr.io/astral-sh/uv:0.8.18@sha256:62022a082ce1358336b920e9b7746ac7c95b1b11473aa93ab5e4f01232d6712d /uv /bin/uv

# install test dependencies
RUN uv sync --frozen

COPY Makefile ./
COPY tests ./tests

RUN make in_container_test
